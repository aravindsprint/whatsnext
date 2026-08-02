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


class BaseProvider:
	name = "Base"

	def __init__(self, settings):
		self.settings = settings

	def send_text(self, to: str, body: str) -> dict:
		raise NotImplementedError

	def send_template(self, to: str, template, params: dict, lang: str = "en") -> dict:
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
		data = resp.json()
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

	def send_template(self, to, template, params, lang="en"):
		components = []
		if params:
			components.append({
				"type": "body",
				"parameters": [{"type": "text", "text": str(v)} for v in params.values()],
			})
		payload = {
			"messaging_product": "whatsapp",
			"to": to,
			"type": "template",
			"template": {
				"name": template,
				"language": {"code": lang},
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

	def fetch_templates(self):
		"""Pull approved/pending templates from Meta so the local template
		library can reflect real approval_status."""
		url = f"https://graph.facebook.com/{self.version}/{self.settings.meta_waba_id}/message_templates"
		resp = requests.get(url, headers=self._headers(), timeout=30)
		resp.raise_for_status()
		return resp.json().get("data", [])

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
		payload = resp.json()
		if resp.status_code >= 400:
			raise WhatsAppSendError(payload.get("message", str(payload)))
		return payload

	def send_text(self, to, body):
		return self._post({
			"From": self._wa(self.from_number),
			"To": self._wa(to),
			"Body": body,
		})

	def send_template(self, to, template, params, lang="en"):
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
		if params:
			data["ContentVariables"] = json.dumps(params)
		return self._post(data)

	def send_media(self, to, media_url, media_type, caption=""):
		return self._post({
			"From": self._wa(self.from_number),
			"To": self._wa(to),
			"Body": caption,
			"MediaUrl": media_url,
		})
