import frappe
from frappe.model.document import Document

from whatsnext.whatsnext.hooks import WATCHED_DOCTYPES


class WhatsnextNotification(Document):
	def validate(self):
		if (
			self.reference_doctype
			and self.event != "Scheduled"
			and self.reference_doctype not in WATCHED_DOCTYPES
		):
			frappe.throw(
				f"'{self.reference_doctype}' isn't wired for instant notifications — only "
				f"{', '.join(WATCHED_DOCTYPES)} are. Choose the 'Scheduled' event instead "
				"to check this doctype for changes every 5 minutes, or ask a developer to "
				"add it to WATCHED_DOCTYPES in hooks.py for instant delivery."
			)

		if self.attach_document_print and self.template:
			header_type = frappe.db.get_value("Whatsnext Message Template", self.template, "header_type")
			if header_type != "Document":
				frappe.throw(
					f"Template '{self.template}' has Header Type '{header_type}', not 'Document'. "
					"'Attach Document Print as PDF' only works with a template whose header type is "
					"Document (and which has been approved by Meta as such) — otherwise the PDF has "
					"nowhere to go in the outbound message."
				)
