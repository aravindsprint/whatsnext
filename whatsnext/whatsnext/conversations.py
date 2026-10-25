"""Conversation state (assignment, open/closed, 24-hour window) and opt-outs.

A Whatsnext Conversation row is upserted for every message, so the chat list
and the send endpoints can answer "who owns this chat", "is it closed" and
"may we send free-form text right now" with one indexed lookup instead of
scanning the message table.
"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

# WhatsApp lets a business send free-form (non-template) messages only within
# 24 hours of the customer's last message to it.
SERVICE_WINDOW_HOURS = 24


def message_preview(msg) -> str:
	"""One-line text for the chat list."""
	text = (msg.get("message") or "").strip()
	if not text and msg.get("template"):
		text = f"📋 {msg.get('template')}"
	if not text and msg.get("content_type") not in (None, "", "text"):
		text = {"image": "📷 Photo", "video": "🎬 Video", "audio": "🎵 Audio", "document": "📎 Document",
		        "location": "📍 Location", "contacts": "👤 Contact"}.get(msg.get("content_type"), "📎 Media")
	return text.replace("\n", " ")[:140]


def is_unsent_scheduled(msg) -> bool:
	return bool(msg.get("scheduled_time")) and msg.get("status") == "Pending"


def touch_conversation(msg, sending_scheduled=False):
	"""Keep the Whatsnext Conversation row in step with its messages. Called
	from Whatsnext Message.after_insert, and by the scheduler when a
	scheduled message actually goes out. The chat list reads only this
	table, so it stays fast however much message history builds up."""
	conversation_id = msg.conversation_id
	if not conversation_id or (is_unsent_scheduled(msg) and not sending_scheduled):
		# A scheduled message joins the chat when it's sent, not when it's
		# scheduled.
		return

	now = msg.creation or now_datetime()
	incoming = msg.type == "Incoming"
	updates = {
		"last_message_at": now,
		"last_message": message_preview(msg),
		"last_message_type": msg.type,
		"last_message_name": msg.name,
	}
	if msg.customer:
		updates["customer"] = msg.customer
	if msg.get("contact"):
		updates["contact"] = msg.contact
	if incoming:
		updates["last_incoming_at"] = now
		if msg.profile_name:
			updates["profile_name"] = msg.profile_name
		# A customer writing again reopens a closed chat.
		updates["status"] = "Open"

	if not frappe.db.exists("Whatsnext Conversation", conversation_id):
		doc = frappe.get_doc({
			"doctype": "Whatsnext Conversation",
			"conversation_id": conversation_id,
			"status": "Open",
			"unread_count": 1 if incoming and msg.status == "Delivered" else 0,
			"outgoing_count": 0 if incoming else 1,
			**updates,
		})
		try:
			doc.insert(ignore_permissions=True)
			return
		except frappe.DuplicateEntryError:
			pass  # created concurrently by another message — update it below

	frappe.db.set_value("Whatsnext Conversation", conversation_id, updates, update_modified=False)
	# Counters as single atomic UPDATEs, so concurrent webhooks can't lose counts.
	if incoming and msg.status == "Delivered":
		_bump(conversation_id, "unread_count", 1)
	elif not incoming:
		_bump(conversation_id, "outgoing_count", 1)


# One fixed statement per counter: the column can't be a query parameter, and
# building it into the SQL string is what the Marketplace security scan rejects.
_BUMP_SQL = {
	"unread_count": """UPDATE `tabWhatsnext Conversation`
		SET `unread_count` = GREATEST(COALESCE(`unread_count`, 0) + %(delta)s, 0)
		WHERE name = %(name)s""",
	"outgoing_count": """UPDATE `tabWhatsnext Conversation`
		SET `outgoing_count` = GREATEST(COALESCE(`outgoing_count`, 0) + %(delta)s, 0)
		WHERE name = %(name)s""",
}


def _bump(conversation_id, field, delta):
	frappe.db.sql(_BUMP_SQL[field], {"delta": delta, "name": conversation_id})


def mark_conversation_read(conversation_id):
	frappe.db.set_value("Whatsnext Conversation", conversation_id, "unread_count", 0, update_modified=False)


def record_outgoing_failed(conversation_id):
	"""A sent message turned out Failed — it no longer counts as sent."""
	if conversation_id:
		_bump(conversation_id, "outgoing_count", -1)


def refresh_conversation_summary(conversation_id):
	"""Recompute the summary fields from the messages (used after a message
	is removed, and by the backfill patch)."""
	latest = frappe.db.sql(
		"""SELECT name, type, message, template, content_type, creation, scheduled_time, status
		FROM `tabWhatsnext Message`
		WHERE conversation_id = %(cid)s AND NOT (status = 'Pending' AND scheduled_time IS NOT NULL)
		ORDER BY creation DESC, name DESC LIMIT 1""",
		{"cid": conversation_id},
		as_dict=True,
	)
	counts = frappe.db.sql(
		"""SELECT
			SUM(CASE WHEN type = 'Incoming' AND status = 'Delivered' THEN 1 ELSE 0 END),
			SUM(CASE WHEN type = 'Outgoing' AND status != 'Failed'
				AND NOT (status = 'Pending' AND scheduled_time IS NOT NULL) THEN 1 ELSE 0 END)
		FROM `tabWhatsnext Message` WHERE conversation_id = %(cid)s""",
		{"cid": conversation_id},
	)[0]
	updates = {"unread_count": int(counts[0] or 0), "outgoing_count": int(counts[1] or 0)}
	if latest:
		m = latest[0]
		updates.update({
			"last_message_at": m.creation,
			"last_message": message_preview(m),
			"last_message_type": m.type,
			"last_message_name": m.name,
		})
	frappe.db.set_value("Whatsnext Conversation", conversation_id, updates, update_modified=False)


def window_expires_at(conversation_id):
	"""When the customer-service window closes, or None if the customer has
	never written to us (so only templates can be sent)."""
	last_incoming = frappe.db.get_value("Whatsnext Conversation", conversation_id, "last_incoming_at")
	if not last_incoming:
		# Fallback for chats that predate the Conversation table.
		last_incoming = frappe.db.get_value(
			"Whatsnext Message",
			{"conversation_id": conversation_id, "type": "Incoming"},
			"creation",
			order_by="creation desc",
		)
	if not last_incoming:
		return None
	return add_to_date(get_datetime(last_incoming), hours=SERVICE_WINDOW_HOURS)


def window_is_open(conversation_id) -> bool:
	expires = window_expires_at(conversation_id)
	return bool(expires and expires > now_datetime())


# --------------------------------------------------------------------------
# Opt-outs
# --------------------------------------------------------------------------

def is_opted_out(number) -> bool:
	from whatsnext.whatsnext.contacts import normalize_outbound_number

	if not number:
		return False
	return bool(frappe.db.get_value("Whatsnext Opt Out", normalize_outbound_number(number), "opted_out"))


def set_opt_out(number, opted_out: bool, source="Manual", keyword=None, customer=None):
	from whatsnext.whatsnext.contacts import normalize_outbound_number

	phone = normalize_outbound_number(number)
	if frappe.db.exists("Whatsnext Opt Out", phone):
		doc = frappe.get_doc("Whatsnext Opt Out", phone)
	else:
		if not opted_out:
			return None  # nothing to opt back in
		doc = frappe.new_doc("Whatsnext Opt Out")
		doc.phone = phone
	doc.opted_out = 1 if opted_out else 0
	doc.source = source
	if keyword:
		doc.last_keyword = keyword
	if customer:
		doc.customer = customer
	doc.save(ignore_permissions=True)
	return doc


def _keywords(text):
	return {k.strip().upper() for k in (text or "").splitlines() if k.strip()}


def handle_opt_keywords(message_doc):
	"""If an incoming text is exactly an opt-out/opt-in keyword, record it
	and send the configured confirmation (we're inside the 24h window since
	the customer just wrote). Returns True when a keyword was handled."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.opt_out_enabled:
		return False

	text = (message_doc.message or "").strip().upper()
	if not text:
		return False

	if text in _keywords(settings.opt_out_keywords):
		set_opt_out(message_doc.from_number, True, "Keyword", text, message_doc.customer)
		reply = settings.opt_out_confirmation
	elif text in _keywords(settings.opt_in_keywords):
		if not is_opted_out(message_doc.from_number):
			return False
		set_opt_out(message_doc.from_number, False, "Keyword", text, message_doc.customer)
		reply = settings.opt_in_confirmation
	else:
		return False

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request; the opt-out must persist even if the confirmation send fails
	if reply:
		try:
			from whatsnext.whatsnext.api import send_message

			send_message(to=message_doc.from_number, message=reply, provider=message_doc.provider, automated=1)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Whatsnext: opt-out confirmation failed")
	return True


# --------------------------------------------------------------------------
# Read receipts
# --------------------------------------------------------------------------

def send_read_receipt(message_id):
	"""Background job (enqueued from api.mark_as_read)."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not (settings.send_read_receipts and settings.meta_enabled):
		return
	from whatsnext.whatsnext.provider_engine import MetaProvider, WhatsAppSendError

	try:
		MetaProvider(settings).mark_read(message_id)
	except WhatsAppSendError:
		# Meta only accepts receipts for recent messages; nothing to retry.
		pass


# --------------------------------------------------------------------------
# Away message (outside business hours)
# --------------------------------------------------------------------------

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def is_business_hours(settings, at=None) -> bool:
	from frappe.utils import get_time, getdate

	at = at or now_datetime()
	days = {d.strip()[:3].title() for d in (settings.business_days or "").split(",") if d.strip()}
	if days and _DAYS[at.weekday()] not in days:
		return False

	if settings.holiday_list and frappe.db.exists(
		"Holiday", {"parent": settings.holiday_list, "holiday_date": getdate(at)}
	):
		return False

	if not (settings.business_hours_start and settings.business_hours_end):
		return True
	start, end, now = get_time(settings.business_hours_start), get_time(settings.business_hours_end), at.time()
	if start <= end:
		return start <= now < end
	return now >= start or now < end  # overnight hours, e.g. 20:00-02:00


def queue_away_reply(message_doc):
	"""Called from the inbound webhook for each customer message. Cheap
	checks happen here; the send runs in the background after commit."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not (settings.away_enabled and settings.away_message) or is_business_hours(settings):
		return
	frappe.enqueue(
		"whatsnext.whatsnext.conversations.send_away_reply",
		queue="short",
		enqueue_after_commit=True,
		conversation_id=message_doc.conversation_id,
		provider=message_doc.provider,
	)


def send_away_reply(conversation_id, provider=None):
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not (settings.away_enabled and settings.away_message) or is_business_hours(settings):
		return

	cooldown = int(settings.away_cooldown_hours or 12)
	last = frappe.db.get_value("Whatsnext Conversation", conversation_id, "last_away_reply_at")
	if last and get_datetime(last) > add_to_date(now_datetime(), hours=-cooldown):
		return

	# Claim the slot first so two messages arriving together send one reply.
	frappe.db.set_value("Whatsnext Conversation", conversation_id, "last_away_reply_at", now_datetime(), update_modified=False)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job; claim before the slow send

	from whatsnext.whatsnext.api import send_message

	try:
		send_message(to=conversation_id, message=settings.away_message, provider=provider, automated=1)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext: away reply to {conversation_id} failed")
