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

	# "00" is the international dialling prefix (0044..., 0091...): what
	# follows already starts with the country code.
	if digits.startswith("00"):
		return digits[2:]

	settings = frappe.get_cached_doc("Whatsnext Settings")
	default_cc = (settings.default_country_code or "91").lstrip("+") or "91"

	# A single leading "0" is the domestic trunk prefix (09876543210,
	# 07911 123456): drop it and add the country code. Kept as-is, the
	# number was sent with the 0 and WhatsApp rejected it.
	if digits.startswith("0"):
		return f"{default_cc}{digits.lstrip('0')}"
	if len(digits) <= 10:
		return f"{default_cc}{digits}"
	return digits


def resolve_contact_from_phone(phone: str) -> str | None:
	"""WhatsApp number -> Contact (via Contact Phone rows, matched on the
	last 10 digits so country-code/formatting differences don't matter)."""
	if not phone:
		return None

	target = _normalize_phone(phone)
	if not target:
		return None

	# Compare digits only: numbers are commonly stored formatted
	# ("+91 98765 43210", "+91-98765-43210", "(0) 98765 43210"), and a plain
	# LIKE on the raw value never matched those, leaving the chat with no
	# Contact or Customer -- and so visible to every Sales Person.
	row = frappe.db.sql(
		"""
		SELECT parent FROM `tabContact Phone`
		WHERE parenttype = 'Contact'
			AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(phone,
				' ', ''), '-', ''), '(', ''), ')', ''), '.', ''), '+', '') LIKE %s
		ORDER BY is_primary_mobile_no DESC, is_primary_phone DESC
		LIMIT 1
		""",
		(f"%{target}",),
	)
	return row[0][0] if row else None


def customer_for_contact(contact_name: str | None) -> str | None:
	if not contact_name:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
		"link_name",
	)


def resolve_customer_from_phone(phone: str) -> str | None:
	"""Best-effort lookup: WhatsApp number -> Contact -> Customer (via the
	Contact's Dynamic Link rows). Returns None if no Contact matches or no
	Customer is linked — callers should treat that as 'unassigned'."""
	return customer_for_contact(resolve_contact_from_phone(phone))
