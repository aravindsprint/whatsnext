import json

import frappe

from whatsnext.whatsnext.permissions import users_who_can_see


def get_vapid_keys():
	"""Returns (public_key, private_key), generating and persisting a keypair
	on Whatsnext Settings the first time this is called. Generated lazily
	(instead of at install time) so a fresh site never ships a shared/known
	keypair baked into the app -- every install gets its own, and installs
	that never turn push on never pay for generating one at all."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	private_pem = settings.get_password("vapid_private_key", raise_exception=False)

	# Earlier versions wrote the private key with db.set_single_value, which
	# stores it as plain text in tabSingles instead of the encrypted __Auth
	# table that get_password() reads -- so it was never found again and a
	# fresh keypair was generated on every call, silently invalidating every
	# browser subscription bound to the previous public key. Recover such a
	# key (keeping the public key browsers already subscribed with) by moving
	# it into encrypted storage.
	if not private_pem:
		raw = frappe.db.get_single_value("Whatsnext Settings", "vapid_private_key") or ""
		if raw.startswith("-----BEGIN"):
			_store_private_key(raw)
			private_pem = raw

	if settings.vapid_public_key and private_pem:
		return settings.vapid_public_key, private_pem

	# py_vapid is a dependency of pywebpush, so it's available wherever
	# pywebpush is. Keeping the import local means merely importing this
	# module never requires pywebpush to be installed unless push is used.
	from py_vapid import Vapid

	vapid = Vapid()
	vapid.generate_keys()

	# The browser's Push API (applicationServerKey) needs the raw
	# uncompressed EC point (0x04 || X || Y), base64url-encoded.
	public_key = _b64_urlsafe_public_key(vapid)
	private_pem = vapid.private_pem().decode("ascii")

	frappe.db.set_single_value("Whatsnext Settings", "vapid_public_key", public_key)
	_store_private_key(private_pem)
	# Committed immediately: this can run inside a background job, and an
	# uncommitted keypair that later rolls back would be regenerated on the
	# next call -- permanently breaking every subscription a browser had
	# already created against the old public key.
	frappe.db.commit()  # nosemgrep: frappe-manual-commit

	return public_key, private_pem


def _store_private_key(private_pem: str):
	"""Password fields must go through Frappe's encrypted password store;
	the Singles row only keeps a mask, like a normal form save does."""
	from frappe.utils.password import set_encrypted_password

	set_encrypted_password("Whatsnext Settings", "Whatsnext Settings", private_pem, "vapid_private_key")
	frappe.db.set_single_value("Whatsnext Settings", "vapid_private_key", "*" * 10)
	frappe.clear_document_cache("Whatsnext Settings", "Whatsnext Settings")


def _b64_urlsafe_public_key(vapid) -> str:
	"""Fallback for py_vapid versions without the raw-b64 helper: derive the
	uncompressed EC point (0x04 || X || Y) from the public key object and
	base64url-encode it ourselves -- this is the exact format the Push API's
	applicationServerKey expects."""
	import base64

	numbers = vapid.public_key.public_numbers()
	x = numbers.x.to_bytes(32, "big")
	y = numbers.y.to_bytes(32, "big")
	raw = b"\x04" + x + y
	return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def send_push_to_users(users: list[str], title: str, body: str, url: str = "/whatsnext", tag: str | None = None):
	"""Best-effort fan-out: sends a web push to every subscription belonging
	to any user in `users`. Failures for one subscription (expired,
	unsubscribed, unreachable push service) never block delivery to the
	others -- each is attempted and cleaned up independently."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.push_notifications_enabled or not users:
		return

	try:
		from pywebpush import WebPushException, webpush
	except ImportError:
		frappe.log_error(
			title="Whatsnext Push",
			message="push_notifications_enabled is on but the 'pywebpush' package isn't installed. "
			"Run: bench pip install pywebpush",
		)
		return

	from py_vapid import Vapid

	_, private_pem = get_vapid_keys()
	# Hand pywebpush a Vapid object: given a bare string it calls
	# Vapid.from_string(), which expects base64 DER and can't parse the PEM
	# we store, so every send failed.
	private_key = Vapid.from_pem(private_pem.encode())
	vapid_claims = {"sub": settings.vapid_subject or "mailto:admin@example.com"}

	subscriptions = frappe.get_all(
		"Whatsnext Push Subscription",
		filters={"user": ["in", users]},
		fields=["name", "endpoint", "p256dh", "auth"],
	)

	payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or url})

	for sub in subscriptions:
		try:
			webpush(
				subscription_info={
					"endpoint": sub.endpoint,
					"keys": {"p256dh": sub.p256dh, "auth": sub.auth},
				},
				data=payload,
				vapid_private_key=private_key,
				vapid_claims=dict(vapid_claims),
			)
		except WebPushException as e:
			status_code = getattr(e.response, "status_code", None)
			if status_code in (404, 410):
				# Push service says this endpoint is gone for good (browser
				# uninstalled/unsubscribed) -- stop trying it going forward.
				frappe.delete_doc("Whatsnext Push Subscription", sub.name, ignore_permissions=True)
			else:
				frappe.log_error(title="Whatsnext Push send failed", message=str(e))
		except Exception as e:
			frappe.log_error(title="Whatsnext Push send failed", message=str(e))


def notify_new_message(message_name: str, conversation_id: str, customer: str | None,
	text: str, profile_name: str | None, from_number: str | None):
	"""Background job (enqueued from WhatsnextMessage.after_insert) that
	fans a push notification out to every subscribed user permitted to see
	this conversation. Runs off-request so a slow/unreachable push service
	never adds latency to the inbound-webhook or send-message response.

	Recipient scoping mirrors permissions.has_message_permission: unscoped
	(System Manager/Administrator) users get everything; Sales-Person-mapped
	users only get pushes for customers assigned to them (or unassigned
	conversations); a subscribed user with no Sales Person mapping and no
	System Manager role gets nothing, same as they'd see nothing in the UI."""
	subscribed_users = set(frappe.get_all("Whatsnext Push Subscription", pluck="user", distinct=True))
	if not subscribed_users:
		return

	recipients = [u for u in users_who_can_see(customer) if u in subscribed_users]
	if not recipients:
		return

	title = profile_name or from_number or "New WhatsApp message"
	body = (text or "").strip()
	if len(body) > 120:
		body = body[:117] + "..."

	send_push_to_users(
		recipients,
		title=title,
		body=body or "Sent you a message",
		url=f"/whatsnext?conversation={conversation_id}",
		tag=f"whatsnext-{conversation_id}",
	)
