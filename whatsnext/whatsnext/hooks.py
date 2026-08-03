
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

# Whatsnext Notification: activates the existing notification_engine.py,
# which was already built but never wired up here — this is the missing
# piece that actually makes "On Submit" / "On Update" / "On Change"
# notifications fire.
# Fired on submit/update/change for a curated list of commonly-notified
# transactional doctypes (Selling, Buying, CRM, Accounts) so a Whatsnext
# Notification configured against one of these actually triggers.
#
# NOTE: this used to be a wildcard ("*") firing on every doctype in the
# system. That's simpler for the end user (works out of the box on any
# doctype, custom or standard) but Frappe Cloud's marketplace audit flags
# wildcard doc_events as a Major performance risk on shared benches, since
# it runs on every single document operation site-wide. Add/remove entries
# below to match what your customers actually configure notifications on —
# if a Whatsnext Notification is set up against a doctype not in this list,
# it silently won't fire, so keep this in sync with what's documented as
# supported.
WHATSNEXT_NOTIFICATION_DOCTYPES = [
	"Sales Order",
	"Sales Invoice",
	"Delivery Note",
	"Quotation",
	"Payment Entry",
	"Purchase Order",
	"Purchase Invoice",
	"Lead",
	"Opportunity",
	"Customer",
	"Supplier",
]

doc_events = {
	doctype: {
		"on_submit": "whatsnext.whatsnext.notification_engine.on_submit",
		"on_update": "whatsnext.whatsnext.notification_engine.on_update",
		"on_change": "whatsnext.whatsnext.notification_engine.on_change",
	}
	for doctype in WHATSNEXT_NOTIFICATION_DOCTYPES
}
