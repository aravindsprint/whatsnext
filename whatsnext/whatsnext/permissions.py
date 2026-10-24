import frappe


def _sales_persons_for_user(user: str) -> list:
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return []
	return frappe.db.get_all("Sales Person", filters={"employee": employee}, pluck="name")


def get_allowed_customers(user: str = None):
	"""Returns:
	  None -> unrestricted (System Manager / Administrator)
	  []   -> user has no Sales Person mapping; sees only unassigned chats
	  [..] -> Customers assigned to this user's Sales Person record(s),
	          via ERPNext's existing Customer -> Sales Team -> Sales Person link
	"""
	user = user or frappe.session.user

	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return None

	sales_persons = _sales_persons_for_user(user)
	if not sales_persons:
		return []

	return frappe.db.get_all(
		"Sales Team",
		filters={"parenttype": "Customer", "sales_person": ["in", sales_persons]},
		pluck="parent",
		distinct=True,
	) or []


def get_message_permission_query_conditions(user=None):
	"""Frappe's permission_query_conditions hook for Whatsnext Message.
	Applies to Desk list/report views and frappe.get_list() calls. Does NOT
	apply to frappe.get_all() or raw frappe.db.sql() — those are filtered
	explicitly in whatsnext.whatsnext.api (get_conversations / get_messages),
	which is what the chat UI actually calls."""
	user = user or frappe.session.user
	customers = get_allowed_customers(user)

	if customers is None:
		return ""

	if not customers:
		return "(`tabWhatsnext Message`.customer is null or `tabWhatsnext Message`.customer = '')"

	customer_list = ", ".join(frappe.db.escape(c) for c in customers)
	return (
		f"(`tabWhatsnext Message`.customer in ({customer_list}) "
		f"or `tabWhatsnext Message`.customer is null or `tabWhatsnext Message`.customer = '')"
	)


def get_conversation_permission_query_conditions(user=None):
	return get_message_permission_query_conditions(user).replace(
		"`tabWhatsnext Message`", "`tabWhatsnext Conversation`"
	)


def has_message_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	customers = get_allowed_customers(user)

	if customers is None:
		return True
	if not doc.customer:
		return True
	return doc.customer in customers


def users_who_can_see(customer: str | None) -> list[str]:
	"""Enabled users allowed to see a conversation for `customer`, using the
	same rules as has_message_permission: unrestricted users always, Sales
	Person-mapped users when the customer is theirs or the chat is
	unassigned. Used to target realtime events and push notifications so
	they reach exactly the people who can open the chat."""
	candidates = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", ["Whatsnext User", "System Manager"]]},
		pluck="parent",
		distinct=True,
	)
	candidates = set(candidates) | {"Administrator"}
	enabled = set(
		frappe.get_all("User", filters={"name": ["in", list(candidates)], "enabled": 1}, pluck="name")
	)

	users = []
	for user in enabled:
		allowed = get_allowed_customers(user)
		if allowed is None or not customer or customer in allowed:
			users.append(user)
	return users
