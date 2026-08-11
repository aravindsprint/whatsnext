
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

# Whatsnext Notification: realtime dispatch for a curated set of common
# business doctypes. Anything NOT in this list can still be watched, just
# via the "Scheduled" event (polling every 5 minutes — see scheduler_events
# below and scheduler.py's dispatch_scheduled_doctype_notifications) rather
# than an instant doc_events hook. whatsnext_notification.py's validate()
# refuses to save a realtime event against a doctype outside this list, so
# there's no way to end up with a silently-dead configuration the way an
# earlier version of this file did with a "*" wildcard (flagged by a
# marketplace audit for firing on every document operation site-wide).
#
# To add realtime support for another doctype, add it here — Scheduled
# polling keeps working for it in the meantime regardless.
WATCHED_DOCTYPES = [
	"Sales Order", "Purchase Order", "Sales Invoice", "Purchase Invoice",
	"Payment Entry", "Quotation", "Delivery Note", "Task", "Issue",
	"Lead", "Opportunity", "Employee", "Leave Application", "Expense Claim",
	"ToDo", "Contact", "Customer", "Supplier", "CRM Lead",
]

doc_events = {
	doctype: {
		"after_insert": "whatsnext.whatsnext.notification_engine.after_insert",
		"on_submit": "whatsnext.whatsnext.notification_engine.on_submit",
		"on_update": "whatsnext.whatsnext.notification_engine.on_update",
		"on_change": "whatsnext.whatsnext.notification_engine.on_change",
	}
	for doctype in WATCHED_DOCTYPES
}

# Was previously unregistered entirely despite scheduler.py's docstrings
# describing a 5-minute cadence — dispatch_scheduled_messages and
# recover_stuck_messages were dead code with no scheduler_events entry to
# ever run them. dispatch_scheduled_doctype_notifications is new: it's the
# polling counterpart to the realtime doc_events above, covering any
# doctype an admin configures a "Scheduled" notification against.
scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"whatsnext.whatsnext.scheduler.dispatch_scheduled_messages",
			"whatsnext.whatsnext.scheduler.recover_stuck_messages",
			"whatsnext.whatsnext.scheduler.dispatch_scheduled_doctype_notifications",
		],
		# refresh_template_approval_status was also sitting completely
		# unregistered despite its own docstring saying "Daily" — found
		# while wiring up the functions above, fixed at the same time.
		"0 2 * * *": [
			"whatsnext.whatsnext.scheduler.refresh_template_approval_status",
		],
	},
}
