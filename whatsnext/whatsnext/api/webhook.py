import json
import frappe
from werkzeug.wrappers import Response

from whatsnext.whatsnext.contacts import resolve_customer_from_phone, normalize_outbound_number


# ---------------------------------------------------------------------------
# Meta WhatsApp Cloud API webhook
# GET  /api/method/whatsnext.whatsnext.api.webhook.meta_webhook  -> verification handshake
# POST /api/method/whatsnext.whatsnext.api.webhook.meta_webhook  -> inbound events
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def meta_webhook():
	if frappe.request.method == "GET":
		return _meta_verify()
	return _meta_receive()


def _meta_verify():
	settings = frappe.get_cached_doc("Whatsnext Settings")
	mode = frappe.form_dict.get("hub.mode")
	token = frappe.form_dict.get("hub.verify_token")
	challenge = frappe.form_dict.get("hub.challenge")

	if mode == "subscribe" and token == settings.meta_webhook_verify_token:
		# Must return the raw challenge string with a 200, nothing more --
		# no JSON wrapper, no download disposition. frappe.response.type =
		# "text" looks like it should do this but isn't actually a valid
		# key in Frappe's response_type_map (the closest real option, "txt",
		# forces a file-download Content-Disposition and needs a "doctype"
		# key that isn't set here) -- both crash with a 500 on this exact
		# code path. Returning a raw Response bypasses Frappe's response
		# builder entirely (see frappe.api.handle: `if isinstance(data,
		# Response): return data`), which is the actually-supported way to
		# hand back a bare value from a whitelisted method.
		return Response(challenge, status=200, mimetype="text/plain")
	return Response("Verification failed", status=403, mimetype="text/plain")


def _meta_receive():
	try:
		data = json.loads(frappe.request.data)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: bad Meta webhook payload")
		return {"ok": False}

	for entry in data.get("entry", []):
		for change in entry.get("changes", []):
			value = change.get("value", {})

			for msg in value.get("messages", []):
				_save_incoming_meta_message(msg, value)

			for status in value.get("statuses", []):
				_update_status_from_meta(status)

	return {"ok": True}


def _save_incoming_meta_message(msg, value):
	from_number = normalize_outbound_number(msg.get("from"))
	profile_name = None
	for contact in value.get("contacts", []):
		if contact.get("wa_id") == msg.get("from"):
			profile_name = contact.get("profile", {}).get("name")

	msg_type = msg.get("type", "text")
	text_body = ""
	content_type = "text"
	media_id = None
	media_filename_hint = None

	if msg_type == "text":
		text_body = msg.get("text", {}).get("body", "")
	elif msg_type in ("image", "document", "video", "audio"):
		content_type = msg_type
		media = msg.get(msg_type, {})
		text_body = media.get("caption", "")
		media_id = media.get("id")
		media_filename_hint = media.get("filename")  # only present for documents
	elif msg_type == "interactive":
		content_type = "interactive"
		interactive = msg.get("interactive", {})
		text_body = (
			interactive.get("button_reply", {}).get("title")
			or interactive.get("list_reply", {}).get("title")
			or ""
		)

	if frappe.db.exists("Whatsnext Message", {"provider_message_id": msg.get("id")}):
		return  # webhook can redeliver; avoid duplicates

	doc = frappe.get_doc({
		"doctype": "Whatsnext Message",
		"type": "Incoming",
		"provider": "Meta",
		"status": "Delivered",
		"from_number": from_number,
		"to_number": value.get("metadata", {}).get("display_phone_number"),
		"profile_name": profile_name,
		"message": text_body,
		"content_type": content_type,
		"provider_message_id": msg.get("id"),
		"conversation_id": from_number,
		"customer": resolve_customer_from_phone(from_number),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request, no request-level auto-commit to rely on

	if media_id:
		_download_and_attach_meta_media(doc, media_id, content_type, media_filename_hint)


def _download_and_attach_meta_media(doc, media_id, content_type, filename_hint=None):
	"""Runs after the message doc already exists so a media-download failure
	never loses the incoming message itself — worst case it's saved with no
	attachment and a logged error, not silently dropped."""
	try:
		import mimetypes

		from frappe.utils.file_manager import save_file
		from whatsnext.whatsnext.provider_engine import MetaProvider

		settings = frappe.get_cached_doc("Whatsnext Settings")
		provider = MetaProvider(settings)
		content, mime_type = provider.download_media(media_id)

		ext = mimetypes.guess_extension(mime_type) or ""
		fname = filename_hint or f"{content_type}_{media_id}{ext}"

		file_doc = save_file(fname, content, "Whatsnext Message", doc.name, is_private=1)
		doc.db_set("attach", file_doc.file_url, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext: failed to download Meta media {media_id} for {doc.name}")


def _update_status_from_meta(status):
	provider_message_id = status.get("id")
	new_status = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}.get(status.get("status"))
	if not (provider_message_id and new_status):
		return
	name = frappe.db.get_value("Whatsnext Message", {"provider_message_id": provider_message_id})
	if name:
		frappe.db.set_value("Whatsnext Message", name, "status", new_status)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request


# ---------------------------------------------------------------------------
# Twilio webhook
# POST /api/method/whatsnext.whatsnext.api.webhook.twilio_webhook       -> inbound messages
# POST /api/method/whatsnext.whatsnext.api.webhook.twilio_status_callback -> delivery status
# ---------------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["POST"])
def twilio_webhook():
	form = frappe.form_dict
	from_number = normalize_outbound_number((form.get("From") or "").replace("whatsapp:", ""))
	to_number = normalize_outbound_number((form.get("To") or "").replace("whatsapp:", ""))
	body = form.get("Body") or ""
	message_sid = form.get("MessageSid") or form.get("SmsSid")
	num_media = int(form.get("NumMedia") or 0)

	content_type = "text"
	attach = None
	if num_media:
		attach = form.get("MediaUrl0")
		content_type_hdr = form.get("MediaContentType0", "")
		if "image" in content_type_hdr:
			content_type = "image"
		elif "video" in content_type_hdr:
			content_type = "video"
		elif "audio" in content_type_hdr:
			content_type = "audio"
		else:
			content_type = "document"

	if message_sid and frappe.db.exists("Whatsnext Message", {"provider_message_id": message_sid}):
		return

	doc = frappe.get_doc({
		"doctype": "Whatsnext Message",
		"type": "Incoming",
		"provider": "Twilio",
		"status": "Delivered",
		"from_number": from_number,
		"to_number": to_number,
		"message": body,
		"content_type": content_type,
		"attach": attach,
		"provider_message_id": message_sid,
		"conversation_id": from_number,
		"customer": resolve_customer_from_phone(from_number),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request
	frappe.response.type = "text"
	return ""


@frappe.whitelist(allow_guest=True, methods=["POST"])
def twilio_status_callback():
	form = frappe.form_dict
	message_sid = form.get("MessageSid")
	status_map = {
		"queued": "Queued", "sent": "Sent", "delivered": "Delivered",
		"read": "Read", "failed": "Failed", "undelivered": "Failed",
	}
	new_status = status_map.get((form.get("MessageStatus") or "").lower())
	if message_sid and new_status:
		name = frappe.db.get_value("Whatsnext Message", {"provider_message_id": message_sid})
		if name:
			updates = {"status": new_status}
			if new_status == "Failed":
				updates["error_message"] = form.get("ErrorMessage") or f"Twilio error {form.get('ErrorCode', '')}"
			frappe.db.set_value("Whatsnext Message", name, updates)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request
	frappe.response.type = "text"
	return ""
