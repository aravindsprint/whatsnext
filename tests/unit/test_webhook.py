import base64
import hashlib
import hmac
import types

import pytest

from whatsnext.whatsnext.api import webhook as wh


@pytest.mark.parametrize("msg,expected", [
	({"type": "text", "text": {"body": "hello"}}, ("text", "hello", None, None)),
	({"type": "button", "button": {"text": "Yes, confirm", "payload": "Y"}}, ("interactive", "Yes, confirm", None, None)),
	({"type": "interactive", "interactive": {"button_reply": {"title": "Track"}}}, ("interactive", "Track", None, None)),
	({"type": "interactive", "interactive": {"list_reply": {"title": "Option 2"}}}, ("interactive", "Option 2", None, None)),
	({"type": "sticker", "sticker": {"id": "S1"}}, ("image", "", "S1", None)),
	({"type": "document", "document": {"id": "D1", "caption": "PO", "filename": "po.pdf"}}, ("document", "PO", "D1", "po.pdf")),
	({"type": "reaction", "reaction": {"emoji": "👍"}}, ("text", "Reacted 👍", None, None)),
	({"type": "reaction", "reaction": {}}, ("text", "Removed a reaction", None, None)),
	({"type": "order"}, ("text", "[Unsupported message type: order]", None, None)),
])
def test_parse_meta_message(msg, expected):
	assert wh._parse_meta_message(msg) == expected


def test_parse_location_and_contacts():
	ct, text, *_ = wh._parse_meta_message({"type": "location", "location": {"latitude": 11.1, "longitude": 77.3, "name": "Mill"}})
	assert ct == "location" and "q=11.1,77.3" in text and "Mill" in text
	_, text, *_ = wh._parse_meta_message({"type": "contacts", "contacts": [{"name": {"formatted_name": "Ravi"}, "phones": [{"phone": "+9199"}]}]})
	assert text == "👤 Shared contact: Ravi +9199"


def _request(body=b"", headers=None, path="/api/method/x", url="https://test.site/api/method/x", form=None):
	class Form(dict):
		def getlist(self, k):
			v = self[k]
			return v if isinstance(v, list) else [v]

	return types.SimpleNamespace(
		get_data=lambda: body, data=body, headers=headers or {}, path=path, url=url, form=Form(form or {}),
	)


def test_meta_signature(frappe):
	body = b'{"entry": []}'
	frappe.get_cached_doc.return_value.get_password = lambda k, raise_exception=True: "SECRET" if k == "meta_app_secret" else None
	good = "sha256=" + hmac.new(b"SECRET", body, hashlib.sha256).hexdigest()

	frappe.local.request = _request(body, {"X-Hub-Signature-256": good})
	assert wh._meta_signature_ok()
	frappe.local.request = _request(body, {"X-Hub-Signature-256": "sha256=deadbeef"})
	assert not wh._meta_signature_ok()
	frappe.local.request = _request(body, {})
	assert not wh._meta_signature_ok()


def test_meta_signature_skipped_without_secret(frappe):
	frappe.local.request = _request(b"{}", {})
	assert wh._meta_signature_ok()


def _twilio_sig(token, url, params):
	payload = "".join(f"{k}{params[k]}" for k in sorted(params))
	return base64.b64encode(hmac.new(token.encode(), (url + payload).encode(), hashlib.sha1).digest()).decode()


def test_twilio_signature(frappe):
	frappe.settings.twilio_verify_signature = 1
	params = {"From": "whatsapp:+919876543210", "Body": "hi", "MessageSid": "SM1"}
	url = "https://test.site/api/method/whatsnext.whatsnext.api.webhook.twilio_webhook"
	good = _twilio_sig("TWILIO_TOKEN", url, params)

	frappe.local.request = _request(headers={"X-Twilio-Signature": good}, url=url, form=params)
	assert wh._twilio_signature_ok()
	# Behind a TLS-terminating proxy the app may see http://
	frappe.local.request = _request(headers={"X-Twilio-Signature": good}, url=url.replace("https", "http"), form=params)
	assert wh._twilio_signature_ok()
	frappe.local.request = _request(headers={"X-Twilio-Signature": good}, url=url, form={**params, "Body": "tampered"})
	assert not wh._twilio_signature_ok()


def test_twilio_signature_off_by_default(frappe):
	frappe.local.request = _request(headers={}, form={})
	assert wh._twilio_signature_ok()


@pytest.mark.parametrize("current,new,applied", [
	("Sent", "Delivered", True),
	("Delivered", "Read", True),
	("Read", "Delivered", False),   # late receipt must not move backwards
	("Delivered", "Sent", False),
	("Sent", "Failed", True),
	("Read", "Failed", False),
	("Failed", "Delivered", False),
])
def test_status_updates_never_regress(frappe, monkeypatch, current, new, applied):
	row = frappe._dict(name="M1", status=current, conversation_id="91", type="Outgoing", customer=None,
	                   reference_doctype=None, reference_name=None)
	frappe.db.get_value.return_value = row
	import sys
	fake = types.ModuleType("whatsnext.whatsnext.doctype.whatsnext_message.whatsnext_message")
	fake.publish_message_event = lambda *a, **k: None
	monkeypatch.setitem(sys.modules, "whatsnext.whatsnext.doctype.whatsnext_message.whatsnext_message", fake)
	wh._apply_status_update("wamid.1", new)
	assert frappe.db.set_value.called == applied
