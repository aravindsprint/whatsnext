import json
from datetime import timedelta

import frappe
from frappe.utils import now_datetime, add_to_date, getdate

from whatsnext.whatsnext.provider_engine import get_provider, WhatsAppSendError

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


@frappe.whitelist()
def get_conversations(limit: int = 100, offset: int = 0):
	"""Latest message per conversation_id, paginated, newest first."""
	limit = int(limit)
	offset = int(offset)

	total = frappe.db.count("Whatsnext Message")

	rows = frappe.db.sql(
		"""
		SELECT m.*
		FROM `tabWhatsnext Message` m
		INNER JOIN (
			SELECT conversation_id, MAX(modified) AS latest
			FROM `tabWhatsnext Message`
			WHERE conversation_id IS NOT NULL AND conversation_id != ''
			GROUP BY conversation_id
			ORDER BY latest DESC
			LIMIT %(limit)s OFFSET %(offset)s
		) latest_msgs
		ON m.conversation_id = latest_msgs.conversation_id AND m.modified = latest_msgs.latest
		ORDER BY m.modified DESC
		""",
		{"limit": limit, "offset": offset},
		as_dict=True,
	)

	distinct_total = frappe.db.sql(
		"SELECT COUNT(DISTINCT conversation_id) FROM `tabWhatsnext Message` WHERE conversation_id IS NOT NULL AND conversation_id != ''"
	)[0][0]

	return {
		"data": rows,
		"total": distinct_total,
		"has_more": offset + limit < distinct_total,
	}


@frappe.whitelist()
def get_messages(conversation_id: str, limit: int = 100, offset: int = 0):
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
	doc = frappe.get_doc({"doctype": "Whatsnext Message", **kwargs})
	doc.insert(ignore_permissions=True)
	return doc


@frappe.whitelist()
def send_message(to: str, message: str, provider: str | None = None,
                  reference_doctype: str | None = None, reference_name: str | None = None):
	"""Send a free-form text message. Only valid inside a 24h customer service
	window per WhatsApp policy — use send_template_message outside that window."""
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=message, message_type="Manual", content_type="text",
		reference_doctype=reference_doctype, reference_name=reference_name,
	)
	_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def send_template_message(to: str, template: str, parameters: str | dict | None = None,
                           provider: str | None = None,
                           reference_doctype: str | None = None, reference_name: str | None = None):
	tpl = frappe.get_doc("Whatsnext Message Template", template)
	if isinstance(parameters, str):
		parameters = json.loads(parameters) if parameters else {}
	parameters = parameters or {}

	msg = _create_message_record(
		type="Outgoing", provider=provider or tpl.provider if tpl.provider != "Both" else provider,
		status="Pending", to_number=to, message=tpl.body, message_type="Template",
		content_type="text", template=template, template_parameters=json.dumps(parameters),
		reference_doctype=reference_doctype, reference_name=reference_name,
	)
	_dispatch(msg, template_doc=tpl, params=parameters)
	return msg.as_dict()


def _dispatch(msg, template_doc=None, params=None):
	"""Actually calls out to the provider and updates the message status.
	Kept small and defensive: failures are recorded on the doc, never raised
	back through the whitelisted endpoint as a 500 — the SPA reads status."""
	try:
		provider = get_provider(msg.provider)
		if msg.message_type == "Template" and template_doc:
			result = provider.send_template(msg.to_number, template_doc.name, params, template_doc.language)
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
		fields=["name", "template_name", "provider", "language", "category", "approval_status", "body", "header_type", "header_text", "footer_text", "twilio_content_sid", "meta_template_id"],
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
