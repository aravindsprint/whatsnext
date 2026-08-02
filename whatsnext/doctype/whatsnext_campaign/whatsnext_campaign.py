import frappe
from frappe.model.document import Document


class WhatsnextCampaign(Document):
	def validate(self):
		self.total_recipients = len(self.recipients)
