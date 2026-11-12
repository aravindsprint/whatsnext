import sys
import types
from unittest.mock import MagicMock

from whatsnext.whatsnext import automation
from whatsnext.whatsnext.api import webhook as wh


def test_handler_takes_message_and_skips_away_reply(frappe, monkeypatch):
	calls = []
	frappe.get_hooks = MagicMock(return_value=["app.one", "app.two"])
	handlers = {"app.one": lambda doc: calls.append("one") or False, "app.two": lambda doc: calls.append("two") or True}
	frappe.get_attr = lambda path: handlers[path]
	away = MagicMock()
	conv = types.ModuleType("whatsnext.whatsnext.conversations")
	conv.handle_opt_keywords = lambda doc: False
	conv.queue_away_reply = away
	monkeypatch.setitem(sys.modules, "whatsnext.whatsnext.conversations", conv)

	wh._handle_keywords(types.SimpleNamespace(name="M1"))
	assert calls == ["one", "two"]
	away.assert_not_called()


def test_no_handler_falls_through_to_away_reply(frappe, monkeypatch):
	frappe.get_hooks = MagicMock(return_value=[])
	away = MagicMock()
	conv = types.ModuleType("whatsnext.whatsnext.conversations")
	conv.handle_opt_keywords = lambda doc: False
	conv.queue_away_reply = away
	monkeypatch.setitem(sys.modules, "whatsnext.whatsnext.conversations", conv)

	wh._handle_keywords(types.SimpleNamespace(name="M1"))
	away.assert_called_once()


def test_opt_out_keyword_wins_over_handlers(frappe, monkeypatch):
	handler = MagicMock(return_value=True)
	frappe.get_hooks = MagicMock(return_value=["app.h"])
	frappe.get_attr = lambda path: handler
	conv = types.ModuleType("whatsnext.whatsnext.conversations")
	conv.handle_opt_keywords = lambda doc: True
	conv.queue_away_reply = MagicMock()
	monkeypatch.setitem(sys.modules, "whatsnext.whatsnext.conversations", conv)

	wh._handle_keywords(types.SimpleNamespace(name="M1"))
	handler.assert_not_called()


def test_broken_handler_is_logged_and_skipped(frappe):
	frappe.get_hooks = MagicMock(return_value=["bad", "good"])
	def bad(doc):
		raise RuntimeError("boom")
	frappe.get_attr = lambda path: bad if path == "bad" else (lambda doc: True)
	assert automation.run_incoming_handlers(types.SimpleNamespace(name="M1")) is True
	frappe.log_error.assert_called_once()


def test_meta_send_media_bytes_uploads_then_sends_by_id(frappe, monkeypatch):
	from whatsnext.whatsnext import provider_engine as pe

	posts = []

	class R:
		def __init__(self, body):
			self.status_code = 200
			self._b = body
			self.text = str(body)

		def json(self):
			return self._b

	def fake_post(url, headers=None, data=None, files=None, timeout=None, **k):
		posts.append({"url": url, "data": data, "files": files, "headers": headers})
		return R({"id": "MEDIA1"} if url.endswith("/media") else {"messages": [{"id": "wamid.1"}]})

	monkeypatch.setattr(pe.requests, "post", fake_post)
	p = pe.MetaProvider(frappe.settings)
	res = p.send_media_bytes("919876543210", b"OggS..", "audio/ogg", "audio", caption="ignored")

	assert posts[0]["url"] == "https://graph.facebook.com/v20.0/PNID/media"
	assert posts[0]["data"] == {"messaging_product": "whatsapp", "type": "audio/ogg"}
	assert posts[0]["files"]["file"][1] == b"OggS.."
	import json
	body = json.loads(posts[1]["data"])
	assert body["type"] == "audio" and body["audio"] == {"id": "MEDIA1"}  # no caption on audio
	assert res["messages"][0]["id"] == "wamid.1"


def test_twilio_cannot_send_bytes(frappe):
	import pytest
	from whatsnext.whatsnext import provider_engine as pe

	settings = frappe.settings
	settings.twilio_enabled = 1
	p = pe.TwilioProvider(settings)
	with pytest.raises(pe.WhatsAppSendError):
		p.send_media_bytes("9198", b"x", "audio/ogg", "audio")
