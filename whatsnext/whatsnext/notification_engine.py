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
		# The configured field (e.g. Sales Invoice's contact_mobile) is a
		# client-side "Fetch From" field — it only populates when someone
		# picks the Contact Person in the browser form. Documents created
		# via API/import/automation skip that fetch and submit with the
		# field blank, so the notification would otherwise silently no-op
		# even though the linked Contact does have a number on file.
		number = _fallback_contact_mobile(doc)
	if not number:
		frappe.log_error(
			f"No recipient number found on {doc.doctype} {doc.name} "
			f"(field '{notif.recipient_number_field}' was blank and no "
			f"linked Contact had a mobile number either)",
			f"Whatsnext notification '{notif.name}' skipped — no recipient number",
		)
		return

	params = {}
	for row in notif.field_mapping:
		value = row.static_value
		if row.source_fieldname:
			value = doc.get(row.source_fieldname, value)
		params[row.template_variable] = value

	header_media_url = None
	if notif.attach_document_print:
		header_media_url = _attach_document_pdf(notif, doc)

	from whatsnext.whatsnext.api import send_template_message
	send_template_message(
		to=number,
		template=notif.template,
		parameters=params,
		provider=notif.provider or None,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		header_media_url=header_media_url,
	)


def _fallback_contact_mobile(doc):
	"""Look up the mobile number directly from the linked Contact when the
	document's own recipient field is empty. Covers Sales Invoice, Sales
	Order, Delivery Note, Quotation, etc. — anything with a contact_person
	link — without needing per-doctype configuration."""
	contact_name = doc.get("contact_person")
	if not contact_name:
		return None
	return frappe.db.get_value("Contact", contact_name, "mobile_no") or frappe.db.get_value(
		"Contact", contact_name, "phone"
	)


def _attach_document_pdf(notif, doc):
	"""Renders doc's print format to PDF and saves it as a public File so its
	URL can be handed to Meta/Twilio as the template's document header — a
	private file URL (the frappe.utils.file_manager default) isn't fetchable
	by either provider, same failure mode as the scontent.whatsapp.net links
	on the marketing templates. Mirrors the old WhatsApp Notification's
	attach_document_print behaviour, minus the reliance on the desk-only
	print PDF endpoint that doctype no longer has access to here."""
	from frappe.utils.file_manager import save_file
	from frappe.utils.pdf import get_pdf
	from frappe.www.printview import get_html

	html = get_html(doctype=doc.doctype, name=doc.name, print_format=notif.print_format or None, no_letterhead=0)
	pdf_content = get_pdf(html)

	fname = f"{doc.doctype}-{doc.name}.pdf".replace(" ", "-").replace("/", "-")
	file_doc = save_file(fname, pdf_content, doc.doctype, doc.name, is_private=0)
	return file_doc.file_url if file_doc.file_url.startswith("http") else frappe.utils.get_url(file_doc.file_url)
