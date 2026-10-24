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


def touch_conversation(msg):
	"""Called from Whatsnext Message.after_insert."""
	conversation_id = msg.conversation_id
	if not conversation_id:
		return

	now = msg.creation or now_datetime()
	existing = frappe.db.get_value(
		"Whatsnext Conversation", conversation_id, ["name", "status"], as_dict=True
	)
	updates = {"last_message_at": now}
	if msg.customer:
		updates["customer"] = msg.customer
	if msg.get("contact"):
		updates["contact"] = msg.contact
	if msg.type == "Incoming":
		updates["last_incoming_at"] = now
		if msg.profile_name:
			updates["profile_name"] = msg.profile_name
		# A customer writing again reopens a closed chat.
		updates["status"] = "Open"

	if existing:
		frappe.db.set_value("Whatsnext Conversation", conversation_id, updates, update_modified=False)
		return

	doc = frappe.get_doc({
		"doctype": "Whatsnext Conversation",
		"conversation_id": conversation_id,
		"status": "Open",
		**updates,
	})
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Two messages for a brand-new number inserted concurrently.
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

			send_message(to=message_doc.from_number, message=reply, provider=message_doc.provider)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Whatsnext: opt-out confirmation failed")
	return True
