import json

import frappe


def execute():
	"""Template messages sent before the body was rendered at save time were
	stored with raw {{1}}, {{2}}... placeholders, so the chat showed the
	template text instead of what the customer actually received. Their
	template_parameters were saved, so fill the values in now.

	update_modified=False keeps each row's timestamp, so the chat list order
	and the conversation summaries don't change."""
	from whatsnext.whatsnext.api import _render_body

	rows = frappe.db.sql(
		"""
		SELECT name, message, template_parameters
		FROM `tabWhatsnext Message`
		WHERE message LIKE %(pattern)s
			AND IFNULL(template_parameters, '') NOT IN ('', '{}', 'null')
		""",
		{"pattern": "%{{%}}%"},
		as_dict=True,
	)

	for i, row in enumerate(rows, 1):
		try:
			params = json.loads(row.template_parameters)
		except (TypeError, ValueError):
			continue
		if not isinstance(params, dict):
			continue
		rendered = _render_body(row.message, params)
		if rendered != row.message:
			frappe.db.set_value("Whatsnext Message", row.name, "message", rendered, update_modified=False)
		if i % 500 == 0:
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long one-time patch; keep progress
