import frappe


def execute():
	"""Re-link chats that never found their ERPNext Contact. The phone lookup
	used to compare against the raw stored number, so a Contact saved as
	"+91 98765 43210" never matched and the chat stayed without a Contact or
	Customer (and so visible to every Sales Person). The lookup now ignores
	formatting; run it again for every chat still missing a Contact."""
	from whatsnext.whatsnext.contacts import customer_for_contact, resolve_contact_from_phone

	names = frappe.get_all(
		"Whatsnext Conversation",
		filters={"contact": ["is", "not set"]},
		pluck="name",
	)
	for i, conversation_id in enumerate(names, 1):
		contact = resolve_contact_from_phone(conversation_id)
		if not contact:
			continue
		customer = customer_for_contact(contact)

		frappe.db.sql(
			"""UPDATE `tabWhatsnext Message` SET contact = %(contact)s
			WHERE conversation_id = %(cid)s AND (contact IS NULL OR contact = '')""",
			{"contact": contact, "cid": conversation_id},
		)
		updates = {"contact": contact}
		if customer:
			frappe.db.sql(
				"""UPDATE `tabWhatsnext Message` SET customer = %(customer)s
				WHERE conversation_id = %(cid)s AND (customer IS NULL OR customer = '')""",
				{"customer": customer, "cid": conversation_id},
			)
			if not frappe.db.get_value("Whatsnext Conversation", conversation_id, "customer"):
				updates["customer"] = customer
		frappe.db.set_value("Whatsnext Conversation", conversation_id, updates, update_modified=False)

		if i % 500 == 0:
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long one-time patch; keep progress
