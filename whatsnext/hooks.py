app_name = "whatsnext"
app_title = "Whatsnext"
app_publisher = "Aravind Govindaraj"
app_description = "Standalone WhatsApp Business messaging hub (Meta Cloud API + Twilio) for ERPNext — templates, scheduling, dashboards, and event-driven notifications."
app_email = "aravindsprint@gmail.com"
app_license = "MIT"
app_version = "1.1.0"

# Messages link to Customer and Contact, and chats are scoped by Sales Person,
# so the app needs ERPNext; without it the install fails on those links.
required_apps = ["erpnext"]

# Includes
# ------------------
app_include_css = "/assets/whatsnext/css/whatsnext.css"
app_include_js = "/assets/whatsnext/js/whatsnext.js"

# Fixtures — dedicated role only, no seed business data as a fixture (see setup.py)
fixtures = [
    {"dtype": "Role", "filters": [["name", "=", "Whatsnext User"]]},
]

# Document Events
# ------------------
# Whatsnext Notification: realtime dispatch for a curated set of common
# business doctypes. Anything NOT in this list can still be watched via the
# "Scheduled" event (polled every 5 minutes by
# scheduler.dispatch_scheduled_doctype_notifications). A "*" wildcard is
# deliberately NOT used: it fires on every document operation site-wide.
# whatsnext_notification.py's validate() refuses to save a realtime event
# against a doctype outside this list, so a configuration can never end up
# silently dead.
#
# To add realtime support for another doctype, add it here.
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

# Scheduled Tasks
# ------------------
scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			# Pending messages whose scheduled_time has arrived
			"whatsnext.whatsnext.scheduler.dispatch_scheduled_messages",
			# Campaigns whose scheduled_time has arrived
			"whatsnext.whatsnext.scheduler.start_scheduled_campaigns",
			# Polling counterpart to doc_events for "Scheduled" notifications
			"whatsnext.whatsnext.scheduler.dispatch_scheduled_doctype_notifications",
		],
		# Safety net for messages/campaigns stuck in flight
		"*/15 * * * *": [
			"whatsnext.whatsnext.scheduler.recover_stuck_messages",
		],
		"0 2 * * *": [
			"whatsnext.whatsnext.scheduler.refresh_template_approval_status",
		],
	},
}

# Extensions
# ------------------
# Other apps can add features to the chat by declaring, in their own hooks.py:
#
# whatsnext_extensions = [{
#     "feature": "smart_replies",                     # what the chat should show
#     "enabled": "my_app.api.is_enabled",            # optional; returns True/False
#     "options": "my_app.api.get_reply_options",     # whitelisted, GET
#     "suggest": "my_app.api.suggest_replies",       # whitelisted, POST
# }]
#
# api.whoami() lists the enabled ones and the SPA shows the matching UI.
# Features the SPA knows: smart_replies (options, suggest), improve_reply
# (improve), translate (translate), chat_summary (summarize), order_draft
# (extract, search_items, create) and auto_tag (retag).
#
# Chips on chats in the list and chat header:
# whatsnext_conversation_labels = ["my_app.labels.labels_for"]
#   called with a list of conversation ids the user may see; returns
#   {conversation_id: [{"text": "Urgent", "tone": "red", "title": "why"}]}
#   (tones: teal, gray, orange, red, green). Publish the realtime event
#   "whatsnext_conversation_update" with {"conversation_id": ...} to make
#   open chat screens refresh a chat's labels.

# Installation
# ------------------
after_install = "whatsnext.whatsnext.setup.create_defaults"
after_migrate = "whatsnext.whatsnext.setup.create_defaults"

# Website route rules — serve the SPA shell for every /whatsnext/* path so
# Vue Router can handle client-side routing (deep links, refreshes, etc).
website_route_rules = [
    # These exact static files must resolve to their own physical files
    # (www/whatsnext/sw.js, public/whatsnext_frontend/manifest.webmanifest)
    # rather than falling into the SPA catch-all below — the service worker
    # script in particular MUST be served with a JS mime type, or the
    # browser rejects registration with a SecurityError. Listed before the
    # wildcard so they're matched first.
    # Served from sw.min.js: Frappe's website renderer passes www/ .js files
    # through Jinja like a page, except files ending in "min.js", which it
    # sends unchanged. A stray "{{" or "{%" in a future minified build would
    # otherwise break the service worker (push, offline, auto-update). The
    # public URL stays /whatsnext/sw.js so existing registrations keep working.
    {"from_route": "/whatsnext/sw.js", "to_route": "whatsnext/sw.min.js"},
    {"from_route": "/whatsnext/manifest.webmanifest", "to_route": "whatsnext/manifest.webmanifest"},
    {"from_route": "/whatsnext/<path:app_path>", "to_route": "whatsnext"},
]

# Webhook endpoints are plain whitelisted methods (see whatsnext/api/webhook.py),
# reached at /api/method/whatsnext.api.webhook.meta_webhook etc. — no extra
# hook wiring needed since Frappe exposes @frappe.whitelist() methods directly.

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
	"Whatsnext Conversation": "whatsnext.whatsnext.permissions.get_conversation_permission_query_conditions",
}

has_permission = {
	"Whatsnext Message": "whatsnext.whatsnext.permissions.has_message_permission",
	"Whatsnext Conversation": "whatsnext.whatsnext.permissions.has_message_permission",
}
