import frappe
from frappe.model.document import Document


class WhatsnextSettings(Document):
	def validate(self):
		if self.meta_enabled and not (
			self.meta_phone_number_id and self.get_password("meta_access_token", raise_exception=False)
		):
			frappe.throw("Phone Number ID and Access Token are required when Meta Cloud API is enabled.")
		if self.twilio_enabled and not (
			self.twilio_account_sid
			and self.get_password("twilio_auth_token", raise_exception=False)
			and self.twilio_whatsapp_number
		):
			frappe.throw("Account SID, Auth Token and WhatsApp Number are required when Twilio is enabled.")

	def on_update(self):
		# Password fields are wiped from the response on client-facing GETs;
		# nothing else to do here, kept for future cache-busting of provider config.
		frappe.cache().delete_value("whatsnext_settings")
