"""Unified WhatsApp provider engine.

Wraps Meta's WhatsApp Cloud API and Twilio's WhatsApp API behind one interface
so the rest of the app (api/__init__.py, notification_engine.py, scheduler.py)
never has to branch on provider directly. Add a new provider by subclassing
BaseProvider and registering it in get_provider().
"""

import json
import requests
import frappe


class WhatsAppSendError(Exception):
	pass


def get_settings():
	return frappe.get_cached_doc("Whatsnext Settings")


def get_provider(provider_name: str | None = None):
	settings = get_settings()
	name = provider_name or settings.default_provider
	if name == "Twilio":
		return TwilioProvider(settings)
	return MetaProvider(settings)


def _json_or_error(resp) -> dict:
	"""Provider error pages (gateway timeouts, proxies, outages) aren't
	always JSON; resp.json() then raised a bare decode error that hid the
	real HTTP status."""
	try:
		return resp.json()
	except ValueError:
		if resp.status_code >= 400:
			raise WhatsAppSendError(f"HTTP {resp.status_code}: {(resp.text or '')[:200]}")
		return {}


def _ordered_values(params: dict) -> list:
	"""Template variables in {{1}}, {{2}}, ... order. Meta matches body
	parameters by position, so relying on dict insertion order sent values
	into the wrong slots whenever a notification's field mapping rows weren't
	entered in numeric order."""
	def key(k):
		k = str(k).strip("{} ")
		return (0, int(k)) if k.isdigit() else (1, k)

	return [params[k] for k in sorted(params, key=key)]


def meta_template_name(name: str) -> str:
	"""Meta template names: lowercase letters, digits and underscores. Local
	template names may contain spaces/capitals ("Order Update"); the copy
	submitted to Meta is "order_update", so sends must use the same form."""
	import re

	slug = re.sub(r"[^a-z0-9_]+", "_", (name or "").lower()).strip("_")
	return re.sub(r"_+", "_", slug)[:512]


def _meta_name_for(template: str) -> str:
	"""The template's exact name on Meta: stored meta_name when known
	(synced/submitted templates, including language variants), else the
	Meta-safe form of the local name."""
	stored = frappe.db.get_value("Whatsnext Message Template", template, "meta_name")
	return stored or meta_template_name(template)


def split_template_params(params: dict | None):
	"""Template parameters arrive as one flat dict: "1", "2"... fill the
	body, "header_1" fills a text header's {{1}}, and "button_<index>" fills
	the {{1}} suffix of the URL button at that (0-based) position."""
	body, header, buttons = {}, None, {}
	for k, v in (params or {}).items():
		k = str(k)
		if k == "header_1":
			header = v
		elif k.startswith("button_") and k[7:].isdigit():
			buttons[int(k[7:])] = v
		else:
			body[k] = v
	return body, header, buttons


class BaseProvider:
	name = "Base"

	def __init__(self, settings):
		self.settings = settings

	def send_text(self, to: str, body: str) -> dict:
		raise NotImplementedError

	def send_template(self, to: str, template, params: dict, lang: str = "en",
	                   header_media_url: str | None = None, header_type: str | None = None) -> dict:
		raise NotImplementedError

	def send_media(self, to: str, media_url: str, media_type: str, caption: str = "") -> dict:
		raise NotImplementedError


class MetaProvider(BaseProvider):
	name = "Meta"

	def __init__(self, settings):
		super().__init__(settings)
		if not settings.meta_enabled:
			frappe.throw("Meta WhatsApp Cloud API is not enabled in Whatsnext Settings.")
		self.phone_number_id = settings.meta_phone_number_id
		self.token = settings.get_password("meta_access_token")
		self.version = settings.meta_api_version or "v20.0"
		self.base_url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"

	def _headers(self):
		return {
			"Authorization": f"Bearer {self.token}",
			"Content-Type": "application/json",
		}

	def _post(self, payload: dict) -> dict:
		resp = requests.post(self.base_url, headers=self._headers(), data=json.dumps(payload), timeout=30)
		data = _json_or_error(resp)
		if resp.status_code >= 400:
			raise WhatsAppSendError(data.get("error", {}).get("message", str(data)))
		return data

	def send_text(self, to, body):
		payload = {
			"messaging_product": "whatsapp",
			"to": to,
			"type": "text",
			"text": {"body": body},
		}
		return self._post(payload)

	def send_template(self, to, template, params, lang="en", header_media_url=None, header_type=None):
		body_params, header_param, button_params = split_template_params(params)
		components = []
		if header_type and header_type not in ("None", "Text") and header_media_url:
			media_key = header_type.lower()  # image, video, document
			components.append({
				"type": "header",
				"parameters": [{"type": media_key, media_key: {"link": header_media_url}}],
			})
		elif header_param not in (None, ""):
			components.append({
				"type": "header",
				"parameters": [{"type": "text", "text": str(header_param)}],
			})
		if body_params:
			components.append({
				"type": "body",
				"parameters": [{"type": "text", "text": str(v)} for v in _ordered_values(body_params)],
			})
		for index in sorted(button_params):
			components.append({
				"type": "button",
				"sub_type": "url",
				"index": str(index),
				"parameters": [{"type": "text", "text": str(button_params[index])}],
			})
		payload = {
			"messaging_product": "whatsapp",
			"to": to,
			"type": "template",
			"template": {
				"name": _meta_name_for(template),
				"language": {"code": lang or "en"},
				"components": components,
			},
		}
		return self._post(payload)

	def send_media(self, to, media_url, media_type, caption=""):
		payload = {
			"messaging_product": "whatsapp",
			"to": to,
			"type": media_type,
			media_type: {"link": media_url, **({"caption": caption} if caption else {})},
		}
		return self._post(payload)

	def mark_read(self, message_id: str) -> dict:
		"""Read receipt: the customer sees blue ticks on this message and
		every earlier one in the chat."""
		return self._post({"messaging_product": "whatsapp", "status": "read", "message_id": message_id})

	def test_connection(self) -> dict:
		"""Lightweight credential check: fetch the phone number's own
		metadata. Succeeds only if phone_number_id + token are both valid."""
		url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}"
		resp = requests.get(url, headers=self._headers(), params={"fields": "verified_name,display_phone_number,quality_rating"}, timeout=15)
		data = _json_or_error(resp)
		if resp.status_code >= 400:
			raise WhatsAppSendError(data.get("error", {}).get("message", str(data)))
		return {
			"verified_name": data.get("verified_name"),
			"display_phone_number": data.get("display_phone_number"),
			"quality_rating": data.get("quality_rating"),
		}

	def fetch_templates(self):
		"""Pull approved/pending templates from Meta so the local template
		library can reflect real approval_status."""
		url = f"https://graph.facebook.com/{self.version}/{self.settings.meta_waba_id}/message_templates"
		params = {"limit": 100}
		templates = []
		# Meta pages this endpoint (default 25 per page); without following
		# paging.next, templates beyond the first page were never synced.
		while url:
			resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
			resp.raise_for_status()
			data = resp.json()
			templates.extend(data.get("data", []))
			url = (data.get("paging") or {}).get("next")
			params = None  # the "next" URL already carries its own query string
		return templates

	def upload_example_media(self, content: bytes, mime_type: str) -> str:
		"""Resumable Upload API: media-header templates must be submitted
		with an example file handle. Needs the App ID from Settings."""
		app_id = self.settings.meta_app_id
		if not app_id:
			raise WhatsAppSendError("Set the Meta App ID in Whatsnext Settings to submit templates with a media header.")
		base = f"https://graph.facebook.com/{self.version}"
		resp = requests.post(
			f"{base}/{app_id}/uploads",
			params={"file_length": len(content), "file_type": mime_type},
			headers={"Authorization": f"Bearer {self.token}"},
			timeout=30,
		)
		session = _json_or_error(resp)
		if resp.status_code >= 400 or not session.get("id"):
			raise WhatsAppSendError((session.get("error") or {}).get("message", str(session)))
		resp = requests.post(
			f"{base}/{session['id']}",
			headers={"Authorization": f"OAuth {self.token}", "file_offset": "0"},
			data=content,
			timeout=120,
		)
		result = _json_or_error(resp)
		if resp.status_code >= 400 or not result.get("h"):
			raise WhatsAppSendError((result.get("error") or {}).get("message", str(result)))
		return result["h"]

	def create_template(self, payload: dict) -> dict:
		url = f"https://graph.facebook.com/{self.version}/{self.settings.meta_waba_id}/message_templates"
		resp = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=30)
		data = _json_or_error(resp)
		if resp.status_code >= 400:
			err = data.get("error", {})
			raise WhatsAppSendError(err.get("error_user_msg") or err.get("message") or str(data))
		return data

	def edit_template(self, template_id: str, payload: dict) -> dict:
		resp = requests.post(
			f"https://graph.facebook.com/{self.version}/{template_id}",
			headers=self._headers(), data=json.dumps(payload), timeout=30,
		)
		data = _json_or_error(resp)
		if resp.status_code >= 400:
			err = data.get("error", {})
			raise WhatsAppSendError(err.get("error_user_msg") or err.get("message") or str(data))
		return data

	def get_media_metadata(self, media_id: str) -> dict:
		"""Step 1 of Meta's two-step media download: resolve a media id to a
		short-lived (~5 min) signed URL plus mime type / size."""
		url = f"https://graph.facebook.com/{self.version}/{media_id}"
		resp = requests.get(url, headers=self._headers(), timeout=30)
		resp.raise_for_status()
		return resp.json()

	def download_media(self, media_id: str) -> tuple[bytes, str]:
		"""Step 2: fetch the actual bytes from the signed URL. The signed URL
		still requires the same bearer token — it is not a public link."""
		meta = self.get_media_metadata(media_id)
		media_url = meta.get("url")
		if not media_url:
			frappe.throw(f"Meta did not return a media URL for id {media_id}")
		resp = requests.get(media_url, headers=self._headers(), timeout=60)
		resp.raise_for_status()
		return resp.content, meta.get("mime_type", "application/octet-stream")


class TwilioProvider(BaseProvider):
	name = "Twilio"

	def __init__(self, settings):
		super().__init__(settings)
		if not settings.twilio_enabled:
			frappe.throw("Twilio is not enabled in Whatsnext Settings.")
		self.account_sid = settings.twilio_account_sid
		self.auth_token = settings.get_password("twilio_auth_token")
		self.from_number = settings.twilio_whatsapp_number
		self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

	@staticmethod
	def _wa(number: str) -> str:
		return number if number.startswith("whatsapp:") else f"whatsapp:{number}"

	def _post(self, data: dict) -> dict:
		resp = requests.post(self.base_url, data=data, auth=(self.account_sid, self.auth_token), timeout=30)
		payload = _json_or_error(resp)
		if resp.status_code >= 400:
			raise WhatsAppSendError(payload.get("message", str(payload)))
		return payload

	def send_text(self, to, body):
		return self._post({
			"From": self._wa(self.from_number),
			"To": self._wa(to),
			"Body": body,
		})

	def send_template(self, to, template, params, lang="en", header_media_url=None, header_type=None):
		# header_media_url/header_type are accepted for interface parity with
		# MetaProvider but unused here — Twilio Content API templates carry
		# their media as part of the Content SID definition itself.
		# Twilio Content API templates are referenced by Content SID, stored
		# on Whatsnext Message Template.twilio_content_sid
		doc = frappe.get_doc("Whatsnext Message Template", template)
		if not doc.twilio_content_sid:
			frappe.throw(f"Template '{template}' has no Twilio Content SID configured.")
		data = {
			"From": self._wa(self.from_number),
			"To": self._wa(to),
			"ContentSid": doc.twilio_content_sid,
		}
		body_params, _, _ = split_template_params(params)
		if body_params:
			data["ContentVariables"] = json.dumps({str(k): str(v) for k, v in body_params.items()})
		return self._post(data)

	def send_media(self, to, media_url, media_type, caption=""):
		return self._post({
			"From": self._wa(self.from_number),
			"To": self._wa(to),
			"Body": caption,
			"MediaUrl": media_url,
		})

	def test_connection(self) -> dict:
		"""Lightweight credential check: fetch the Twilio account's own
		details. Succeeds only if account_sid + auth_token are both valid."""
		url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}.json"
		resp = requests.get(url, auth=(self.account_sid, self.auth_token), timeout=15)
		data = _json_or_error(resp)
		if resp.status_code >= 400:
			raise WhatsAppSendError(data.get("message", str(data)))
		return {
			"friendly_name": data.get("friendly_name"),
			"status": data.get("status"),
		}
