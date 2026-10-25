import json
from unittest.mock import MagicMock

import pytest

from whatsnext.whatsnext import provider_engine as pe


class FakeResponse:
	def __init__(self, status=200, data=None, text=None):
		self.status_code = status
		self._data = data
		self.text = text if text is not None else json.dumps(data or {})

	def json(self):
		if self._data is None:
			raise ValueError("not json")
		return self._data


@pytest.fixture
def meta(frappe, monkeypatch):
	frappe.db.get_value.return_value = None  # no stored meta_name
	post = MagicMock(return_value=FakeResponse(200, {"messages": [{"id": "wamid.1"}]}))
	monkeypatch.setattr(pe.requests, "post", post)
	return pe.MetaProvider(frappe.settings), post


def sent_payload(post):
	return json.loads(post.call_args.kwargs["data"])


def test_ordered_values_numeric_order():
	assert pe._ordered_values({"10": "j", "2": "b", "1": "a"}) == ["a", "b", "j"]


def test_split_template_params():
	body, header, buttons = pe.split_template_params({"1": "a", "header_1": "H", "button_0": "x", "2": "b"})
	assert body == {"1": "a", "2": "b"}
	assert header == "H"
	assert buttons == {0: "x"}


@pytest.mark.parametrize("local,expected", [
	("Order Update", "order_update"),
	("order_update", "order_update"),
	("Invoice - v2!", "invoice_v2"),
])
def test_meta_template_name(local, expected):
	assert pe.meta_template_name(local) == expected


def test_template_payload_has_header_body_button_and_context(meta):
	provider, post = meta
	provider.send_template(
		"919876543210", "Order Update", {"2": "SO-1", "1": "Ravi", "header_1": "Hi", "button_1": "SO-1"},
		"en", header_type="Text", context_id="wamid.prev",
	)
	p = sent_payload(post)
	assert p["template"]["name"] == "order_update"
	comps = p["template"]["components"]
	assert comps[0] == {"type": "header", "parameters": [{"type": "text", "text": "Hi"}]}
	assert comps[1]["parameters"] == [{"type": "text", "text": "Ravi"}, {"type": "text", "text": "SO-1"}]
	assert comps[2] == {"type": "button", "sub_type": "url", "index": "1", "parameters": [{"type": "text", "text": "SO-1"}]}
	assert p["context"] == {"message_id": "wamid.prev"}


def test_template_uses_stored_meta_name(meta, frappe):
	provider, post = meta
	frappe.db.get_value.return_value = "order_update"  # e.g. local name order_update_ta
	provider.send_template("919876543210", "order_update_ta", {}, "ta")
	p = sent_payload(post)
	assert p["template"]["name"] == "order_update"
	assert p["template"]["language"] == {"code": "ta"}


def test_media_header(meta):
	provider, post = meta
	provider.send_template("91", "promo", {}, "en", header_media_url="https://x/a.jpg", header_type="Image")
	assert sent_payload(post)["template"]["components"][0] == {
		"type": "header", "parameters": [{"type": "image", "image": {"link": "https://x/a.jpg"}}],
	}


def test_audio_has_no_caption(meta):
	provider, post = meta
	provider.send_media("91", "https://x/a.ogg", "audio", "ignored")
	assert "caption" not in sent_payload(post)["audio"]


def test_location_and_contacts_payloads(meta):
	provider, post = meta
	provider.send_location("91", "11.1", "77.3", "Mill", "Tirupur")
	assert sent_payload(post)["location"] == {"latitude": 11.1, "longitude": 77.3, "name": "Mill", "address": "Tirupur"}
	provider.send_contacts("91", [{"name": "Ravi Kumar", "phones": ["+9198"], "emails": ["r@x.in"], "company": "PSS"}])
	c = sent_payload(post)["contacts"][0]
	assert c["name"] == {"formatted_name": "Ravi Kumar", "first_name": "Ravi", "last_name": "Kumar"}
	assert c["phones"] == [{"phone": "+9198", "type": "CELL"}]
	assert c["org"] == {"company": "PSS"}


def test_non_json_error_reports_http_status(meta, monkeypatch):
	provider, _ = meta
	monkeypatch.setattr(pe.requests, "post", MagicMock(return_value=FakeResponse(502, None, "<html>Bad gateway</html>")))
	with pytest.raises(pe.WhatsAppSendError, match="HTTP 502"):
		provider.send_text("91", "hi")


def test_meta_error_message_surfaces(meta, monkeypatch):
	provider, _ = meta
	monkeypatch.setattr(pe.requests, "post", MagicMock(return_value=FakeResponse(400, {"error": {"message": "Bad number"}})))
	with pytest.raises(pe.WhatsAppSendError, match="Bad number"):
		provider.send_text("91", "hi")


def test_twilio_content_variables_body_only(frappe, monkeypatch):
	frappe.settings.twilio_enabled = 1
	post = MagicMock(return_value=FakeResponse(201, {"sid": "SM1"}))
	monkeypatch.setattr(pe.requests, "post", post)
	tpl = MagicMock(twilio_content_sid="HX123")
	monkeypatch.setattr(frappe, "get_doc", MagicMock(return_value=tpl), raising=False)
	pe.TwilioProvider(frappe.settings).send_template("919876543210", "t", {"1": "a", "header_1": "h", "button_0": "b"})
	data = post.call_args.kwargs["data"]
	assert data["ContentSid"] == "HX123"
	assert json.loads(data["ContentVariables"]) == {"1": "a"}
	assert data["To"] == "whatsapp:+919876543210"


def test_disabled_provider_refuses(frappe):
	frappe.settings.meta_enabled = 0
	with pytest.raises(frappe.ValidationError):
		pe.MetaProvider(frappe.settings)


@pytest.mark.parametrize("raw,expected", [
	("919876543210", "whatsapp:+919876543210"),   # how numbers are stored
	("+919876543210", "whatsapp:+919876543210"),
	("whatsapp:+14155238886", "whatsapp:+14155238886"),
	("whatsapp:14155238886", "whatsapp:+14155238886"),
	("+1 (415) 523-8886", "whatsapp:+14155238886"),
])
def test_twilio_numbers_are_e164(raw, expected):
	assert pe.TwilioProvider._wa(raw) == expected


def test_twilio_text_send_uses_plus(frappe, monkeypatch):
	frappe.settings.twilio_enabled = 1
	post = MagicMock(return_value=FakeResponse(201, {"sid": "SM1"}))
	monkeypatch.setattr(pe.requests, "post", post)
	pe.TwilioProvider(frappe.settings).send_text("919876543210", "hi")
	assert post.call_args.kwargs["data"]["To"] == "whatsapp:+919876543210"
