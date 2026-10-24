import re

from frappe.model.document import Document


class WhatsnextQuickReply(Document):
	def validate(self):
		if self.shortcut:
			self.shortcut = re.sub(r"[^a-z0-9_-]", "", self.shortcut.lower().lstrip("/"))
