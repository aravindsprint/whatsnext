import frappe


def _normalize_phone(phone: str) -> str:
	"""Digits only, trailing 10 kept, so '+91 98765 43210', '919876543210',
	and '09876543210' all match on '9876543210' regardless of country-code
	or leading-zero formatting differences between WhatsApp and the Contact."""
	digits = "".join(ch for ch in (phone or "") if ch.isdigit())
	return digits[-10:] if len(digits) >= 10 else digits


def normalize_outbound_number(number: str) -> str:
	"""Best-effort normalization to the digits-only, country-code-prefixed
	format WhatsApp expects (e.g. '919894088422', not '9894088422' or
	'+91 98940 88422'). A bare local number that's missing its country
	code can be accepted by Meta's API without error yet still fail to
	route to any real device — this exists to catch that before send."""
	digits = "".join(ch for ch in (number or "") if ch.isdigit())
	if not digits:
		return number

	settings = frappe.get_cached_doc("Whatsnext Settings")
	default_cc = (settings.default_country_code or "91").lstrip("+") or "91"

	if len(digits) <= 10:
		return f"{default_cc}{digits}"
	return digits


def resolve_customer_from_phone(phone: str) -> str | None:
	"""Best-effort lookup: WhatsApp number -> Contact (via Contact Phone) ->
	Customer (via the Contact's Dynamic Link rows). Returns None if no
	Contact matches or no Customer is linked — callers should treat that as
	'unassigned', not an error."""
	if not phone:
		return None

	target = _normalize_phone(phone)
	if not target:
		return None

	row = frappe.db.sql(
		"""
		SELECT parent FROM `tabContact Phone`
		WHERE parenttype = 'Contact' AND phone LIKE %s
		LIMIT 1
		""",
		(f"%{target}",),
	)
	contact_name = row[0][0] if row else None
	if not contact_name:
		return None

	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
		"link_name",
	)
