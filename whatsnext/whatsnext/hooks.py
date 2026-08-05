
# App launcher tile — shows Whatsnext on the /apps screen
# ------------------
add_to_apps_screen = [
	{
		"name": "whatsnext",
		"logo": "/assets/whatsnext/images/logo.svg",
		"title": "Whatsnext",
		"route": "/whatsnext",
	}
]

# Permissions — scope Whatsnext Message visibility to the logged-in user's
# assigned Sales Person (via ERPNext's Customer -> Sales Team link)
# ------------------
permission_query_conditions = {
	"Whatsnext Message": "whatsnext.whatsnext.permissions.get_message_permission_query_conditions",
}

has_permission = {
	"Whatsnext Message": "whatsnext.whatsnext.permissions.has_message_permission",
}

# Whatsnext Notification: activates notification_engine.py for every
# doctype ("*"), including custom ones — a curated allowlist was tried
# instead (matching a marketplace audit's wildcard performance warning)
# but that meant a notification configured against any NEW doctype
# through the UI silently did nothing until a developer edited this file
# and redeployed, defeating the point of a UI-driven notification builder.
#
# nosemgrep: frappe-doc-events-wildcard -- intentional. The handler
# (notification_engine._dispatch_for_event) does one indexed
# `frappe.get_all(..., filters={"reference_doctype": doc.doctype, "event":
# event, "enabled": 1})` lookup and returns immediately when nothing
# matches, so the marginal cost per document operation site-wide is a
# single cheap indexed query, not real work — the same tradeoff Frappe's
# own core Notification doctype makes for its own doc_events wiring.
doc_events = {
	"*": {
		"after_insert": "whatsnext.whatsnext.notification_engine.after_insert",
		"on_submit": "whatsnext.whatsnext.notification_engine.on_submit",
		"on_update": "whatsnext.whatsnext.notification_engine.on_update",
		"on_change": "whatsnext.whatsnext.notification_engine.on_change",
	}
}
