import frappe
from frappe.model.document import Document


class WhatsnextNotification(Document):
	def validate(self):
		if self.attach_document_print and self.template:
			header_type = frappe.db.get_value("Whatsnext Message Template", self.template, "header_type")
			if header_type != "Document":
				frappe.throw(
					f"Template '{self.template}' has Header Type '{header_type}', not 'Document'. "
					"'Attach Document Print as PDF' only works with a template whose header type is "
					"Document (and which has been approved by Meta as such) — otherwise the PDF has "
					"nowhere to go in the outbound message."
				)
