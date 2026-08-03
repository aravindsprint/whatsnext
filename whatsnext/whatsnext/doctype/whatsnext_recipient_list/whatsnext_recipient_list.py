from frappe.model.document import Document


class WhatsnextRecipientList(Document):
	def validate(self):
		self.recipient_count = len(self.recipients)
