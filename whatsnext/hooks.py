app_name = "whatsnext"
app_title = "Whatsnext"
app_publisher = "Aravind Govindaraj"
app_description = "Standalone WhatsApp Business messaging hub (Meta Cloud API + Twilio) for ERPNext — templates, scheduling, dashboards, and event-driven notifications."
app_email = "aravindsprint@gmail.com"
app_license = "MIT"
app_version = "1.0.0"

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
# Generic hook fired on submit/update/change for ANY doctype so we can check
# whether a Whatsnext Notification is configured against it.
doc_events = {
    "*": {
        "on_submit": "whatsnext.whatsnext.notification_engine.on_submit",
        "on_update": "whatsnext.whatsnext.notification_engine.on_update",
        "on_change": "whatsnext.whatsnext.notification_engine.on_change",
    }
}

# Scheduled Tasks
# ------------------
scheduler_events = {
    "cron": {
        # Every 5 minutes: dispatch anything queued/scheduled that's due
        "*/5 * * * *": [
            "whatsnext.whatsnext.scheduler.dispatch_scheduled_messages",
        ],
        # Every 15 minutes: safety net for stuck-in-flight messages (see build spec §10)
        "*/15 * * * *": [
            "whatsnext.whatsnext.scheduler.recover_stuck_messages",
        ],
    },
    "daily": [
        "whatsnext.whatsnext.scheduler.refresh_template_approval_status",
    ],
}

# Installation
# ------------------
after_install = "whatsnext.whatsnext.setup.create_defaults"
after_migrate = "whatsnext.whatsnext.setup.create_defaults"

# Website route rules — serve the SPA shell for every /whatsnext/* path so
# Vue Router can handle client-side routing (deep links, refreshes, etc).
website_route_rules = [
    {"from_route": "/whatsnext/<path:app_path>", "to_route": "whatsnext"},
]

# Webhook endpoints are plain whitelisted methods (see whatsnext/api/webhook.py),
# reached at /api/method/whatsnext.api.webhook.meta_webhook etc. — no extra
# hook wiring needed since Frappe exposes @frappe.whitelist() methods directly.
