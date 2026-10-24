import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class WhatsnextOptOut(Document):
	def before_insert(self):
		# The record is named after the number, so normalize before naming —
		# lookups always use the normalized form (e.g. 919876543210).
		from whatsnext.whatsnext.contacts import normalize_outbound_number

		self.phone = normalize_outbound_number(self.phone)

	def validate(self):
		from whatsnext.whatsnext.contacts import normalize_outbound_number

		if self.is_new():
			self.phone = normalize_outbound_number(self.phone)
		if self.has_value_changed("opted_out") or self.is_new():
			if self.opted_out:
				self.opted_out_on = now_datetime()
			else:
				self.opted_in_on = now_datetime()
