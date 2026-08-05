"""Generic doc_events dispatcher wired to every doctype in hooks.py.
Looks up Whatsnext Notification records configured against doc.doctype for the
firing event, evaluates the optional condition, resolves the recipient number
and template variables, then queues a send. Cheap no-op for the vast majority
of doctypes since it short-circuits on an indexed lookup.
"""

import frappe
from frappe.utils.safe_exec import safe_eval


def after_insert(doc, method=None):
	_dispatch_for_event(doc, "After Insert")


def on_submit(doc, method=None):
	_dispatch_for_event(doc, "On Submit")


def on_update(doc, method=None):
	_dispatch_for_event(doc, "On Update")


def on_change(doc, method=None):
	_dispatch_for_event(doc, "On Change")


def _dispatch_for_event(doc, event):
	if doc.doctype in ("Whatsnext Message", "Whatsnext Notification", "Whatsnext Message Template"):
		return  # never trigger off our own doctypes

	notifications = frappe.get_all(
		"Whatsnext Notification",
		filters={"reference_doctype": doc.doctype, "event": event, "enabled": 1},
		pluck="name",
	)
	if not notifications:
		return

	for name in notifications:
		notif = frappe.get_cached_doc("Whatsnext Notification", name)
		try:
			_fire(notif, doc)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Whatsnext notification '{name}' failed for {doc.doctype} {doc.name}")


def _fire(notif, doc):
	if notif.condition:
		# Only "doc" is exposed here — deliberately NOT the raw frappe module.
		# safe_eval already provides its own restricted frappe.* namespace
		# (frappe.db.get_value, frappe.utils.*, etc; see its docstring for
		# the full allowed list). Passing the real `frappe` module as a
		# local would bypass that restriction entirely and let a configured
		# condition call anything, including frappe.db.sql or delete_doc.
		if not safe_eval(notif.condition, {"doc": doc}):  # nosemgrep: frappe-codeinjection-eval -- sandboxed via frappe.utils.safe_exec.safe_eval, not builtin eval; only "doc" is exposed, no frappe module access
			return

	number = notif.fixed_number
	if notif.recipient_number_field:
		number = doc.get(notif.recipient_number_field) or number
	if not number:
		return

	params = {}
	for row in notif.field_mapping:
		value = row.static_value
		if row.source_fieldname:
			value = doc.get(row.source_fieldname, value)
		params[row.template_variable] = value

	from whatsnext.whatsnext.api import send_template_message
	send_template_message(
		to=number,
		template=notif.template,
		parameters=params,
		provider=notif.provider or None,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)
