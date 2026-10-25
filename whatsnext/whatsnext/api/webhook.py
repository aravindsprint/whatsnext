import hashlib
import hmac
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


def _meta_signature_ok() -> bool:
	"""Meta signs every webhook POST with the App Secret
	(X-Hub-Signature-256: sha256=<hmac>). Without this check anyone who
	learns the URL can inject fake incoming messages. Enforced once an App
	Secret is configured in Whatsnext Settings."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	secret = settings.get_password("meta_app_secret", raise_exception=False)
	if not secret:
		return True
	header = frappe.get_request_header("X-Hub-Signature-256") or ""
	if not header.startswith("sha256="):
		return False
	expected = hmac.new(secret.encode(), frappe.request.get_data() or b"", hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, header.split("=", 1)[1])


def _meta_receive():
	if not _meta_signature_ok():
		frappe.log_error("Rejected a Meta webhook with a missing or invalid signature.", "Whatsnext: webhook signature")
		return Response("Invalid signature", status=403, mimetype="text/plain")

	try:
		data = json.loads(frappe.request.data)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: bad Meta webhook payload")
		return {"ok": False}

	for entry in data.get("entry", []):
		for change in entry.get("changes", []):
			value = change.get("value", {})

			if change.get("field") == "message_template_status_update":
				_update_template_status(value)
				continue

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

	content_type, text_body, media_id, media_filename_hint = _parse_meta_message(msg)

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
		# The customer swiped to reply to one of our messages (or theirs).
		"reply_to": _local_message_for((msg.get("context") or {}).get("id")),
		"customer": resolve_customer_from_phone(from_number),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request, no request-level auto-commit to rely on

	if media_id:
		_download_and_attach_meta_media(doc, media_id, content_type, media_filename_hint)

	_handle_keywords(doc)


def _handle_keywords(doc):
	"""Opt-out/opt-in keywords first; any other message may get the
	outside-business-hours away reply."""
	handled = False
	try:
		from whatsnext.whatsnext.conversations import handle_opt_keywords

		handled = handle_opt_keywords(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: opt-out keyword handling failed")
	if handled:
		return
	try:
		from whatsnext.whatsnext.conversations import queue_away_reply

		queue_away_reply(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: away reply check failed")


def _parse_meta_message(msg):
	"""Returns (content_type, text, media_id, filename). Covers every inbound
	type Meta sends. Template quick-reply taps arrive as type "button" (not
	"interactive"), and location/contacts/sticker/reaction messages used to
	be stored with no text at all -- blank bubbles in the chat."""
	msg_type = msg.get("type", "text")
	content_type, text, media_id, filename = "text", "", None, None

	if msg_type == "text":
		text = msg.get("text", {}).get("body", "")
	elif msg_type in ("image", "document", "video", "audio", "sticker"):
		media = msg.get(msg_type, {})
		content_type = "image" if msg_type == "sticker" else msg_type
		text = media.get("caption", "")
		media_id = media.get("id")
		filename = media.get("filename")  # only present for documents
	elif msg_type == "button":
		content_type = "interactive"
		text = msg.get("button", {}).get("text") or msg.get("button", {}).get("payload", "")
	elif msg_type == "interactive":
		content_type = "interactive"
		interactive = msg.get("interactive", {})
		text = (
			interactive.get("button_reply", {}).get("title")
			or interactive.get("list_reply", {}).get("title")
			or ""
		)
		if not text and interactive.get("nfm_reply"):
			text = interactive["nfm_reply"].get("body") or "Submitted a form"
	elif msg_type == "location":
		content_type = "location"
		loc = msg.get("location", {})
		label = " — ".join(x for x in (loc.get("name"), loc.get("address")) if x)
		text = f"📍 {label + ' ' if label else ''}https://maps.google.com/?q={loc.get('latitude')},{loc.get('longitude')}"
	elif msg_type == "contacts":
		parts = []
		for c in msg.get("contacts", []):
			name = (c.get("name") or {}).get("formatted_name") or ""
			phones = ", ".join(p.get("phone", "") for p in c.get("phones", []))
			parts.append(f"{name} {phones}".strip())
		text = "👤 Shared contact: " + "; ".join(parts)
	elif msg_type == "reaction":
		emoji = msg.get("reaction", {}).get("emoji")
		text = f"Reacted {emoji}" if emoji else "Removed a reaction"
	else:
		text = f"[Unsupported message type: {msg_type}]"

	return content_type, text, media_id, filename


def _update_template_status(value):
	"""Meta's message_template_status_update webhook: reflect approvals and
	rejections immediately instead of waiting for the nightly refresh."""
	template_id = str(value.get("message_template_id") or "")
	status = {"APPROVED": "Approved", "PENDING": "Pending", "REJECTED": "Rejected"}.get(
		(value.get("event") or "").upper()
	)
	if not (template_id and status):
		return
	name = frappe.db.get_value("Whatsnext Message Template", {"meta_template_id": template_id})
	if not name:
		return
	reason = value.get("reason")
	frappe.db.set_value(
		"Whatsnext Message Template", name,
		{"approval_status": status, "rejection_reason": reason if status == "Rejected" and reason != "NONE" else ""},
	)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request


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
	error = None
	if new_status == "Failed":
		e = (status.get("errors") or [{}])[0]
		error = (e.get("error_data") or {}).get("details") or e.get("message") or e.get("title") or "Meta reported delivery failure"
	_apply_status_update(provider_message_id, new_status, error)


# Delivery receipts can arrive out of order (a "delivered" webhook landing
# after "read", or a late "sent"); applying them blindly moved messages
# backwards, e.g. Read -> Delivered.
_STATUS_RANK = {"Pending": 0, "Queued": 1, "Sent": 2, "Delivered": 3, "Read": 4}


def _apply_status_update(provider_message_id, new_status, error=None):
	row = frappe.db.get_value(
		"Whatsnext Message", {"provider_message_id": provider_message_id},
		["name", "status", "conversation_id", "type", "customer", "reference_doctype", "reference_name"],
		as_dict=True,
	)
	if not row:
		return

	current = row.status or "Pending"
	if new_status == "Failed":
		if current in ("Delivered", "Read"):
			return
	elif current == "Failed" or _STATUS_RANK.get(new_status, 0) <= _STATUS_RANK.get(current, 0):
		return

	updates = {"status": new_status}
	if error:
		updates["error_message"] = str(error)[:140]
	frappe.db.set_value("Whatsnext Message", row.name, updates)

	if new_status == "Failed" and row.type == "Outgoing":
		from whatsnext.whatsnext.conversations import record_outgoing_failed

		record_outgoing_failed(row.conversation_id)

	if row.reference_doctype == "Whatsnext Campaign" and row.reference_name:
		_update_campaign_recipient(row.reference_name, row.name, new_status, error)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request

	# Status changes bypass document hooks (db.set_value), so tell open
	# chats directly -- otherwise tick marks never updated live.
	from whatsnext.whatsnext.doctype.whatsnext_message.whatsnext_message import publish_message_event

	row.status = new_status
	publish_message_event(row, event="whatsnext_message_update")


def _update_campaign_recipient(campaign, message_name, new_status, error=None):
	"""Carry delivery receipts through to the campaign's recipient row and
	counters -- delivered_count was otherwise never updated after a send."""
	recipient = frappe.db.get_value(
		"Whatsnext Campaign Recipient", {"parent": campaign, "message": message_name}, "name"
	)
	if not recipient:
		return
	updates = {"status": new_status}
	if error:
		updates["error_message"] = str(error)[:140]
	frappe.db.set_value("Whatsnext Campaign Recipient", recipient, updates, update_modified=False)

	counts = dict(frappe.db.sql(
		"""SELECT status, COUNT(*) FROM `tabWhatsnext Campaign Recipient`
		WHERE parent = %s AND parenttype = 'Whatsnext Campaign' GROUP BY status""",
		(campaign,),
	))
	delivered = counts.get("Delivered", 0) + counts.get("Read", 0)
	frappe.db.set_value(
		"Whatsnext Campaign", campaign,
		{
			"delivered_count": delivered,
			"failed_count": counts.get("Failed", 0),
			"sent_count": counts.get("Sent", 0) + delivered,
		},
		update_modified=False,
	)


# ---------------------------------------------------------------------------
# Twilio webhook
# POST /api/method/whatsnext.whatsnext.api.webhook.twilio_webhook       -> inbound messages
# POST /api/method/whatsnext.whatsnext.api.webhook.twilio_status_callback -> delivery status
# ---------------------------------------------------------------------------
def _twilio_signature_ok() -> bool:
	"""Validates X-Twilio-Signature (HMAC-SHA1 over the full URL plus the
	sorted POST params, keyed with the Auth Token). Opt-in via Settings,
	since the URL must match exactly what's configured in Twilio; both the
	http and https forms are accepted to tolerate TLS-terminating proxies."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.twilio_verify_signature:
		return True
	token = settings.get_password("twilio_auth_token", raise_exception=False)
	signature = frappe.get_request_header("X-Twilio-Signature") or ""
	if not (token and signature):
		return False

	import base64

	params = frappe.request.form
	payload = "".join(f"{k}{v}" for k in sorted(params) for v in params.getlist(k))
	url = frappe.request.url
	candidates = {url, url.replace("http://", "https://", 1)}
	for candidate in candidates:
		digest = hmac.new(token.encode(), (candidate + payload).encode(), hashlib.sha1).digest()
		if hmac.compare_digest(base64.b64encode(digest).decode(), signature):
			return True
	return False


@frappe.whitelist(allow_guest=True, methods=["POST"])
def twilio_webhook():
	if not _twilio_signature_ok():
		frappe.log_error("Rejected a Twilio webhook with a missing or invalid signature.", "Whatsnext: webhook signature")
		return Response("Invalid signature", status=403, mimetype="text/plain")

	form = frappe.form_dict
	from_number = normalize_outbound_number((form.get("From") or "").replace("whatsapp:", ""))
	to_number = normalize_outbound_number((form.get("To") or "").replace("whatsapp:", ""))
	body = form.get("Body") or ""
	message_sid = form.get("MessageSid") or form.get("SmsSid")
	num_media = int(form.get("NumMedia") or 0)

	content_type = "text"
	media_url = None
	media_mime = ""
	if num_media:
		media_url = form.get("MediaUrl0")
		media_mime = form.get("MediaContentType0", "")
		if "image" in media_mime:
			content_type = "image"
		elif "video" in media_mime:
			content_type = "video"
		elif "audio" in media_mime:
			content_type = "audio"
		else:
			content_type = "document"
	elif form.get("Latitude") and form.get("Longitude"):
		content_type = "location"
		label = form.get("Address") or form.get("Label") or ""
		body = f"📍 {label + ' ' if label else ''}https://maps.google.com/?q={form.get('Latitude')},{form.get('Longitude')}"
	elif form.get("ButtonText") or form.get("ButtonPayload"):
		content_type = "interactive"
		body = form.get("ButtonText") or form.get("ButtonPayload")

	if message_sid and frappe.db.exists("Whatsnext Message", {"provider_message_id": message_sid}):
		return _twiml_ok()

	doc = frappe.get_doc({
		"doctype": "Whatsnext Message",
		"type": "Incoming",
		"provider": "Twilio",
		"status": "Delivered",
		"from_number": from_number,
		"to_number": to_number,
		"profile_name": form.get("ProfileName"),
		"message": body,
		"content_type": content_type,
		"provider_message_id": message_sid,
		"conversation_id": from_number,
		"reply_to": _local_message_for(form.get("OriginalRepliedMessageSid")),
		"customer": resolve_customer_from_phone(from_number),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request

	if media_url:
		_download_and_attach_twilio_media(doc, media_url, media_mime, content_type)

	_handle_keywords(doc)
	return _twiml_ok()


def _download_and_attach_twilio_media(doc, media_url, mime_type, content_type):
	"""Twilio media URLs require the account's credentials to fetch, so a
	stored link never displayed in the chat. Download it once and keep it as
	a private File attached to the message, like Meta media."""
	try:
		import mimetypes

		import requests
		from frappe.utils.file_manager import save_file

		settings = frappe.get_cached_doc("Whatsnext Settings")
		resp = requests.get(
			media_url,
			auth=(settings.twilio_account_sid, settings.get_password("twilio_auth_token")),
			timeout=60,
		)
		resp.raise_for_status()
		ext = mimetypes.guess_extension((mime_type or "").split(";")[0]) or ""
		fname = f"{content_type}_{doc.provider_message_id or doc.name}{ext}"
		file_doc = save_file(fname, resp.content, "Whatsnext Message", doc.name, is_private=1)
		doc.db_set("attach", file_doc.file_url, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Whatsnext: failed to download Twilio media for {doc.name}")
		# Keep the link so the media isn't lost entirely.
		doc.db_set("attach", media_url, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- webhook request


def _local_message_for(provider_message_id):
	if not provider_message_id:
		return None
	return frappe.db.get_value("Whatsnext Message", {"provider_message_id": provider_message_id}, "name")


def _twiml_ok():
	"""Empty TwiML reply. `frappe.response.type = "text"` isn't a valid
	Frappe response type (see _meta_verify above), so both Twilio endpoints
	answered every webhook with a 500 and Twilio logged errors/retried. A raw
	Response bypasses Frappe's response builder."""
	return Response("<Response></Response>", status=200, mimetype="text/xml")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def twilio_status_callback():
	if not _twilio_signature_ok():
		return Response("Invalid signature", status=403, mimetype="text/plain")
	form = frappe.form_dict
	message_sid = form.get("MessageSid")
	status_map = {
		"queued": "Queued", "sent": "Sent", "delivered": "Delivered",
		"read": "Read", "failed": "Failed", "undelivered": "Failed",
	}
	new_status = status_map.get((form.get("MessageStatus") or "").lower())
	if message_sid and new_status:
		error = None
		if new_status == "Failed":
			error = form.get("ErrorMessage") or f"Twilio error {form.get('ErrorCode', '')}"
		_apply_status_update(message_sid, new_status, error)
	return _twiml_ok()
