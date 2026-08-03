import frappe
from frappe.model.document import Document


class WhatsnextMessage(Document):
	def before_insert(self):
		if not self.conversation_id:
			# Group by reference_name if we have one, else by counterpart number
			self.conversation_id = self.reference_name or self.to_number or self.from_number

	def after_insert(self):
		# Scoped to this document: Frappe only delivers to sessions permitted to
		# read this Whatsnext Message (via the has_permission/
		# permission_query_conditions hooks already registered for this
		# doctype), instead of broadcasting to every connected user on the site.
		frappe.publish_realtime(
			event="whatsnext_new_message",
			message={
				"name": self.name,
				"conversation_id": self.conversation_id,
				"type": self.type,
				"status": self.status,
			},
			doctype=self.doctype,
			docname=self.name,
			after_commit=True,
		)
