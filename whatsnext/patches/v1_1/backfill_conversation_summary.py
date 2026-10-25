import frappe


def execute():
	"""Fill the chat-list summary fields (last message, unread and sent
	counts) for existing chats, and create a conversation row for any
	number that has messages but no row yet. Runs once on migrate; after
	that the fields are kept up to date as messages arrive."""
	frappe.reload_doc("whatsnext", "doctype", "whatsnext_conversation")
	frappe.reload_doc("whatsnext", "doctype", "whatsnext_message")

	from whatsnext.whatsnext.conversations import refresh_conversation_summary

	missing = frappe.db.sql(
		"""
		SELECT DISTINCT m.conversation_id
		FROM `tabWhatsnext Message` m
		LEFT JOIN `tabWhatsnext Conversation` c ON c.name = m.conversation_id
		WHERE m.conversation_id IS NOT NULL AND m.conversation_id != '' AND c.name IS NULL
		""",
		pluck=True,
	)
	for conversation_id in missing:
		customer = frappe.db.get_value(
			"Whatsnext Message", {"conversation_id": conversation_id, "customer": ["is", "set"]}, "customer"
		)
		frappe.get_doc({
			"doctype": "Whatsnext Conversation",
			"conversation_id": conversation_id,
			"status": "Open",
			"customer": customer,
		}).insert(ignore_permissions=True)

	names = frappe.get_all("Whatsnext Conversation", pluck="name")
	for i, name in enumerate(names, 1):
		refresh_conversation_summary(name)
		if i % 500 == 0:
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long one-time patch; keep progress
