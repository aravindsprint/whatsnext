"""Hooks for other apps to answer incoming WhatsApp messages automatically.

1. Declare a handler in your app's hooks.py:

	whatsnext_incoming_handlers = ["my_app.whatsapp.on_incoming"]

   It is called with every saved incoming Whatsnext Message (after media is
   downloaded and opt-out keywords are handled). Return True if your app
   takes the message; Whatsnext then skips its away reply. Handlers run
   inside the webhook request, so keep them cheap: decide, enqueue the real
   work, and return. A failing handler is logged and skipped.

2. From your background job, reply with send_reply(). The reply is stored as
   an automated outgoing message, so it shows in the chat like any other.
"""

import frappe


def run_incoming_handlers(doc) -> bool:
	for path in frappe.get_hooks("whatsnext_incoming_handlers") or []:
		try:
			if frappe.get_attr(path)(doc):
				return True
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Whatsnext: incoming handler {path} failed")
	return False


def send_reply(to, text=None, audio=None, audio_mime="audio/ogg", provider=None, reply_to=None):
	"""Send an automated reply inside the 24-hour window.

	text:  the message body.
	audio: bytes of a voice reply (Ogg/Opus or MP3). Sent through Meta's media
	       upload, so no public link is needed; ignored on Twilio, which can
	       only send media from a public URL.
	Returns the names of the Whatsnext Message records created.
	"""
	from frappe.utils.file_manager import save_file

	from whatsnext.whatsnext.api import _create_message_record, _dispatch, _extract_provider_message_id, _mark_failed
	from whatsnext.whatsnext.api.webhook import apply_early_statuses
	from whatsnext.whatsnext.contacts import normalize_outbound_number
	from whatsnext.whatsnext.provider_engine import WhatsAppSendError, get_provider

	to = normalize_outbound_number(to)
	names = []

	if text:
		msg = _create_message_record(
			type="Outgoing", provider=provider, status="Pending", to_number=to, message=text,
			message_type="Manual", content_type="text", reply_to=reply_to, is_automated=1,
		)
		_dispatch(msg)
		names.append(msg.name)

	if audio and (provider or frappe.get_cached_doc("Whatsnext Settings").default_provider) == "Meta":
		msg = _create_message_record(
			type="Outgoing", provider="Meta", status="Pending", to_number=to, message="",
			message_type="Manual", content_type="audio", is_automated=1,
		)
		ext = "mp3" if "mpeg" in (audio_mime or "") else "ogg"
		# Private copy so staff can play it in the chat; WhatsApp gets an uploaded media id.
		file_doc = save_file(f"voice_reply_{msg.name}.{ext}", audio, "Whatsnext Message", msg.name, is_private=1)
		msg.db_set("attach", file_doc.file_url, update_modified=False)
		try:
			result = get_provider("Meta").send_media_bytes(to, audio, (audio_mime or "audio/ogg").split(";")[0], "audio")
			msg.db_set("status", "Sent", update_modified=False)
			mid = _extract_provider_message_id("Meta", result)
			if mid:
				msg.db_set("provider_message_id", mid, update_modified=False)
				frappe.db.commit()  # nosemgrep: frappe-manual-commit -- let delivery receipts find it
				apply_early_statuses(mid)
		except WhatsAppSendError as e:
			_mark_failed(msg, str(e))
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Whatsnext: voice reply {msg.name} failed")
			_mark_failed(msg, str(e))
		names.append(msg.name)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job sending replies
	return names
