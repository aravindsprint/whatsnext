import frappe
from frappe.model.document import Document


class WhatsnextMessage(Document):
	def before_insert(self):
		if not self.conversation_id:
			# Group by reference_name if we have one, else by counterpart number
			self.conversation_id = self.reference_name or self.to_number or self.from_number

	def after_insert(self):
		frappe.publish_realtime(
			event="whatsnext_new_message",
			message={
				"name": self.name,
				"conversation_id": self.conversation_id,
				"type": self.type,
				"status": self.status,
			},
			after_commit=True,
		)
