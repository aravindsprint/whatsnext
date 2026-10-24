import frappe


def execute():
	"""Create a Whatsnext Conversation row for every existing chat thread so
	assignment, open/closed state and the 24-hour window work for history
	that predates the Conversation doctype."""
	frappe.reload_doc("whatsnext", "doctype", "whatsnext_conversation")

	rows = frappe.db.sql(
		"""
		SELECT conversation_id,
			MAX(creation) AS last_message_at,
			MAX(CASE WHEN type = 'Incoming' THEN creation END) AS last_incoming_at,
			MAX(customer) AS customer
		FROM `tabWhatsnext Message`
		WHERE conversation_id IS NOT NULL AND conversation_id != ''
		GROUP BY conversation_id
		""",
		as_dict=True,
	)
	for r in rows:
		if frappe.db.exists("Whatsnext Conversation", r.conversation_id):
			continue
		profile_name = frappe.db.get_value(
			"Whatsnext Message",
			{"conversation_id": r.conversation_id, "profile_name": ["is", "set"]},
			"profile_name",
			order_by="creation desc",
		)
		frappe.get_doc({
			"doctype": "Whatsnext Conversation",
			"conversation_id": r.conversation_id,
			"status": "Open",
			"profile_name": profile_name,
			"customer": r.customer,
			"last_message_at": r.last_message_at,
			"last_incoming_at": r.last_incoming_at,
		}).insert(ignore_permissions=True)
