import frappe
from frappe.model.document import Document


class WhatsnextMessageTemplate(Document):
	def validate(self):
		import re
		placeholders = re.findall(r"\{\{(\d+)\}\}", self.body or "")
		# keep variables_sample keys in sync so the dashboard/template picker
		# always has a slot to fill in for every {{n}} used in the body
		if placeholders:
			import json
			existing = {}
			if self.variables_sample:
				try:
					existing = json.loads(self.variables_sample) if isinstance(self.variables_sample, str) else self.variables_sample
				except Exception:
					existing = {}
			merged = {p: existing.get(p, "") for p in sorted(set(placeholders), key=int)}
			self.variables_sample = json.dumps(merged)
