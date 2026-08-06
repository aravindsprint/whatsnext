import frappe

from whatsnext.whatsnext.push_engine import get_vapid_keys


@frappe.whitelist()
def get_vapid_public_key():
	"""Public key only -- the private key never leaves the server. Returns
	None while push is switched off so the frontend knows not to prompt for
	notification permission at all."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.push_notifications_enabled:
		return None
	public_key, _ = get_vapid_keys()
	return public_key


@frappe.whitelist()
def save_push_subscription(subscription):
	"""Upserts by (user, endpoint) -- re-subscribing on the same device
	(browser restart, permission re-grant, etc.) updates the existing row's
	keys instead of accumulating duplicates that would each receive their
	own push attempt."""
	if isinstance(subscription, str):
		import json

		subscription = json.loads(subscription)

	endpoint = subscription.get("endpoint")
	keys = subscription.get("keys") or {}
	p256dh = keys.get("p256dh")
	auth = keys.get("auth")

	if not (endpoint and p256dh and auth):
		frappe.throw("Invalid push subscription payload.")

	existing_name = frappe.db.get_value(
		"Whatsnext Push Subscription",
		{"user": frappe.session.user, "endpoint": endpoint},
		"name",
	)

	if existing_name:
		doc = frappe.get_doc("Whatsnext Push Subscription", existing_name)
	else:
		doc = frappe.new_doc("Whatsnext Push Subscription")
		doc.user = frappe.session.user
		doc.endpoint = endpoint

	doc.p256dh = p256dh
	doc.auth = auth
	doc.user_agent = frappe.request.headers.get("User-Agent", "")[:140] if frappe.request else ""
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"ok": True}


@frappe.whitelist()
def remove_push_subscription(endpoint):
	"""Called when the frontend unsubscribes (user turns notifications off,
	or the browser reports the subscription as no longer valid)."""
	name = frappe.db.get_value(
		"Whatsnext Push Subscription",
		{"user": frappe.session.user, "endpoint": endpoint},
		"name",
	)
	if name:
		frappe.delete_doc("Whatsnext Push Subscription", name, ignore_permissions=True)
		frappe.db.commit()
	return {"ok": True}
