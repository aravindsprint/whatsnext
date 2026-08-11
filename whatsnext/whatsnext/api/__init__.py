import json
import re
from datetime import timedelta

import frappe
from frappe.utils import now_datetime, add_to_date, getdate

from whatsnext.whatsnext.provider_engine import get_provider, WhatsAppSendError, MetaProvider
from whatsnext.whatsnext.contacts import resolve_customer_from_phone, normalize_outbound_number
from whatsnext.whatsnext.permissions import get_allowed_customers

MESSAGE_FIELDS = [
	"name", "type", "provider", "status", "to_number", "from_number", "profile_name",
	"message", "message_type", "content_type", "attach", "template", "template_parameters",
	"reference_doctype", "reference_name", "conversation_id", "provider_message_id",
	"error_message", "scheduled_time", "creation", "modified",
]


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	"""Guest-accessible so the SPA shell can bootstrap a CSRF token before login."""
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def whoami():
	roles = frappe.get_roles(frappe.session.user)
	return {
		"user": frappe.session.user,
		"roles": roles,
		"is_system_manager": "System Manager" in roles,
	}


def _map_meta_category(cat: str) -> str:
	cat = (cat or "").upper()
	if cat == "MARKETING":
		return "Marketing"
	if cat == "AUTHENTICATION":
		return "Authentication"
	return "Utility"  # UTILITY, TRANSACTIONAL, or anything unrecognized


def _map_meta_status(status: str) -> str:
	return {"APPROVED": "Approved", "PENDING": "Pending", "REJECTED": "Rejected"}.get((status or "").upper(), "Draft")


def _map_button_type(btn_type: str) -> str:
	return {
		"QUICK_REPLY": "Quick Reply",
		"URL": "URL",
		"PHONE_NUMBER": "Phone Number",
	}.get((btn_type or "").upper(), "Quick Reply")


@frappe.whitelist()
def sync_templates_from_meta():
	"""Pull every template from the connected Meta WABA and create local
	Whatsnext Message Template records for any that don't already exist
	here (matched by meta_template_id, falling back to name+language).
	Existing local templates just get their approval status refreshed."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Managers can sync templates.", frappe.PermissionError)

	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.meta_enabled:
		frappe.throw("Meta WhatsApp Cloud API is not enabled in Whatsnext Settings.")

	remote_templates = MetaProvider(settings).fetch_templates()

	created, updated = 0, 0

	for t in remote_templates:
		meta_id = t.get("id")
		name = t.get("name")
		language = t.get("language")

		existing = frappe.db.get_value("Whatsnext Message Template", {"meta_template_id": meta_id}, "name")
		if not existing:
			existing = frappe.db.get_value(
				"Whatsnext Message Template",
				{"template_name": name, "language": language},
				"name",
			)

		header_text = ""
		header_type = ""
		header_example_url = ""
		footer_text = ""
		body = ""
		buttons = []
		for comp in t.get("components", []):
			ctype = (comp.get("type") or "").upper()
			if ctype == "HEADER":
				header_type = (comp.get("format") or "Text").title()
				if header_type == "Text":
					header_text = comp.get("text", "")
				else:
					handles = comp.get("example", {}).get("header_handle", [])
					if handles:
						header_example_url = handles[0]
			elif ctype == "BODY":
				body = comp.get("text", "")
			elif ctype == "FOOTER":
				footer_text = comp.get("text", "")
			elif ctype == "BUTTONS":
				for b in comp.get("buttons", []):
					buttons.append({
						"button_type": _map_button_type(b.get("type")),
						"button_text": b.get("text", ""),
						"button_value": b.get("url") or b.get("phone_number") or "",
					})

		if existing:
			doc = frappe.get_doc("Whatsnext Message Template", existing)
			doc.approval_status = _map_meta_status(t.get("status"))
			doc.meta_template_id = meta_id
			if header_example_url:
				doc.header_example_url = header_example_url
			doc.save(ignore_permissions=True)
			updated += 1
			continue

		doc = frappe.get_doc({
			"doctype": "Whatsnext Message Template",
			"template_name": name,
			"provider": "Meta",
			"language": language,
			"category": _map_meta_category(t.get("category")),
			"approval_status": _map_meta_status(t.get("status")),
			"meta_template_id": meta_id,
			"header_type": header_type or None,
			"header_text": header_text,
			"header_example_url": header_example_url,
			"body": body,
			"footer_text": footer_text,
			"buttons": buttons,
		})
		doc.insert(ignore_permissions=True)
		created += 1

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user-triggered sync action

	return {"created": created, "updated": updated, "total_fetched": len(remote_templates)}


@frappe.whitelist()
def get_selectable_contacts(search: str = None):
	"""Contacts eligible for starting a new chat: scoped to the customers
	assigned to the logged-in user's Sales Person record(s) (System
	Managers see all). Returns one row per Contact with its first known
	phone number and the Customer it's linked to."""
	customers = get_allowed_customers()
	if customers is not None and not customers:
		return []

	conditions = ["dl.parenttype = 'Contact'", "dl.link_doctype = 'Customer'"]
	values = {}
	if customers is not None:
		conditions.append("dl.link_name in %(customers)s")
		values["customers"] = tuple(customers)
	if search:
		conditions.append(
			"(c.first_name like %(search)s or c.last_name like %(search)s "
			"or dl.link_name like %(search)s or cp.phone like %(search)s)"
		)
		values["search"] = f"%{search}%"

	where = " and ".join(conditions)

	rows = frappe.db.sql(
		"""
		select c.name as contact_name,
			trim(concat_ws(' ', c.first_name, c.last_name)) as full_name,
			dl.link_name as customer,
			min(cp.phone) as phone
		from `tabDynamic Link` dl
		inner join `tabContact` c on c.name = dl.parent
		left join `tabContact Phone` cp on cp.parent = c.name
		where """ + where + """
		group by c.name, dl.link_name
		having phone is not null and phone != ''
		order by full_name
		limit 200
		""",
		values,
		as_dict=True,
	)

	return rows


@frappe.whitelist()
def test_provider_connection(provider: str):
	"""Verify saved credentials for the given provider ('Meta' or 'Twilio')
	actually work, without sending a real WhatsApp message."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Managers can test provider connections.", frappe.PermissionError)

	try:
		instance = get_provider(provider)
		details = instance.test_connection()
		return {"success": True, "details": details}
	except WhatsAppSendError as e:
		return {"success": False, "error": str(e)}
	except Exception as e:
		return {"success": False, "error": str(e)}


def _clean_param(value):
	"""GET requests from the frontend can serialize a missing/optional JS
	value as the literal string 'undefined' or 'null' instead of omitting
	it — treat those the same as not having been passed at all."""
	if value in (None, "", "undefined", "null"):
		return None
	return value


def _conversation_scope_where(search: str = None):
	"""Shared WHERE clause + params: customer permission scope, plus an
	optional search on conversation_id/profile_name. Used by both
	get_conversations and get_conversation_stats so the counts always
	match what the list actually shows."""
	search = _clean_param(search)
	customers = get_allowed_customers()
	conditions = ["conversation_id IS NOT NULL", "conversation_id != ''"]
	params = {}

	if customers is not None:
		if not customers:
			conditions.append("(customer IS NULL OR customer = '')")
		else:
			conditions.append("(customer IN %(customers)s OR customer IS NULL OR customer = '')")
			params["customers"] = tuple(customers)

	if search:
		conditions.append("(conversation_id LIKE %(search)s OR profile_name LIKE %(search)s)")
		params["search"] = f"%{search}%"

	return " AND ".join(conditions), params


@frappe.whitelist()
def get_conversations(limit: int = 100, offset: int = 0, search: str = None, filter: str = None):
	"""Latest message per conversation_id, newest first. Scoped to the
	logged-in user's assigned customers unless System Manager/Admin.
	filter: None/'all', 'unread', 'incoming', 'outgoing'."""
	limit = int(limit)
	offset = int(offset)
	filter = _clean_param(filter)

	where, params = _conversation_scope_where(search)

	rows = frappe.db.sql(
		"""
		SELECT m.*
		FROM `tabWhatsnext Message` m
		INNER JOIN (
			SELECT conversation_id, MAX(modified) AS latest
			FROM `tabWhatsnext Message`
			WHERE """ + where + """
			GROUP BY conversation_id
		) lm ON m.conversation_id = lm.conversation_id AND m.modified = lm.latest
		ORDER BY m.modified DESC
		""",
		params,
		as_dict=True,
	)

	unread_ids = set()
	if rows:
		conv_ids = tuple(r.conversation_id for r in rows)
		unread_rows = frappe.db.sql(
			"""
			SELECT DISTINCT conversation_id FROM `tabWhatsnext Message`
			WHERE type='Incoming' AND status='Delivered' AND conversation_id IN %(ids)s
			""",
			{"ids": conv_ids},
		)
		unread_ids = {r[0] for r in unread_rows}

	for r in rows:
		r["is_unread"] = r["conversation_id"] in unread_ids

	if filter == "unread":
		rows = [r for r in rows if r["is_unread"]]
	elif filter == "incoming":
		rows = [r for r in rows if r["type"] == "Incoming"]
	elif filter == "outgoing":
		rows = [r for r in rows if r["type"] == "Outgoing"]

	total = len(rows)
	page = rows[offset: offset + limit]

	return {
		"data": page,
		"total": total,
		"has_more": offset + limit < total,
	}


@frappe.whitelist()
def get_conversation_media(conversation_id: str):
	"""All messages in a conversation that carry an attachment, grouped by
	kind, for the Media & Files side panel."""
	customers = get_allowed_customers()
	if customers is not None:
		msg_customer = frappe.db.get_value(
			"Whatsnext Message", {"conversation_id": conversation_id}, "customer"
		)
		if msg_customer and msg_customer not in customers:
			frappe.throw("You are not permitted to view this conversation.", frappe.PermissionError)

	rows = frappe.get_all(
		"Whatsnext Message",
		filters={"conversation_id": conversation_id, "attach": ["is", "set"]},
		fields=["name", "content_type", "attach", "message", "creation", "type"],
		order_by="creation desc",
	)

	grouped = {"media": [], "docs": [], "audio": []}
	for r in rows:
		if r.content_type in ("image", "video"):
			grouped["media"].append(r)
		elif r.content_type == "audio":
			grouped["audio"].append(r)
		else:
			grouped["docs"].append(r)

	return grouped


@frappe.whitelist()
def get_conversation_stats():
	"""Counts for the Chats header bar, respecting the same customer
	permission scope as get_conversations (unfiltered by search)."""
	where, params = _conversation_scope_where()

	total = frappe.db.sql(
		"SELECT COUNT(DISTINCT conversation_id) FROM `tabWhatsnext Message` WHERE " + where, params
	)[0][0]
	unread = frappe.db.sql(
		"SELECT COUNT(DISTINCT conversation_id) FROM `tabWhatsnext Message` WHERE type='Incoming' AND status='Delivered' AND " + where,
		params,
	)[0][0]
	sent = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabWhatsnext Message` WHERE type='Outgoing' AND status IN ('Sent','Delivered','Read') AND " + where,
		params,
	)[0][0]

	return {"total": total, "unread": unread, "sent": sent}


@frappe.whitelist()
def get_messages(conversation_id: str, limit: int = 100, offset: int = 0):
	customers = get_allowed_customers()
	if customers is not None:
		msg_customer = frappe.db.get_value(
			"Whatsnext Message", {"conversation_id": conversation_id}, "customer"
		)
		if msg_customer and msg_customer not in customers:
			frappe.throw("You are not permitted to view this conversation.", frappe.PermissionError)

	return frappe.get_all(
		"Whatsnext Message",
		filters={"conversation_id": conversation_id},
		fields=MESSAGE_FIELDS,
		order_by="creation asc",
		limit_page_length=int(limit),
		limit_start=int(offset),
	)


@frappe.whitelist()
def mark_as_read(conversation_id: str):
	frappe.db.set_value(
		"Whatsnext Message",
		{"conversation_id": conversation_id, "type": "Incoming"},
		"status",
		"Read",
	)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action, needs to land immediately
	return {"ok": True}


def _create_message_record(**kwargs) -> "frappe.model.document.Document":
	if not kwargs.get("customer"):
		number = kwargs.get("to_number") or kwargs.get("from_number")
		kwargs["customer"] = resolve_customer_from_phone(number)
	doc = frappe.get_doc({"doctype": "Whatsnext Message", **kwargs})
	doc.insert(ignore_permissions=True)
	return doc


@frappe.whitelist()
def send_message(to: str, message: str, provider: str | None = None,
                  reference_doctype: str | None = None, reference_name: str | None = None):
	"""Send a free-form text message. Only valid inside a 24h customer service
	window per WhatsApp policy — use send_template_message outside that window."""
	to = normalize_outbound_number(to)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=message, message_type="Manual", content_type="text",
		reference_doctype=reference_doctype, reference_name=reference_name,
	)
	_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def send_media_message(to: str, media_url: str, media_type: str, caption: str = "",
                        provider: str | None = None,
                        reference_doctype: str | None = None, reference_name: str | None = None):
	"""Send a standalone image/video/document/audio message (composer
	attach button) — as opposed to a header image that's part of a
	Template send."""
	to = normalize_outbound_number(to)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=caption, message_type="Manual", content_type=media_type,
		attach=media_url, reference_doctype=reference_doctype, reference_name=reference_name,
	)
	_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def send_template_message(to: str, template: str, parameters: str | dict | None = None,
                           provider: str | None = None,
                           reference_doctype: str | None = None, reference_name: str | None = None,
                           header_media_url: str | None = None):
	to = normalize_outbound_number(to)
	tpl = frappe.get_doc("Whatsnext Message Template", template)
	if isinstance(parameters, str):
		parameters = json.loads(parameters) if parameters else {}
	parameters = parameters or {}

	if tpl.header_type not in (None, "None", "Text") and not header_media_url:
		frappe.throw(f"Template '{template}' has a {tpl.header_type} header — a header_media_url is required to send it.")

	# Mirror the header media on our own record too, not just the outbound
	# API payload — otherwise the chat UI has no way to show the image/
	# video/document that was actually part of the sent message.
	content_type = (tpl.header_type or "text").lower() if header_media_url else "text"

	msg = _create_message_record(
		type="Outgoing", provider=provider or tpl.provider if tpl.provider != "Both" else provider,
		status="Pending", to_number=to, message=tpl.body, message_type="Template",
		content_type=content_type, attach=header_media_url,
		template=template, template_parameters=json.dumps(parameters),
		reference_doctype=reference_doctype, reference_name=reference_name,
	)
	_dispatch(msg, template_doc=tpl, params=parameters, header_media_url=header_media_url)
	return msg.as_dict()


def _dispatch(msg, template_doc=None, params=None, header_media_url=None):
	"""Actually calls out to the provider and updates the message status.
	Kept small and defensive: failures are recorded on the doc, never raised
	back through the whitelisted endpoint as a 500 — the SPA reads status."""
	try:
		provider = get_provider(msg.provider)
		if msg.message_type == "Template" and template_doc:
			result = provider.send_template(
				msg.to_number, template_doc.name, params, template_doc.language,
				header_media_url=header_media_url, header_type=template_doc.header_type,
			)
		elif msg.content_type in ("image", "video", "document", "audio") and msg.attach:
			result = provider.send_media(msg.to_number, msg.attach, msg.content_type, msg.message or "")
		else:
			result = provider.send_text(msg.to_number, msg.message)

		provider_message_id = _extract_provider_message_id(provider.name, result)
		msg.db_set("status", "Sent", update_modified=False)
		msg.db_set("provider", provider.name, update_modified=False)
		if provider_message_id:
			msg.db_set("provider_message_id", provider_message_id, update_modified=False)
	except WhatsAppSendError as e:
		_mark_failed(msg, str(e))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext send failed: {msg.name}")
		_mark_failed(msg, str(e))


def _mark_failed(msg, error: str):
	try:
		msg.reload()
		msg.status = "Failed"
		msg.error_message = error[:140]
		msg.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- failure path must land even if caller rolls back
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext failure-handling itself failed: {msg.name}")
		frappe.db.set_value("Whatsnext Message", msg.name, "status", "Failed", update_modified=True)
		frappe.db.commit()

	settings = frappe.get_cached_doc("Whatsnext Settings")
	if settings.notify_on_failure and settings.failure_notification_email:
		frappe.sendmail(
			recipients=[settings.failure_notification_email],
			subject=f"Whatsnext: message to {msg.to_number} failed",
			message=f"Message {msg.name} to {msg.to_number} failed: {error}",
		)


def _extract_provider_message_id(provider_name, result):
	if provider_name == "Meta":
		msgs = result.get("messages") or []
		return msgs[0].get("id") if msgs else None
	if provider_name == "Twilio":
		return result.get("sid")
	return None


@frappe.whitelist()
def get_templates(provider: str | None = None, approved_only: bool = False):
	filters = {}
	if provider:
		filters["provider"] = ["in", [provider, "Both"]]
	if int(approved_only):
		filters["approval_status"] = "Approved"
	return frappe.get_all(
		"Whatsnext Message Template",
		filters=filters,
		fields=["name", "template_name", "provider", "language", "category", "approval_status", "body", "header_type", "header_text", "header_example_url", "footer_text", "twilio_content_sid", "meta_template_id"],
		order_by="modified desc",
	)


@frappe.whitelist()
def update_template_provider_ids(template: str, twilio_content_sid: str | None = None):
	"""Narrow, purpose-built endpoint (rather than exposing generic
	frappe.client.set_value for this) so we can validate the SID shape and
	keep the permission surface tight to just this one field."""
	if twilio_content_sid and not twilio_content_sid.startswith("HX"):
		frappe.throw("A Twilio Content SID normally starts with 'HX'. Double-check you copied the Content SID, not the Template SID.")
	frappe.db.set_value("Whatsnext Message Template", template, "twilio_content_sid", twilio_content_sid or "")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action from Templates UI
	return {"ok": True}


@frappe.whitelist()
def save_recipient_list(list_name: str, recipients: str | list, description: str | None = None):
	"""Creates or fully replaces a saved recipient list. recipients: list of
	{"contact_name": "...", "to_number": "...", "parameters": {...}}."""
	if isinstance(recipients, str):
		recipients = json.loads(recipients)

	rows = [
		{
			"contact_name": r.get("contact_name", ""),
			"to_number": r["to_number"],
			"parameters": json.dumps(r.get("parameters", {})),
		}
		for r in recipients
	]

	if frappe.db.exists("Whatsnext Recipient List", list_name):
		doc = frappe.get_doc("Whatsnext Recipient List", list_name)
		doc.description = description if description is not None else doc.description
		doc.recipients = []
		for row in rows:
			doc.append("recipients", row)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({
			"doctype": "Whatsnext Recipient List",
			"list_name": list_name,
			"description": description or "",
			"recipients": rows,
		})
		doc.insert(ignore_permissions=True)

	return doc.as_dict()


@frappe.whitelist()
def list_recipient_lists():
	return frappe.get_all(
		"Whatsnext Recipient List",
		fields=["name", "list_name", "description", "recipient_count", "modified"],
		order_by="modified desc",
	)


@frappe.whitelist()
def get_recipient_list(list_name: str):
	doc = frappe.get_doc("Whatsnext Recipient List", list_name)
	return {
		"name": doc.name,
		"list_name": doc.list_name,
		"description": doc.description,
		"recipients": [
			{
				"contact_name": r.contact_name,
				"to_number": r.to_number,
				"parameters": json.loads(r.parameters) if r.parameters else {},
			}
			for r in doc.recipients
		],
	}


@frappe.whitelist()
def delete_recipient_list(list_name: str):
	frappe.delete_doc("Whatsnext Recipient List", list_name, ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist()
def create_campaign(campaign_name: str, template: str, recipients: str | list, provider: str | None = None):
	"""recipients: list of {"to_number": "...", "parameters": {...}} dicts,
	or a JSON string of the same. Creates the Campaign in Draft and does NOT
	send — call start_campaign separately so the frontend can show a
	confirmation/preview step first."""
	if isinstance(recipients, str):
		recipients = json.loads(recipients)

	if not recipients:
		frappe.throw("At least one recipient is required.")

	phone_re = re.compile(r"^\+?\d{7,15}$")
	bad = [
		r["to_number"] for r in recipients
		if not phone_re.match(re.sub(r"[\s\-()]", "", r.get("to_number", "")))
	]
	if bad:
		frappe.throw(
			f"{len(bad)} recipient(s) have an invalid phone number (e.g. {bad[0]!r}). "
			"Check that names and phone numbers weren't swapped in the CSV."
		)

	doc = frappe.get_doc({
		"doctype": "Whatsnext Campaign",
		"campaign_name": campaign_name,
		"template": template,
		"provider": provider or None,
		"status": "Draft",
		"recipients": [
			{
				"to_number": r["to_number"],
				"parameters": json.dumps(r.get("parameters", {})),
				"status": "Pending",
			}
			for r in recipients
		],
	})
	doc.insert(ignore_permissions=True)
	return doc.as_dict()


@frappe.whitelist()
def start_campaign(campaign_name: str):
	from whatsnext.whatsnext.campaign_engine import start_campaign as _start

	frappe.db.set_value("Whatsnext Campaign", campaign_name, "status", "Queued")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action, needs to land before enqueue races the UI's next poll
	_start(campaign_name)
	return {"ok": True}


@frappe.whitelist()
def list_campaigns():
	return frappe.get_all(
		"Whatsnext Campaign",
		fields=["name", "campaign_name", "template", "status", "total_recipients", "sent_count", "delivered_count", "failed_count", "creation"],
		order_by="creation desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def get_campaign(campaign_name: str):
	doc = frappe.get_doc("Whatsnext Campaign", campaign_name)
	return {
		"name": doc.name,
		"campaign_name": doc.campaign_name,
		"template": doc.template,
		"status": doc.status,
		"total_recipients": doc.total_recipients,
		"sent_count": doc.sent_count,
		"delivered_count": doc.delivered_count,
		"failed_count": doc.failed_count,
		"recipients": [
			{"to_number": r.to_number, "status": r.status, "error_message": r.error_message}
			for r in doc.recipients
		],
	}


@frappe.whitelist()
def export_campaign_results(campaign_name: str, format: str = "xlsx"):
	"""Streams the campaign's recipient results as a file download.
	format: 'xlsx' or 'pdf'."""
	doc = frappe.get_doc("Whatsnext Campaign", campaign_name)

	headers = ["Phone Number", "Status", "Parameters", "Error", "Message"]
	rows = [headers]
	for r in doc.recipients:
		try:
			params = ", ".join(str(v) for v in json.loads(r.parameters or "{}").values())
		except Exception:
			params = r.parameters or ""
		rows.append([r.to_number, r.status, params, r.error_message or "", r.message or ""])

	safe_name = frappe.scrub(doc.campaign_name or doc.name)

	if format == "xlsx":
		from frappe.utils.xlsxutils import make_xlsx

		xlsx_file = make_xlsx(rows, "Campaign Results")
		frappe.local.response.filename = f"{safe_name}-results.xlsx"
		frappe.local.response.filecontent = xlsx_file.getvalue()
		frappe.local.response.type = "binary"
	elif format == "pdf":
		from frappe.utils.pdf import get_pdf

		html = frappe.render_template(
			"whatsnext/templates/campaign_results_pdf.html",
			{
				"campaign_name": doc.campaign_name,
				"template": doc.template,
				"status": doc.status,
				"total_recipients": doc.total_recipients,
				"sent_count": doc.sent_count,
				"failed_count": doc.failed_count,
				"rows": rows[1:],
			},
		)
		frappe.local.response.filename = f"{safe_name}-results.pdf"
		frappe.local.response.filecontent = get_pdf(html)
		frappe.local.response.type = "download"
	else:
		frappe.throw("format must be 'xlsx' or 'pdf'")


@frappe.whitelist()
def dashboard_stats():
	"""Powers the WhatsApp Hub dashboard: counts, delivery donut, weekly trend, top templates."""
	today = getdate()
	week_start = add_to_date(today, days=-6)

	counts = frappe.db.sql(
		"""
		SELECT status, COUNT(*) AS cnt
		FROM `tabWhatsnext Message`
		GROUP BY status
		""",
		as_dict=True,
	)
	status_counts = {row.status: row.cnt for row in counts}

	message_queue = frappe.db.count("Whatsnext Message", {"status": ["in", ["Pending", "Queued"]]})
	scheduled_jobs = frappe.db.count("Whatsnext Message", {"scheduled_time": ["is", "set"], "status": ["in", ["Pending", "Queued"]]})

	delivered = status_counts.get("Delivered", 0) + status_counts.get("Read", 0)
	failed = status_counts.get("Failed", 0)
	pending = status_counts.get("Pending", 0) + status_counts.get("Queued", 0)
	total_sent = sum(status_counts.values())
	delivered_pct = round((delivered / total_sent) * 100, 1) if total_sent else 0

	weekly = frappe.db.sql(
		"""
		SELECT DATE(creation) AS day,
			SUM(CASE WHEN type='Outgoing' THEN 1 ELSE 0 END) AS sent,
			SUM(CASE WHEN status IN ('Delivered','Read') THEN 1 ELSE 0 END) AS delivered
		FROM `tabWhatsnext Message`
		WHERE DATE(creation) BETWEEN %(start)s AND %(end)s
		GROUP BY DATE(creation)
		ORDER BY day ASC
		""",
		{"start": week_start, "end": today},
		as_dict=True,
	)

	top_templates = frappe.db.sql(
		"""
		SELECT template, COUNT(*) AS cnt
		FROM `tabWhatsnext Message`
		WHERE template IS NOT NULL AND template != ''
		GROUP BY template
		ORDER BY cnt DESC
		LIMIT 5
		""",
		as_dict=True,
	)

	recent = frappe.get_all(
		"Whatsnext Message",
		fields=["name", "to_number", "type", "status", "message", "template", "creation"],
		order_by="creation desc",
		limit_page_length=8,
	)

	return {
		"message_queue": message_queue,
		"sent_this_week": sum(r.sent for r in weekly) if weekly else 0,
		"failed_messages": failed,
		"scheduled_jobs": scheduled_jobs,
		"delivery_status": {
			"delivered": delivered,
			"pending": pending,
			"failed": failed,
			"delivered_pct": delivered_pct,
		},
		"weekly_overview": weekly,
		"top_templates": top_templates,
		"recent_messages": recent,
	}
