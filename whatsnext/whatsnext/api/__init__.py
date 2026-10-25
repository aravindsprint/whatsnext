import json
import re
from datetime import timedelta

import frappe
from frappe.utils import now_datetime, add_to_date, getdate

from whatsnext.whatsnext.provider_engine import get_provider, WhatsAppSendError, MetaProvider, meta_template_name
from whatsnext.whatsnext.contacts import resolve_customer_from_phone, normalize_outbound_number
from whatsnext.whatsnext.permissions import get_allowed_customers
from whatsnext.whatsnext.permissions import is_app_user, require_app_user as _require_app_user

MESSAGE_FIELDS = [
	"name", "type", "provider", "status", "to_number", "from_number", "profile_name",
	"message", "message_type", "content_type", "attach", "template", "template_parameters",
	"reference_doctype", "reference_name", "conversation_id", "provider_message_id",
	"error_message", "scheduled_time", "creation", "modified", "reply_to", "is_automated", "payload", "owner",
]


@frappe.whitelist(allow_guest=True)
def get_csrf_token():
	"""Guest-accessible so the SPA shell can bootstrap a CSRF token before login."""
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def whoami():
	"""Session info plus the app configuration the SPA needs: which
	providers can be picked per message, and who chats can be assigned to."""
	roles = frappe.get_roles(frappe.session.user)
	settings = frappe.get_cached_doc("Whatsnext Settings")
	providers = [p for p, on in (("Meta", settings.meta_enabled), ("Twilio", settings.twilio_enabled)) if on]

	has_access = is_app_user()
	# The staff list is only for people who can assign chats; anyone else
	# logged in (e.g. a portal customer) used to receive it too.
	agent_ids = set() if not has_access else set(frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", ["Whatsnext User", "System Manager"]]},
		pluck="parent",
		distinct=True,
	)) - {"Administrator", "Guest"}
	agents = frappe.get_all(
		"User",
		filters={"name": ["in", list(agent_ids)], "enabled": 1, "user_type": "System User"},
		fields=["name", "full_name"],
		order_by="full_name asc",
	) if agent_ids else []

	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"roles": roles,
		"is_system_manager": "System Manager" in roles,
		"has_access": has_access,
		"providers": providers,
		"default_provider": settings.default_provider,
		"opt_out_enabled": bool(settings.opt_out_enabled),
		"agents": agents,
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
	_require_app_user()
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Managers can sync templates.", frappe.PermissionError)

	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.meta_enabled:
		frappe.throw("Meta WhatsApp Cloud API is not enabled in Whatsnext Settings.")

	remote_templates = MetaProvider(settings).fetch_templates()

	created, updated, errors = 0, 0, []

	for t in remote_templates:
		# One bad template (e.g. an unexpected format) used to abort the
		# whole sync, leaving every later template unsynced.
		try:
			result = _sync_one_meta_template(t)
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Whatsnext: couldn't sync Meta template {t.get('name')}")
			errors.append(f"{t.get('name')} ({t.get('language')}): {e}")
			continue
		if result == "created":
			created += 1
		else:
			updated += 1
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user-triggered sync; keep each template that succeeded

	return {"created": created, "updated": updated, "total_fetched": len(remote_templates), "errors": errors}


def is_meta_hosted_url(url) -> bool:
	"""True for an empty value or a link Meta hosts (template sample media
	on scontent.whatsapp.net / fbcdn), which expires after about a month."""
	if not url:
		return True
	from urllib.parse import urlparse

	host = (urlparse(url).hostname or "").lower()
	return host.endswith("whatsapp.net") or host.endswith("fbcdn.net")


def meta_header_sample_url(t) -> str:
	"""The header sample media link from a template as Meta returns it."""
	for comp in t.get("components", []):
		if (comp.get("type") or "").upper() == "HEADER" and (comp.get("format") or "").upper() in ("IMAGE", "VIDEO", "DOCUMENT"):
			handles = comp.get("example", {}).get("header_handle", [])
			return handles[0] if handles else ""
	return ""


def _sync_one_meta_template(t):
	meta_id = t.get("id")
	name = t.get("name")
	language = t.get("language")

	existing = frappe.db.get_value("Whatsnext Message Template", {"meta_template_id": meta_id}, "name")
	if not existing:
		existing = frappe.db.get_value(
			"Whatsnext Message Template", {"meta_name": name, "language": language}, "name"
		) or frappe.db.get_value(
			"Whatsnext Message Template", {"template_name": name, "language": language}, "name"
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
			# Only these exist as Header Type options; anything else
			# (e.g. LOCATION headers) failed Select validation and
			# aborted the whole sync on that one template.
			if header_type not in ("Text", "Image", "Document", "Video"):
				header_type = "None"
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
		doc.meta_name = name
		# Meta's sample link is temporary; refresh it, but keep a permanent
		# link someone entered on the template themselves.
		if header_example_url and is_meta_hosted_url(doc.header_example_url):
			doc.header_example_url = header_example_url
		doc.save(ignore_permissions=True)
		return "updated"

	# Template names are unique here, but Meta keys templates by name AND
	# language — the same template in English and Tamil is two templates.
	# The second language used to fail the insert (and abort the sync); it
	# now gets a language-suffixed local name, and meta_name keeps the real
	# name for sending.
	local_name = name
	if frappe.db.exists("Whatsnext Message Template", local_name):
		local_name = f"{name}_{language}"

	doc = frappe.get_doc({
		"doctype": "Whatsnext Message Template",
		"template_name": local_name,
		"meta_name": name,
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
	return "created"


@frappe.whitelist()
def get_selectable_contacts(search: str = None):
	"""Contacts eligible for starting a new chat: scoped to the customers
	assigned to the logged-in user's Sales Person record(s) (System
	Managers see all). Returns one row per Contact with its first known
	phone number and the Customer it's linked to."""
	_require_app_user()
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
	_require_app_user()
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


CONVERSATION_FILTERS = ("all", "unread", "mine", "closed", "incoming", "outgoing")


def build_conversation_where(customers, search=None, filter=None, user=None):
	"""WHERE clause + params over `tabWhatsnext Conversation` (one row per
	chat, indexed) for the chat list and its header counts.

	customers: get_allowed_customers() result — None means unrestricted.
	filter: all/unread/mine/incoming/outgoing hide Closed chats; closed
	shows only those. None skips the open/closed condition entirely (used
	for the header totals)."""
	conditions = []
	params = {}

	if customers is not None:
		if not customers:
			conditions.append("(customer IS NULL OR customer = '')")
		else:
			conditions.append("(customer IN %(customers)s OR customer IS NULL OR customer = '')")
			params["customers"] = tuple(customers)

	if search:
		conditions.append("(name LIKE %(search)s OR profile_name LIKE %(search)s)")
		params["search"] = f"%{search}%"

	if filter is not None:
		filter = filter or "all"
		if filter not in CONVERSATION_FILTERS:
			frappe.throw(f"Unknown filter '{filter}'.")
		if filter == "closed":
			conditions.append("status = 'Closed'")
		else:
			conditions.append("(status IS NULL OR status != 'Closed')")
		if filter == "unread":
			conditions.append("unread_count > 0")
		elif filter == "mine":
			conditions.append("assigned_to = %(user)s")
			params["user"] = user
		elif filter == "incoming":
			conditions.append("last_message_type = 'Incoming'")
		elif filter == "outgoing":
			conditions.append("last_message_type = 'Outgoing'")

	return (" AND ".join(conditions) or "1=1"), params


@frappe.whitelist()
def get_conversations(limit: int = 50, offset: int = 0, search: str = None, filter: str = None):
	"""Chat list, newest activity first, one page at a time. Reads only
	the Whatsnext Conversation table (kept up to date by
	conversations.touch_conversation), so the cost doesn't grow with message
	history. Scoped to the user's assigned customers unless System Manager.
	filter: all/unread/mine/closed/incoming/outgoing."""
	_require_app_user()
	limit = max(1, min(int(limit), 200))
	offset = max(0, int(offset))
	where, params = build_conversation_where(
		get_allowed_customers(), _clean_param(search), _clean_param(filter) or "all", frappe.session.user,
	)

	total = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabWhatsnext Conversation` WHERE " + where, params
	)[0][0]
	rows = frappe.db.sql(
		"""
		SELECT name AS conversation_id, profile_name, customer, contact, status AS conversation_status,
			assigned_to, last_message_at, last_message, last_message_type, last_message_name,
			last_incoming_at, unread_count
		FROM `tabWhatsnext Conversation`
		WHERE """ + where + """
		ORDER BY last_message_at DESC, name DESC
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		{**params, "limit": limit, "offset": offset},
		as_dict=True,
	)

	from whatsnext.whatsnext.conversations import SERVICE_WINDOW_HOURS

	window_cutoff = add_to_date(now_datetime(), hours=-SERVICE_WINDOW_HOURS)
	for r in rows:
		# Field names the chat UI already uses for a list row.
		r["name"] = r.last_message_name or r.conversation_id
		r["message"] = r.last_message
		r["type"] = r.last_message_type
		r["modified"] = r.last_message_at
		r["is_unread"] = bool(r.unread_count)
		r["window_open"] = bool(r.last_incoming_at and r.last_incoming_at > window_cutoff)

	return {
		"data": rows,
		"total": total,
		"has_more": offset + len(rows) < total,
	}


def _assert_conversation_access(conversation_id: str):
	"""Same visibility rule as the chat list: a restricted user may open a
	conversation only if every customer it's linked to is theirs (or it's
	unassigned). Checking just one arbitrary message's customer let a
	conversation slip through when its messages were linked to different
	customers."""
	customers = get_allowed_customers()
	if customers is None:
		return
	linked = frappe.get_all(
		"Whatsnext Message",
		filters={"conversation_id": conversation_id, "customer": ["is", "set"]},
		pluck="customer",
		distinct=True,
	)
	if any(c not in customers for c in linked):
		frappe.throw("You are not permitted to view this conversation.", frappe.PermissionError)


@frappe.whitelist()
def get_conversation_media(conversation_id: str):
	"""All messages in a conversation that carry an attachment, grouped by
	kind, for the Media & Files side panel."""
	_require_app_user()
	_assert_conversation_access(conversation_id)

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
	"""Counts for the Chats header bar, with the same customer scope as the
	list — from the conversation table, not a scan of every message."""
	_require_app_user()
	where, params = build_conversation_where(get_allowed_customers())
	total, unread, sent = frappe.db.sql(
		"""SELECT COUNT(*),
			COALESCE(SUM(CASE WHEN unread_count > 0 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(outgoing_count), 0)
		FROM `tabWhatsnext Conversation` WHERE """ + where,
		params,
	)[0]
	return {"total": int(total or 0), "unread": int(unread or 0), "sent": int(sent or 0)}


@frappe.whitelist()
def get_messages(conversation_id: str, limit: int = 100, offset: int = 0):
	_require_app_user()
	_assert_conversation_access(conversation_id)

	# Newest `limit` messages, returned oldest-first for display. Ordering
	# ascending with a limit returned the *oldest* 200 messages, so in any
	# long-running chat new messages (including the one just sent or
	# received) never appeared.
	rows = frappe.get_all(
		"Whatsnext Message",
		filters={"conversation_id": conversation_id},
		# Scheduled messages that haven't gone out yet aren't part of the
		# timeline (they're listed in get_conversation_info instead).
		or_filters={"scheduled_time": ["is", "not set"], "status": ["!=", "Pending"]},
		fields=MESSAGE_FIELDS,
		order_by="creation desc, name desc",
		limit_page_length=int(limit),
		limit_start=int(offset),
	)
	rows.reverse()
	_attach_reply_previews(rows)
	return rows


def _attach_reply_previews(rows):
	"""Each reply carries a short preview of the message it quotes."""
	ids = list({r.reply_to for r in rows if r.get("reply_to")})
	if not ids:
		return
	quoted = {
		q.name: q for q in frappe.get_all(
			"Whatsnext Message",
			filters={"name": ["in", ids]},
			fields=["name", "type", "message", "content_type", "template", "profile_name"],
		)
	}
	for r in rows:
		q = quoted.get(r.get("reply_to"))
		if q:
			r["reply_preview"] = {
				"name": q.name,
				"type": q.type,
				"text": (q.message or ("📋 " + q.template if q.template else f"[{q.content_type}]"))[:160],
				"author": q.profile_name if q.type == "Incoming" else "You",
			}


@frappe.whitelist()
def mark_as_read(conversation_id: str):
	_require_app_user()
	_assert_conversation_access(conversation_id)
	# Blue ticks for the customer: one receipt for the newest unread Meta
	# message marks everything before it as read too.
	latest_unread = frappe.db.get_value(
		"Whatsnext Message",
		{"conversation_id": conversation_id, "type": "Incoming", "status": "Delivered", "provider": "Meta"},
		"provider_message_id",
		order_by="creation desc",
	)
	if latest_unread and frappe.get_cached_doc("Whatsnext Settings").send_read_receipts:
		frappe.enqueue(
			"whatsnext.whatsnext.conversations.send_read_receipt",
			queue="short",
			enqueue_after_commit=True,
			message_id=latest_unread,
		)

	from whatsnext.whatsnext.conversations import mark_conversation_read

	if frappe.db.exists("Whatsnext Conversation", conversation_id):
		mark_conversation_read(conversation_id)

	# Only unread (Delivered) messages: re-stamping every incoming message in
	# the thread bumped their `modified` on each open for no reason.
	frappe.db.set_value(
		"Whatsnext Message",
		{"conversation_id": conversation_id, "type": "Incoming", "status": "Delivered"},
		"status",
		"Read",
	)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action, needs to land immediately
	return {"ok": True}


@frappe.whitelist()
def get_conversation_info(conversation_id: str):
	"""Everything the chat header/side panel needs about one thread."""
	_require_app_user()
	_assert_conversation_access(conversation_id)
	from whatsnext.whatsnext.conversations import is_opted_out, window_expires_at

	conv = frappe.db.get_value(
		"Whatsnext Conversation", conversation_id,
		["status", "assigned_to", "customer", "contact", "profile_name", "last_incoming_at"],
		as_dict=True,
	) or frappe._dict(status="Open")
	expires = window_expires_at(conversation_id)
	return {
		"conversation_id": conversation_id,
		"status": conv.status or "Open",
		"assigned_to": conv.assigned_to,
		"assigned_to_name": frappe.utils.get_fullname(conv.assigned_to) if conv.assigned_to else None,
		"customer": conv.customer,
		"contact": conv.contact,
		"lead": frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": conv.contact, "link_doctype": "Lead"},
			"link_name",
		) if conv.contact else None,
		"profile_name": conv.profile_name,
		"window_expires_at": expires,
		"window_open": bool(expires and expires > now_datetime()),
		"opted_out": is_opted_out(conversation_id),
		"scheduled": frappe.get_all(
			"Whatsnext Message",
			filters={"conversation_id": conversation_id, "status": "Pending", "scheduled_time": ["is", "set"]},
			fields=["name", "message", "template", "scheduled_time"],
			order_by="scheduled_time asc",
		),
	}


def _ensure_conversation(conversation_id: str):
	if not frappe.db.exists("Whatsnext Conversation", conversation_id):
		frappe.get_doc({
			"doctype": "Whatsnext Conversation",
			"conversation_id": conversation_id,
			"status": "Open",
		}).insert(ignore_permissions=True)


@frappe.whitelist()
def assign_conversation(conversation_id: str, user: str | None = None):
	_require_app_user()
	_assert_conversation_access(conversation_id)
	user = _clean_param(user)
	if user and not frappe.db.exists("User", {"name": user, "enabled": 1}):
		frappe.throw(f"User {user} not found.")
	_ensure_conversation(conversation_id)
	frappe.db.set_value("Whatsnext Conversation", conversation_id, "assigned_to", user or None)
	return get_conversation_info(conversation_id)


@frappe.whitelist()
def set_conversation_status(conversation_id: str, status: str):
	_require_app_user()
	_assert_conversation_access(conversation_id)
	if status not in ("Open", "Closed"):
		frappe.throw("Status must be Open or Closed.")
	_ensure_conversation(conversation_id)
	frappe.db.set_value("Whatsnext Conversation", conversation_id, "status", status)
	return get_conversation_info(conversation_id)


@frappe.whitelist()
def set_opt_out(conversation_id: str, opted_out: int | bool):
	"""Manually opt a number out of (or back into) Marketing messages."""
	_require_app_user()
	_assert_conversation_access(conversation_id)
	from whatsnext.whatsnext.conversations import set_opt_out as _set

	_set(conversation_id, bool(int(opted_out)), "Manual")
	return get_conversation_info(conversation_id)


def _create_message_record(**kwargs) -> "frappe.model.document.Document":
	if not kwargs.get("customer"):
		number = kwargs.get("to_number") or kwargs.get("from_number")
		kwargs["customer"] = resolve_customer_from_phone(number)
	doc = frappe.get_doc({"doctype": "Whatsnext Message", **kwargs})
	doc.insert(ignore_permissions=True)
	return doc


def _resolve_provider(provider: str | None) -> str | None:
	"""Per-message provider choice. Empty means "use the default"; a named
	provider must be enabled, so a stale UI choice fails clearly up front."""
	provider = _clean_param(provider)
	if not provider:
		return None
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if provider == "Meta" and not settings.meta_enabled:
		frappe.throw("Meta Cloud API is not enabled in Whatsnext Settings.")
	if provider == "Twilio" and not settings.twilio_enabled:
		frappe.throw("Twilio is not enabled in Whatsnext Settings.")
	if provider not in ("Meta", "Twilio"):
		frappe.throw(f"Unknown provider '{provider}'.")
	return provider


def _parse_schedule(scheduled_time):
	"""Returns a future datetime, or None to send now."""
	from frappe.utils import get_datetime

	scheduled_time = _clean_param(scheduled_time)
	if not scheduled_time:
		return None
	when = get_datetime(scheduled_time)
	if when <= now_datetime():
		return None
	return when


def _assert_window_open(to: str, when=None):
	"""WhatsApp only allows free-form (non-template) messages within 24 hours
	of the customer's last message. Fail with a clear explanation instead of
	letting the provider reject it with a cryptic error."""
	from whatsnext.whatsnext.conversations import window_expires_at

	expires = window_expires_at(to)
	at = when or now_datetime()
	if not expires or expires <= at:
		if when:
			frappe.throw(
				"The 24-hour reply window will be closed at that time, so only a template can be sent then.",
				title="Outside the 24-hour window",
			)
		frappe.throw(
			"This customer hasn't messaged you in the last 24 hours, so WhatsApp only allows an approved "
			"template message. Use the template button to send one.",
			title="Outside the 24-hour window",
		)


def _render_body(body: str, params: dict) -> str:
	"""Show the message as the customer received it, with {{n}} filled in."""
	def sub(m):
		value = params.get(m.group(1), params.get(int(m.group(1)) if m.group(1).isdigit() else m.group(1)))
		return str(value) if value not in (None, "") else m.group(0)

	return re.sub(r"\{\{(\d+)\}\}", sub, body or "")


@frappe.whitelist()
def send_message(to: str, message: str, provider: str | None = None,
                  reference_doctype: str | None = None, reference_name: str | None = None,
                  scheduled_time: str | None = None, reply_to: str | None = None,
                  automated: int | bool = 0):
	"""Send a free-form text message. Only valid inside a 24h customer service
	window per WhatsApp policy — use send_template_message outside that window.
	With a future scheduled_time the message is queued for the scheduler."""
	_require_app_user()
	to = normalize_outbound_number(to)
	provider = _resolve_provider(provider)
	when = _parse_schedule(scheduled_time)
	_assert_window_open(to, when)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=message, message_type="Manual", content_type="text",
		reference_doctype=_clean_param(reference_doctype), reference_name=_clean_param(reference_name),
		scheduled_time=when, reply_to=_clean_reply_to(reply_to, to), is_automated=1 if int(automated or 0) else 0,
	)
	if not when:
		_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def send_media_message(to: str, media_url: str, media_type: str, caption: str = "",
                        provider: str | None = None,
                        reference_doctype: str | None = None, reference_name: str | None = None,
                        scheduled_time: str | None = None, reply_to: str | None = None):
	"""Send a standalone image/video/document/audio message (composer
	attach button) — as opposed to a header image that's part of a
	Template send."""
	_require_app_user()
	to = normalize_outbound_number(to)
	provider = _resolve_provider(provider)
	when = _parse_schedule(scheduled_time)
	_assert_window_open(to, when)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=caption, message_type="Manual", content_type=media_type,
		attach=media_url, reference_doctype=_clean_param(reference_doctype),
		reference_name=_clean_param(reference_name), scheduled_time=when,
		reply_to=_clean_reply_to(reply_to, to),
	)
	if not when:
		_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def send_template_message(to: str, template: str, parameters: str | dict | None = None,
                           provider: str | None = None,
                           reference_doctype: str | None = None, reference_name: str | None = None,
                           header_media_url: str | None = None, scheduled_time: str | None = None,
                           attach_print: int | bool = 0, print_format: str | None = None,
                           reply_to: str | None = None, automated: int | bool = 0):
	"""attach_print: render the referenced document's print format as a PDF
	and send it as the Document header (used by the Desk WhatsApp button)."""
	_require_app_user()
	to = normalize_outbound_number(to)
	tpl = frappe.get_doc("Whatsnext Message Template", template)
	if isinstance(parameters, str):
		parameters = json.loads(parameters) if parameters else {}
	parameters = parameters or {}
	header_media_url = _clean_param(header_media_url)

	if int(attach_print or 0):
		reference_doctype = _clean_param(reference_doctype)
		reference_name = _clean_param(reference_name)
		if not (reference_doctype and reference_name):
			frappe.throw("Attaching a print needs the document it belongs to.")
		if tpl.header_type != "Document":
			frappe.throw(f"Template '{template}' doesn't have a Document header, so a PDF can't be attached.")
		ref = frappe.get_doc(reference_doctype, reference_name)
		ref.check_permission("print")
		from whatsnext.whatsnext.notification_engine import _attach_document_pdf

		header_media_url = _attach_document_pdf(frappe._dict(print_format=_clean_param(print_format)), ref)

	if tpl.header_type not in (None, "", "None", "Text") and not header_media_url:
		frappe.throw(f"Template '{template}' has a {tpl.header_type} header — a header_media_url is required to send it.")

	from whatsnext.whatsnext.conversations import is_opted_out

	if tpl.category == "Marketing" and is_opted_out(to):
		frappe.throw(
			f"{to} has opted out of promotional messages, so Marketing templates can't be sent to them.",
			title="Opted out",
		)

	provider = _resolve_provider(provider) or (tpl.provider if tpl.provider in ("Meta", "Twilio") else None)
	when = _parse_schedule(scheduled_time)

	# Mirror the header media on our own record too, not just the outbound
	# API payload — otherwise the chat UI has no way to show the image/
	# video/document that was actually part of the sent message.
	content_type = (tpl.header_type or "text").lower() if header_media_url else "text"

	msg = _create_message_record(
		type="Outgoing", provider=provider,
		status="Pending", to_number=to, message=_render_body(tpl.body, parameters), message_type="Template",
		content_type=content_type, attach=header_media_url,
		template=template, template_parameters=json.dumps(parameters, default=str),
		reference_doctype=_clean_param(reference_doctype), reference_name=_clean_param(reference_name),
		scheduled_time=when, reply_to=_clean_reply_to(reply_to, to),
		is_automated=1 if int(automated or 0) else 0,
	)
	if not when:
		_dispatch(msg, template_doc=tpl, params=parameters, header_media_url=header_media_url)
	return msg.as_dict()


@frappe.whitelist()
def send_location(to: str, latitude: float, longitude: float, name: str | None = None,
                  address: str | None = None, provider: str | None = None, reply_to: str | None = None):
	"""Share a map pin (free-form, so only inside the 24-hour window)."""
	_require_app_user()
	to = normalize_outbound_number(to)
	provider = _resolve_provider(provider)
	try:
		lat, lng = float(latitude), float(longitude)
	except (TypeError, ValueError):
		frappe.throw("Latitude and longitude must be numbers.")
	if not (-90 <= lat <= 90 and -180 <= lng <= 180):
		frappe.throw("That isn't a valid map position.")
	_assert_window_open(to)
	name, address = _clean_param(name) or "", _clean_param(address) or ""
	label = " — ".join(x for x in (name, address) if x)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=f"📍 {label + ' ' if label else ''}https://maps.google.com/?q={lat},{lng}",
		message_type="Manual", content_type="location",
		payload=json.dumps({"latitude": lat, "longitude": lng, "name": name, "address": address}),
		reply_to=_clean_reply_to(reply_to, to),
	)
	_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def search_contact_cards(search: str | None = None):
	"""ERPNext Contacts the user may read, for sharing as a contact card."""
	_require_app_user()
	search = _clean_param(search)
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = [["full_name", "like", like], ["mobile_no", "like", like], ["phone", "like", like], ["company_name", "like", like]]
	return frappe.get_list(
		"Contact",
		or_filters=or_filters,
		fields=["name", "full_name", "mobile_no", "phone", "email_id", "company_name"],
		order_by="modified desc",
		limit_page_length=20,
	)


@frappe.whitelist()
def send_contact_card(to: str, contact: str | None = None, name: str | None = None, phone: str | None = None,
                      provider: str | None = None, reply_to: str | None = None):
	"""Share a contact card — an ERPNext Contact, or a name + number."""
	_require_app_user()
	to = normalize_outbound_number(to)
	provider = _resolve_provider(provider)
	contact = _clean_param(contact)
	if contact:
		doc = frappe.get_doc("Contact", contact)
		doc.check_permission("read")
		card = {
			"name": doc.full_name or " ".join(x for x in (doc.first_name, doc.last_name) if x) or doc.name,
			"phones": [p.phone for p in doc.phone_nos] or [x for x in (doc.mobile_no, doc.phone) if x],
			"emails": [e.email_id for e in doc.email_ids] or ([doc.email_id] if doc.email_id else []),
			"company": doc.company_name,
		}
	else:
		if not (_clean_param(name) and _clean_param(phone)):
			frappe.throw("Choose a contact, or enter a name and a phone number.")
		card = {"name": name.strip(), "phones": [phone.strip()], "emails": [], "company": None}
	if not card["phones"]:
		frappe.throw(f"{card['name']} has no phone number to share.")
	_assert_window_open(to)
	msg = _create_message_record(
		type="Outgoing", provider=provider, status="Pending", to_number=to,
		message=f"👤 Contact: {card['name']} {', '.join(card['phones'])}",
		message_type="Manual", content_type="contacts",
		payload=json.dumps({"contacts": [card]}),
		reply_to=_clean_reply_to(reply_to, to),
	)
	_dispatch(msg)
	return msg.as_dict()


@frappe.whitelist()
def cancel_scheduled_message(name: str):
	_require_app_user()
	msg = frappe.get_doc("Whatsnext Message", name)
	msg.check_permission("write")
	if msg.status != "Pending" or not msg.scheduled_time:
		frappe.throw("Only scheduled messages that haven't been sent yet can be cancelled.")
	frappe.delete_doc("Whatsnext Message", name, ignore_permissions=True)
	return {"ok": True}


def _dispatch(msg, template_doc=None, params=None, header_media_url=None):
	"""Actually calls out to the provider and updates the message status.
	Kept small and defensive: failures are recorded on the doc, never raised
	back through the whitelisted endpoint as a 500 — the SPA reads status."""
	try:
		provider = get_provider(msg.provider)
		context_id = _reply_context_id(msg)
		payload = _load_json(msg.get("payload"))
		if msg.message_type == "Template" and template_doc:
			result = provider.send_template(
				msg.to_number, template_doc.name, params, template_doc.language,
				header_media_url=header_media_url, header_type=template_doc.header_type,
				context_id=context_id,
			)
		elif msg.content_type == "location" and payload:
			result = provider.send_location(
				msg.to_number, payload.get("latitude"), payload.get("longitude"),
				payload.get("name") or "", payload.get("address") or "", context_id=context_id,
			)
		elif msg.content_type == "contacts" and payload:
			result = provider.send_contacts(msg.to_number, payload.get("contacts") or [], context_id=context_id)
		elif msg.content_type in ("image", "video", "document", "audio") and msg.attach:
			result = provider.send_media(msg.to_number, msg.attach, msg.content_type, msg.message or "", context_id=context_id)
		else:
			result = provider.send_text(msg.to_number, msg.message, context_id=context_id)

		provider_message_id = _extract_provider_message_id(provider.name, result)
		msg.db_set("status", "Sent", update_modified=False)
		msg.db_set("provider", provider.name, update_modified=False)
		if provider_message_id:
			msg.db_set("provider_message_id", provider_message_id, update_modified=False)
			# The message is out; save the id now so delivery webhooks can find
			# it, then apply any receipt that already arrived before it could.
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- provider already sent it; receipts must be able to match it
			from whatsnext.whatsnext.api.webhook import apply_early_statuses

			apply_early_statuses(provider_message_id)
	except WhatsAppSendError as e:
		_mark_failed(msg, str(e))
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext send failed: {msg.name}")
		_mark_failed(msg, str(e))


def _load_json(value):
	if not value:
		return {}
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except Exception:
		return {}


def _reply_context_id(msg):
	if not msg.get("reply_to"):
		return None
	return frappe.db.get_value("Whatsnext Message", msg.reply_to, "provider_message_id")


def _clean_reply_to(reply_to, conversation_id):
	"""A reply must quote a message from the same chat."""
	reply_to = _clean_param(reply_to)
	if not reply_to:
		return None
	if frappe.db.get_value("Whatsnext Message", reply_to, "conversation_id") != conversation_id:
		frappe.throw("You can only reply to a message from this conversation.")
	return reply_to


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

	from whatsnext.whatsnext.conversations import record_outgoing_failed

	record_outgoing_failed(msg.conversation_id)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- same failure path as above

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
def get_message_log(status: str | None = None, limit: int = 200, offset: int = 0):
	"""Every message (not just the latest per conversation), newest first,
	for the Message Logs page. Uses get_list so the doctype's permission
	query conditions apply the same customer scoping as the chat list."""
	_require_app_user()
	status = _clean_param(status)
	filters = {}
	if status and status != "All":
		filters["status"] = status
	return frappe.get_list(
		"Whatsnext Message",
		filters=filters,
		fields=MESSAGE_FIELDS,
		order_by="creation desc",
		limit_page_length=int(limit),
		limit_start=int(offset),
	)


@frappe.whitelist()
def get_templates(provider: str | None = None, approved_only: bool = False):
	_require_app_user()
	filters = {}
	provider = _clean_param(provider)
	if provider:
		filters["provider"] = ["in", [provider, "Both"]]
	or_filters = None
	if int(approved_only or 0):
		# "Sendable": approved by Meta, or set up for Twilio (Twilio
		# templates are approved in Twilio's console and never get a Meta
		# status here, so filtering on approval_status alone hid every
		# Twilio-only template from the chat, New Chat and Desk pickers).
		or_filters = [
			["approval_status", "=", "Approved"],
			["twilio_content_sid", "like", "HX%"],
		]
	templates = frappe.get_all(
		"Whatsnext Message Template",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "template_name", "meta_name", "provider", "language", "category", "approval_status", "rejection_reason", "body", "header_type", "header_text", "header_example_url", "footer_text", "twilio_content_sid", "meta_template_id", "variables_sample"],
		order_by="modified desc",
	)
	# Buttons are needed to ask for dynamic URL suffixes ({{1}}) at send time.
	if templates:
		buttons = frappe.get_all(
			"Whatsnext Template Button",
			filters={"parenttype": "Whatsnext Message Template", "parent": ["in", [t.name for t in templates]]},
			fields=["parent", "idx", "button_type", "button_text", "button_value"],
			order_by="idx asc",
		)
		by_parent = {}
		for b in buttons:
			by_parent.setdefault(b.parent, []).append(
				{"index": b.idx - 1, "type": b.button_type, "text": b.button_text, "value": b.button_value}
			)
		for t in templates:
			t["buttons"] = by_parent.get(t.name, [])
	return templates


@frappe.whitelist()
def submit_template_to_meta(template: str):
	"""Create the template in the connected WhatsApp Business Account and
	record its review status. Previously templates made in the app only
	existed locally and stayed "Draft" until someone recreated them by hand
	in Business Manager."""
	_require_app_user()
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Managers can submit templates to Meta.", frappe.PermissionError)

	tpl = frappe.get_doc("Whatsnext Message Template", template)
	if tpl.meta_template_id and tpl.approval_status in ("Approved", "Pending"):
		frappe.throw(f"'{template}' is already on Meta ({tpl.approval_status}). Edit it first to submit changes.")

	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.meta_enabled or not settings.meta_waba_id:
		frappe.throw("Enable Meta and set the WhatsApp Business Account ID in Whatsnext Settings first.")
	provider = MetaProvider(settings)

	samples = {}
	if tpl.variables_sample:
		try:
			samples = json.loads(tpl.variables_sample) if isinstance(tpl.variables_sample, str) else tpl.variables_sample
		except Exception:
			samples = {}

	components = []
	header_type = tpl.header_type or "None"
	if header_type == "Text" and tpl.header_text:
		header = {"type": "HEADER", "format": "TEXT", "text": tpl.header_text}
		if "{{1}}" in tpl.header_text:
			header["example"] = {"header_text": [samples.get("header_1") or "Sample"]}
		components.append(header)
	elif header_type in ("Image", "Video", "Document"):
		if not tpl.header_example_url:
			frappe.throw(f"Add a sample {header_type.lower()} URL (Header Example URL) — Meta requires an example file for media headers.")
		import requests

		resp = requests.get(tpl.header_example_url, timeout=60)
		if resp.status_code >= 400:
			frappe.throw(f"Couldn't download the header example file (HTTP {resp.status_code}).")
		mime = (resp.headers.get("Content-Type") or "application/octet-stream").split(";")[0]
		try:
			handle = provider.upload_example_media(resp.content, mime)
		except WhatsAppSendError as e:
			frappe.throw(str(e))
		components.append({"type": "HEADER", "format": header_type.upper(), "example": {"header_handle": [handle]}})

	body = {"type": "BODY", "text": tpl.body}
	placeholders = sorted(set(re.findall(r"\{\{(\d+)\}\}", tpl.body or "")), key=int)
	if placeholders:
		examples = [str(samples.get(p) or f"sample{p}") for p in placeholders]
		body["example"] = {"body_text": [examples]}
	components.append(body)

	if tpl.footer_text:
		components.append({"type": "FOOTER", "text": tpl.footer_text})

	if tpl.buttons:
		buttons = []
		for b in tpl.buttons:
			if b.button_type == "URL":
				btn = {"type": "URL", "text": b.button_text, "url": b.button_value}
				if "{{1}}" in (b.button_value or ""):
					btn["example"] = [(b.button_value or "").replace("{{1}}", "sample")]
				buttons.append(btn)
			elif b.button_type == "Phone Number":
				buttons.append({"type": "PHONE_NUMBER", "text": b.button_text, "phone_number": b.button_value})
			else:
				buttons.append({"type": "QUICK_REPLY", "text": b.button_text})
		components.append({"type": "BUTTONS", "buttons": buttons})

	payload = {
		"name": tpl.meta_name or meta_template_name(tpl.template_name),
		"language": tpl.language or "en",
		"category": (tpl.category or "Utility").upper(),
		"components": components,
	}
	try:
		if tpl.meta_template_id:
			# Already exists on Meta (edited after approval, or rejected):
			# edit that template rather than creating a duplicate name.
			result = provider.edit_template(tpl.meta_template_id, {
				"category": payload["category"], "components": payload["components"],
			})
			result.setdefault("id", tpl.meta_template_id)
			result.setdefault("status", "PENDING")
		else:
			result = provider.create_template(payload)
	except WhatsAppSendError as e:
		frappe.throw(f"Meta rejected the template: {e}")

	tpl.db_set({
		"meta_name": payload["name"],
		"meta_template_id": result.get("id"),
		"approval_status": _map_meta_status(result.get("status") or "PENDING"),
		"rejection_reason": "",
	})
	return {"meta_template_id": result.get("id"), "status": tpl.approval_status, "meta_name": payload["name"]}


@frappe.whitelist()
def update_template_provider_ids(template: str, twilio_content_sid: str | None = None):
	"""Narrow, purpose-built endpoint (rather than exposing generic
	frappe.client.set_value for this) so we can validate the SID shape and
	keep the permission surface tight to just this one field."""
	_require_app_user()
	# Same rule as save_template: only users who may edit the template.
	frappe.get_doc("Whatsnext Message Template", template).check_permission("write")
	if twilio_content_sid and not twilio_content_sid.startswith("HX"):
		frappe.throw("A Twilio Content SID normally starts with 'HX'. Double-check you copied the Content SID, not the Template SID.")
	frappe.db.set_value("Whatsnext Message Template", template, "twilio_content_sid", twilio_content_sid or "")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action from Templates UI
	return {"ok": True}


@frappe.whitelist()
def save_recipient_list(list_name: str, recipients: str | list, description: str | None = None):
	"""Creates or fully replaces a saved recipient list. recipients: list of
	{"contact_name": "...", "to_number": "...", "parameters": {...}}."""
	_require_app_user()
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
	_require_app_user()
	return frappe.get_all(
		"Whatsnext Recipient List",
		fields=["name", "list_name", "description", "recipient_count", "modified"],
		order_by="modified desc",
	)


@frappe.whitelist()
def get_recipient_list(list_name: str):
	_require_app_user()
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
	_require_app_user()
	frappe.delete_doc("Whatsnext Recipient List", list_name, ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist()
def create_campaign(campaign_name: str, template: str, recipients: str | list, provider: str | None = None,
                    scheduled_time: str | None = None):
	"""recipients: list of {"to_number": "...", "parameters": {...}} dicts,
	or a JSON string of the same. Creates the Campaign in Draft and does NOT
	send — call start_campaign separately so the frontend can show a
	confirmation/preview step first."""
	_require_app_user()
	if isinstance(recipients, str):
		recipients = json.loads(recipients)

	if not recipients:
		frappe.throw("At least one recipient is required.")

	phone_re = re.compile(r"^\+?\d{7,15}$")
	bad = [
		r.get("to_number") for r in recipients
		if not phone_re.match(re.sub(r"[\s\-()]", "", r.get("to_number") or ""))
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
		"provider": _resolve_provider(provider),
		"status": "Draft",
		"scheduled_time": _parse_schedule(scheduled_time),
		"recipients": [
			{
				# Same normalization as one-off sends: raw CSV numbers like
				# "+91 98940 88422" or a bare 10-digit local number went to
				# the provider as-is and failed or misrouted.
				"to_number": normalize_outbound_number(r["to_number"]),
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
	"""Sends now, or marks the campaign Scheduled when it has a future
	scheduled_time (the scheduler starts it when due). Also resumes a paused
	campaign: only recipients still Pending are sent."""
	_require_app_user()
	from whatsnext.whatsnext.campaign_engine import start_campaign as _start

	frappe.get_doc("Whatsnext Campaign", campaign_name).check_permission("write")
	# A double-click or a second tab used to enqueue a second send loop for
	# the same campaign, messaging every pending recipient twice. The row
	# lock (held until the commit below) makes a concurrent call wait and
	# then see "Queued", instead of both passing the check at once.
	status, scheduled_time = frappe.db.get_value(
		"Whatsnext Campaign", campaign_name, ["status", "scheduled_time"], for_update=True
	)
	if status in ("Queued", "Sending"):
		frappe.throw(f"Campaign '{campaign_name}' is already {status.lower()}.")
	if status == "Cancelled":
		frappe.throw("This campaign was cancelled. Create a new one to send again.")

	if scheduled_time and scheduled_time > now_datetime() and status in ("Draft", "Scheduled"):
		frappe.db.set_value("Whatsnext Campaign", campaign_name, "status", "Scheduled")
		return {"ok": True, "status": "Scheduled"}

	frappe.db.set_value("Whatsnext Campaign", campaign_name, "status", "Queued")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- explicit user action, needs to land before enqueue races the UI's next poll
	_start(campaign_name)
	return {"ok": True, "status": "Queued"}


@frappe.whitelist()
def pause_campaign(campaign_name: str):
	_require_app_user()
	frappe.get_doc("Whatsnext Campaign", campaign_name).check_permission("write")
	status = frappe.db.get_value("Whatsnext Campaign", campaign_name, "status")
	if status not in ("Queued", "Sending", "Scheduled"):
		frappe.throw(f"A {status} campaign can't be paused.")
	frappe.db.set_value("Whatsnext Campaign", campaign_name, "status", "Paused")
	return {"ok": True}


@frappe.whitelist()
def cancel_campaign(campaign_name: str):
	_require_app_user()
	frappe.get_doc("Whatsnext Campaign", campaign_name).check_permission("write")
	status = frappe.db.get_value("Whatsnext Campaign", campaign_name, "status")
	if status in ("Completed", "Cancelled"):
		frappe.throw(f"This campaign is already {status.lower()}.")
	frappe.db.set_value("Whatsnext Campaign", campaign_name, "status", "Cancelled")
	return {"ok": True}


@frappe.whitelist()
def retry_failed_campaign(campaign_name: str):
	"""Re-sends to recipients that failed (opted-out/skipped ones stay
	skipped)."""
	_require_app_user()
	doc = frappe.get_doc("Whatsnext Campaign", campaign_name)
	doc.check_permission("write")
	if doc.status in ("Queued", "Sending"):
		frappe.throw("Wait for the current run to finish before retrying.")
	if doc.status == "Cancelled":
		frappe.throw("This campaign was cancelled.")
	retried = 0
	for row in doc.recipients:
		if row.status == "Failed":
			row.db_set({"status": "Pending", "error_message": ""}, update_modified=False)
			retried += 1
	if not retried:
		frappe.throw("There are no failed recipients to retry.")
	frappe.db.set_value("Whatsnext Campaign", campaign_name, "scheduled_time", None)
	start_campaign(campaign_name)
	return {"ok": True, "retried": retried}


@frappe.whitelist()
def list_campaigns():
	_require_app_user()
	return frappe.get_all(
		"Whatsnext Campaign",
		fields=["name", "campaign_name", "template", "provider", "status", "scheduled_time", "total_recipients", "sent_count", "delivered_count", "failed_count", "skipped_count", "creation"],
		order_by="creation desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def get_campaign(campaign_name: str):
	_require_app_user()
	doc = frappe.get_doc("Whatsnext Campaign", campaign_name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"campaign_name": doc.campaign_name,
		"template": doc.template,
		"status": doc.status,
		"total_recipients": doc.total_recipients,
		"sent_count": doc.sent_count,
		"delivered_count": doc.delivered_count,
		"failed_count": doc.failed_count,
		"skipped_count": doc.skipped_count,
		"scheduled_time": doc.scheduled_time,
		"provider": doc.provider,
		"recipients": [
			{"to_number": r.to_number, "status": r.status, "error_message": r.error_message}
			for r in doc.recipients
		],
	}


@frappe.whitelist()
def export_campaign_results(campaign_name: str, format: str = "xlsx"):
	"""Streams the campaign's recipient results as a file download.
	format: 'xlsx' or 'pdf'."""
	_require_app_user()
	doc = frappe.get_doc("Whatsnext Campaign", campaign_name)
	doc.check_permission("read")

	headers =["Phone Number", "Status", "Parameters", "Error", "Message"]
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

		html = frappe.get_template("whatsnext/templates/campaign_results_pdf.html").render(
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


def _customer_scope_sql():
	customers = get_allowed_customers()
	if customers is None:
		return "1=1", {}
	if not customers:
		return "(customer IS NULL OR customer = '')", {}
	return "(customer IN %(scope_customers)s OR customer IS NULL OR customer = '')", {"scope_customers": tuple(customers)}


@frappe.whitelist()
def dashboard_stats():
	"""Powers the WhatsApp Hub dashboard: counts, delivery donut, weekly trend, top templates."""
	_require_app_user()
	today = getdate()
	week_start = add_to_date(today, days=-6)

	# Same customer scoping as the chat list: a Sales Person only sees
	# figures and recent activity for their own customers' chats (plus
	# unassigned ones), not company-wide numbers and other people's messages.
	scope, scope_params = _customer_scope_sql()

	counts = frappe.db.sql(
		"""
		SELECT status, COUNT(*) AS cnt
		FROM `tabWhatsnext Message`
		WHERE type = 'Outgoing' AND """ + scope + """
		GROUP BY status
		""",
		scope_params,
		as_dict=True,
	)
	status_counts = {row.status: row.cnt for row in counts}

	# Delivery figures cover outgoing messages only: incoming messages are
	# stored as Delivered/Read too, which inflated "delivered" and the
	# delivery percentage with messages we never sent.
	message_queue = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabWhatsnext Message` WHERE type='Outgoing' AND status IN ('Pending','Queued') AND " + scope,
		scope_params,
	)[0][0]
	scheduled_jobs = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabWhatsnext Message` WHERE type='Outgoing' AND scheduled_time IS NOT NULL "
		"AND status IN ('Pending','Queued') AND " + scope,
		scope_params,
	)[0][0]

	delivered = status_counts.get("Delivered", 0) + status_counts.get("Read", 0)
	failed = status_counts.get("Failed", 0)
	pending = status_counts.get("Pending", 0) + status_counts.get("Queued", 0)
	total_sent = sum(status_counts.values())
	delivered_pct = round((delivered / total_sent) * 100, 1) if total_sent else 0

	weekly_rows = frappe.db.sql(
		"""
		SELECT DATE(creation) AS day,
			SUM(CASE WHEN type='Outgoing' THEN 1 ELSE 0 END) AS sent,
			SUM(CASE WHEN type='Outgoing' AND status IN ('Delivered','Read') THEN 1 ELSE 0 END) AS delivered
		FROM `tabWhatsnext Message`
		WHERE DATE(creation) BETWEEN %(start)s AND %(end)s AND """ + scope + """
		GROUP BY DATE(creation)
		ORDER BY day ASC
		""",
		{"start": week_start, "end": today, **scope_params},
		as_dict=True,
	)
	# One point per day for the whole week, zero-filled -- days with no
	# messages used to be missing entirely, so the chart's x-axis skipped
	# them and the line implied activity that never happened.
	by_day = {getdate(r.day): r for r in weekly_rows}
	weekly = []
	for i in range(7):
		day = getdate(add_to_date(week_start, days=i))
		r = by_day.get(day)
		weekly.append({
			"day": str(day),
			"sent": int(r.sent or 0) if r else 0,
			"delivered": int(r.delivered or 0) if r else 0,
		})

	top_templates = frappe.db.sql(
		"""
		SELECT template, COUNT(*) AS cnt
		FROM `tabWhatsnext Message`
		WHERE template IS NOT NULL AND template != '' AND """ + scope + """
		GROUP BY template
		ORDER BY cnt DESC
		LIMIT 5
		""",
		scope_params,
		as_dict=True,
	)

	# get_list applies the doctype's permission query conditions.
	recent = frappe.get_list(
		"Whatsnext Message",
		fields=["name", "to_number", "from_number", "conversation_id", "type", "status", "message", "template", "creation"],
		order_by="creation desc",
		limit_page_length=8,
	)

	return {
		"message_queue": message_queue,
		"sent_this_week": sum(r["sent"] for r in weekly),
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


# ---------------------------------------------------------------------------
# Notifications (event-driven sends) — managed from the SPA, System Managers
# ---------------------------------------------------------------------------

def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("Only System Managers can manage notifications.", frappe.PermissionError)


NOTIFICATION_FIELDS = [
	"notification_name", "enabled", "event", "reference_doctype", "recipient_number_field",
	"fixed_number", "template", "provider", "attach_document_print", "print_format", "condition",
]


@frappe.whitelist()
def list_notifications():
	_require_app_user()
	_require_system_manager()
	return frappe.get_all(
		"Whatsnext Notification",
		fields=["name", "notification_name", "enabled", "event", "reference_doctype", "template", "last_polled", "modified"],
		order_by="modified desc",
	)


@frappe.whitelist()
def get_notification(name: str):
	_require_app_user()
	_require_system_manager()
	doc = frappe.get_doc("Whatsnext Notification", name)
	data = {f: doc.get(f) for f in NOTIFICATION_FIELDS}
	data["name"] = doc.name
	data["field_mapping"] = [
		{"template_variable": r.template_variable, "source_fieldname": r.source_fieldname, "static_value": r.static_value}
		for r in doc.field_mapping
	]
	return data


@frappe.whitelist()
def save_notification(data: str | dict):
	"""Create or update a Whatsnext Notification (validate() still enforces
	the realtime-vs-Scheduled and PDF-header rules)."""
	_require_app_user()
	_require_system_manager()
	if isinstance(data, str):
		data = json.loads(data)
	name = data.get("name")
	doc = frappe.get_doc("Whatsnext Notification", name) if name else frappe.new_doc("Whatsnext Notification")
	for f in NOTIFICATION_FIELDS:
		if f in data:
			doc.set(f, data[f])
	if name and data.get("notification_name") and data["notification_name"] != name:
		frappe.throw("Renaming a notification isn't supported — create a new one instead.")
	doc.set("field_mapping", [])
	for row in data.get("field_mapping") or []:
		if row.get("template_variable"):
			doc.append("field_mapping", {
				"template_variable": str(row["template_variable"]),
				"source_fieldname": row.get("source_fieldname") or None,
				"static_value": row.get("static_value") or None,
			})
	doc.save()
	return get_notification(doc.name)


@frappe.whitelist()
def delete_notification(name: str):
	_require_app_user()
	_require_system_manager()
	frappe.delete_doc("Whatsnext Notification", name)
	return {"ok": True}


@frappe.whitelist()
def get_notification_options(doctype: str | None = None):
	"""Doctypes with instant (realtime) events, and — for a chosen doctype —
	its fields so the UI can offer pickers instead of free-typed names."""
	_require_app_user()
	_require_system_manager()
	from whatsnext.hooks import WATCHED_DOCTYPES

	result = {"watched_doctypes": [d for d in WATCHED_DOCTYPES if frappe.db.exists("DocType", d)]}
	doctype = _clean_param(doctype)
	if doctype:
		meta = frappe.get_meta(doctype)
		skip = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect", "Fold", "Heading", "Image"}
		result["fields"] = [
			{"fieldname": f.fieldname, "label": f.label or f.fieldname, "fieldtype": f.fieldtype}
			for f in meta.fields if f.fieldtype not in skip
		] + [{"fieldname": "name", "label": "ID (name)", "fieldtype": "Data"}]
		result["is_submittable"] = bool(meta.is_submittable)
		result["print_formats"] = frappe.get_all("Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name")
	return result


@frappe.whitelist()
def search_doctypes(txt: str = ""):
	"""Any doctype can be watched with the Scheduled event."""
	_require_app_user()
	_require_system_manager()
	return frappe.get_all(
		"DocType",
		filters={"istable": 0, "issingle": 0, "name": ["like", f"%{txt or ''}%"]},
		pluck="name",
		order_by="name asc",
		limit_page_length=20,
	)


@frappe.whitelist()
def get_document_whatsapp_context(doctype: str, name: str):
	"""For the Desk "WhatsApp" button: the best number to message for this
	document, plus print formats and the existing chat (if any)."""
	_require_app_user()
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")

	number = None
	for field in ("whatsapp_no", "whatsapp_number", "mobile_no", "contact_mobile", "mobile",
	              "cell_number", "phone", "contact_phone", "phone_no"):
		if doc.get(field):
			number = doc.get(field)
			break
	if not number:
		from whatsnext.whatsnext.notification_engine import _fallback_contact_mobile

		number = _fallback_contact_mobile(doc)
	if not number and doctype in ("Customer", "Supplier", "Lead"):
		contact = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": doctype, "link_name": name},
			"parent",
		)
		if contact:
			number = frappe.db.get_value("Contact", contact, "mobile_no") or frappe.db.get_value("Contact", contact, "phone")

	conversation_id = normalize_outbound_number(number) if number else None
	return {
		"number": number,
		"conversation_id": conversation_id,
		"has_chat": bool(conversation_id and frappe.db.exists("Whatsnext Conversation", conversation_id)),
		"print_formats": frappe.get_all("Print Format", filters={"doc_type": doctype, "disabled": 0}, pluck="name"),
		"default_print_format": frappe.get_meta(doctype).default_print_format,
	}


TEMPLATE_FIELDS = [
	"provider", "language", "category", "header_type", "header_text", "header_example_url",
	"body", "footer_text", "twilio_content_sid", "variables_sample",
]


@frappe.whitelist()
def save_template(data: str | dict):
	"""Create or update a template including its buttons in one save (the
	page previously issued one set_value per field, which couldn't edit the
	buttons table at all). Editing an Approved Meta template's content means
	it must be re-reviewed, so the status drops back to Draft."""
	_require_app_user()
	if isinstance(data, str):
		data = json.loads(data)
	name = _clean_param(data.get("name"))
	if name:
		doc = frappe.get_doc("Whatsnext Message Template", name)
		doc.check_permission("write")
	else:
		doc = frappe.new_doc("Whatsnext Message Template")
		doc.template_name = (data.get("template_name") or "").strip()

	content_fields = ("header_type", "header_text", "body", "footer_text")
	content_changed = False
	for f in TEMPLATE_FIELDS:
		if f in data:
			value = data[f]
			if f == "variables_sample" and isinstance(value, dict):
				value = json.dumps(value)
			if f in content_fields and (doc.get(f) or "") != (value or ""):
				content_changed = True
			doc.set(f, value)

	if "buttons" in data:
		old = [(b.button_type, b.button_text, b.button_value or "") for b in doc.buttons]
		doc.set("buttons", [])
		for b in data.get("buttons") or []:
			if b.get("button_text"):
				doc.append("buttons", {
					"button_type": b.get("button_type") or "Quick Reply",
					"button_text": b["button_text"],
					"button_value": b.get("button_value") or "",
				})
		new = [(b.button_type, b.button_text, b.button_value or "") for b in doc.buttons]
		content_changed = content_changed or old != new

	twilio_sid = data.get("twilio_content_sid")
	if twilio_sid and not twilio_sid.startswith("HX"):
		frappe.throw("A Twilio Content SID normally starts with 'HX'. Double-check you copied the Content SID, not the Template SID.")

	if name and content_changed and doc.meta_template_id and doc.approval_status in ("Approved", "Rejected"):
		# Meta's copy no longer matches; "Submit to Meta" now sends the edit
		# to the existing template (same meta_template_id) for re-review.
		doc.approval_status = "Draft"
		doc.rejection_reason = None

	doc.save()
	return doc.as_dict()


# ---------------------------------------------------------------------------
# Quick replies
# ---------------------------------------------------------------------------

@frappe.whitelist()
def list_quick_replies(search: str | None = None):
	_require_app_user()
	search = _clean_param(search)
	or_filters = None
	if search:
		like = f"%{search.lstrip('/')}%"
		or_filters = [["title", "like", like], ["shortcut", "like", like], ["message", "like", like]]
	return frappe.get_all(
		"Whatsnext Quick Reply",
		or_filters=or_filters,
		fields=["name", "title", "shortcut", "message"],
		order_by="title asc",
		limit_page_length=100,
	)


@frappe.whitelist()
def save_quick_reply(title: str, message: str, shortcut: str | None = None, name: str | None = None):
	_require_app_user()
	name = _clean_param(name)
	if name:
		doc = frappe.get_doc("Whatsnext Quick Reply", name)
		if title != name:
			frappe.throw("Renaming a quick reply isn't supported — create a new one instead.")
	else:
		doc = frappe.new_doc("Whatsnext Quick Reply")
		doc.title = title
	doc.message = message
	doc.shortcut = _clean_param(shortcut)
	doc.save()
	return doc.as_dict()


@frappe.whitelist()
def delete_quick_reply(name: str):
	_require_app_user()
	frappe.delete_doc("Whatsnext Quick Reply", name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Agent report
# ---------------------------------------------------------------------------

@frappe.whitelist()
def agent_report(from_date: str | None = None, to_date: str | None = None):
	"""Per-agent activity for a date range: messages sent, chats handled,
	replies and how quickly they came after the customer wrote, plus open
	chats currently assigned. Automated sends (notifications, campaigns,
	auto-replies) are excluded. System Managers see every agent; other
	users see only their own row."""
	_require_app_user()
	import statistics

	from frappe.utils import date_diff, get_datetime

	to_date = getdate(_clean_param(to_date) or getdate())
	from_date = getdate(_clean_param(from_date) or add_to_date(to_date, days=-6))
	if from_date > to_date:
		frappe.throw("The start date must be before the end date.")
	if date_diff(to_date, from_date) > 92:
		frappe.throw("Choose a range of up to 3 months.")

	is_manager = "System Manager" in frappe.get_roles(frappe.session.user)
	start = get_datetime(f"{from_date} 00:00:00")
	end = get_datetime(f"{to_date} 23:59:59.999999")

	rows = frappe.db.sql(
		"""
		SELECT conversation_id, type, is_automated, owner, creation
		FROM `tabWhatsnext Message`
		WHERE creation BETWEEN %(start)s AND %(end)s
			AND conversation_id IS NOT NULL AND conversation_id != ''
			AND status != 'Failed'
			AND NOT (status = 'Pending' AND scheduled_time IS NOT NULL)
		ORDER BY conversation_id, creation
		""",
		{"start": start, "end": end},
		as_dict=True,
	)

	stats = {}

	def agent(user):
		return stats.setdefault(user, {"user": user, "messages_sent": 0, "chats": set(), "response_minutes": []})

	incoming = 0
	waiting_chats = 0
	current_conv, waiting_since = None, None
	for r in rows:
		if r.conversation_id != current_conv:
			if waiting_since is not None:
				waiting_chats += 1
			current_conv, waiting_since = r.conversation_id, None

		if r.type == "Incoming":
			incoming += 1
			if waiting_since is None:
				waiting_since = r.creation
			continue

		if r.is_automated or r.owner in ("Guest", None):
			continue  # auto-replies don't count as answering the customer

		a = agent(r.owner)
		a["messages_sent"] += 1
		a["chats"].add(r.conversation_id)
		if waiting_since is not None:
			a["response_minutes"].append((r.creation - waiting_since).total_seconds() / 60)
			waiting_since = None
	if waiting_since is not None:
		waiting_chats += 1

	open_assigned = dict(frappe.db.sql(
		"""SELECT assigned_to, COUNT(*) FROM `tabWhatsnext Conversation`
		WHERE status = 'Open' AND assigned_to IS NOT NULL AND assigned_to != ''
		GROUP BY assigned_to"""
	))
	for user in open_assigned:
		agent(user)

	result = []
	for user, a in stats.items():
		if not is_manager and user != frappe.session.user:
			continue
		times = a["response_minutes"]
		result.append({
			"user": user,
			"full_name": frappe.utils.get_fullname(user),
			"messages_sent": a["messages_sent"],
			"chats_handled": len(a["chats"]),
			"replies": len(times),
			"avg_response_minutes": round(sum(times) / len(times), 1) if times else None,
			"median_response_minutes": round(statistics.median(times), 1) if times else None,
			"open_assigned": open_assigned.get(user, 0),
		})
	result.sort(key=lambda x: (-x["messages_sent"], x["full_name"] or x["user"]))

	return {
		"from_date": str(from_date),
		"to_date": str(to_date),
		"agents": result,
		"totals": {
			"incoming_messages": incoming,
			"chats_waiting_for_reply": waiting_chats,
			"unassigned_open_chats": frappe.db.count(
				"Whatsnext Conversation", {"status": "Open", "assigned_to": ["is", "not set"]}
			),
		} if is_manager else None,
	}


# ---------------------------------------------------------------------------
# Internal notes (team-only, never sent)
# ---------------------------------------------------------------------------

def _publish_note_event(conversation_id):
	from whatsnext.whatsnext.permissions import users_who_can_see

	customer = frappe.db.get_value("Whatsnext Conversation", conversation_id, "customer")
	for user in users_who_can_see(customer):
		frappe.publish_realtime(
			event="whatsnext_note", message={"conversation_id": conversation_id}, user=user, after_commit=True,
		)


@frappe.whitelist()
def get_notes(conversation_id: str):
	_require_app_user()
	_assert_conversation_access(conversation_id)
	notes = frappe.get_all(
		"Whatsnext Conversation Note",
		filters={"conversation_id": conversation_id},
		fields=["name", "note", "owner", "creation"],
		order_by="creation asc",
	)
	for n in notes:
		n["author"] = frappe.utils.get_fullname(n.owner)
	return notes


@frappe.whitelist()
def add_note(conversation_id: str, note: str):
	_require_app_user()
	_assert_conversation_access(conversation_id)
	note = (note or "").strip()
	if not note:
		frappe.throw("The note is empty.")
	doc = frappe.get_doc({
		"doctype": "Whatsnext Conversation Note",
		"conversation_id": conversation_id,
		"note": note,
	}).insert(ignore_permissions=True)
	_publish_note_event(conversation_id)
	return {"name": doc.name, "note": doc.note, "owner": doc.owner, "creation": doc.creation,
	        "author": frappe.utils.get_fullname(doc.owner)}


@frappe.whitelist()
def delete_note(name: str):
	"""Authors can delete their own notes; System Managers any note."""
	_require_app_user()
	row = frappe.db.get_value("Whatsnext Conversation Note", name, ["owner", "conversation_id"])
	if not row:
		# Already deleted (e.g. by a teammate) -- unpacking None was a 500.
		frappe.throw("That note no longer exists.")
	owner, conversation_id = row
	if owner != frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("You can only delete your own notes.", frappe.PermissionError)
	frappe.delete_doc("Whatsnext Conversation Note", name, ignore_permissions=True)
	_publish_note_event(conversation_id)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Link an unknown number to ERPNext (Contact / Lead)
# ---------------------------------------------------------------------------

def _relink_conversation(conversation_id, contact, customer=None):
	"""Point every message in the chat (and the chat itself) at the new
	Contact, and its Customer when there is one."""
	frappe.db.sql(
		"""UPDATE `tabWhatsnext Message` SET contact = %(contact)s
		WHERE conversation_id = %(cid)s""",
		{"contact": contact, "cid": conversation_id},
	)
	if customer:
		frappe.db.sql(
			"""UPDATE `tabWhatsnext Message` SET customer = %(customer)s
			WHERE conversation_id = %(cid)s AND (customer IS NULL OR customer = '')""",
			{"customer": customer, "cid": conversation_id},
		)
	_ensure_conversation(conversation_id)
	updates = {"contact": contact}
	if customer:
		updates["customer"] = customer
	frappe.db.set_value("Whatsnext Conversation", conversation_id, updates, update_modified=False)


def _new_contact(first_name, last_name, number, links):
	contact = frappe.get_doc({
		"doctype": "Contact",
		"first_name": first_name,
		"last_name": last_name or None,
		"phone_nos": [{"phone": f"+{number}", "is_primary_mobile_no": 1}],
		"links": links,
	})
	# Normal permissions on purpose: agents can only create Contacts if their
	# ERPNext role allows it.
	contact.insert()
	return contact


@frappe.whitelist()
def save_number_as_contact(conversation_id: str, first_name: str, last_name: str | None = None,
                           customer: str | None = None):
	"""Create an ERPNext Contact for a chat's number (optionally linked to an
	existing Customer) and link the chat to it."""
	_require_app_user()
	_assert_conversation_access(conversation_id)
	first_name = (first_name or "").strip()
	if not first_name:
		frappe.throw("Enter a first name.")
	customer = _clean_param(customer)

	from whatsnext.whatsnext.contacts import resolve_contact_from_phone

	existing = resolve_contact_from_phone(conversation_id)
	if existing:
		frappe.throw(f"This number already belongs to Contact {existing}.")

	links = []
	if customer:
		if not frappe.db.exists("Customer", customer):
			frappe.throw(f"Customer {customer} not found.")
		if not frappe.has_permission("Customer", "read", customer):
			frappe.throw(f"You don't have access to Customer {customer}.", frappe.PermissionError)
		allowed = get_allowed_customers()
		if allowed is not None and customer not in allowed:
			frappe.throw("You can only link chats to customers assigned to you.", frappe.PermissionError)
		links.append({"link_doctype": "Customer", "link_name": customer})

	contact = _new_contact(first_name, last_name, conversation_id, links)
	_relink_conversation(conversation_id, contact.name, customer)
	return get_conversation_info(conversation_id)


@frappe.whitelist()
def create_lead_from_chat(conversation_id: str, first_name: str, last_name: str | None = None,
                          company_name: str | None = None):
	"""Create an ERPNext Lead for a new enquiry on WhatsApp, with a Contact
	for the number, and link the chat to it."""
	_require_app_user()
	_assert_conversation_access(conversation_id)
	first_name = (first_name or "").strip()
	if not first_name:
		frappe.throw("Enter a first name.")
	if not frappe.db.exists("DocType", "Lead"):
		frappe.throw("ERPNext Leads aren't available on this site.")

	from whatsnext.whatsnext.contacts import resolve_contact_from_phone

	existing = resolve_contact_from_phone(conversation_id)
	if existing:
		frappe.throw(f"This number already belongs to Contact {existing}.")

	meta = frappe.get_meta("Lead")
	lead = frappe.new_doc("Lead")
	lead.first_name = first_name
	if meta.has_field("last_name"):
		lead.last_name = (last_name or "").strip() or None
	if not meta.has_field("first_name"):  # very old ERPNext
		lead.lead_name = " ".join(x for x in (first_name, last_name) if x)
	lead.company_name = _clean_param(company_name)
	lead.mobile_no = f"+{conversation_id}"
	if meta.has_field("whatsapp_no"):
		lead.whatsapp_no = f"+{conversation_id}"
	if meta.has_field("source") and frappe.db.exists("Lead Source", "WhatsApp"):
		lead.source = "WhatsApp"
	lead.insert()  # ERPNext permissions apply

	# Some ERPNext versions create a Contact for the Lead on insert.
	contact = resolve_contact_from_phone(conversation_id)
	if not contact:
		contact = _new_contact(first_name, last_name, conversation_id,
		                       [{"link_doctype": "Lead", "link_name": lead.name}]).name
	_relink_conversation(conversation_id, contact)

	info = get_conversation_info(conversation_id)
	info["lead"] = lead.name
	return info


@frappe.whitelist()
def search_customers(search: str | None = None):
	"""Customers this user may link a chat to."""
	_require_app_user()
	search = _clean_param(search)
	filters = {"disabled": 0}
	allowed = get_allowed_customers()
	if allowed is not None:
		if not allowed:
			return []
		filters["name"] = ["in", allowed]
	or_filters = [["name", "like", f"%{search}%"], ["customer_name", "like", f"%{search}%"]] if search else None
	return frappe.get_list(
		"Customer", filters=filters, or_filters=or_filters,
		fields=["name", "customer_name"], order_by="modified desc", limit_page_length=20,
	)
