import json
import os

import frappe

no_cache = 1
no_breadcrumbs = 1
no_sitemap = 1

# Where `yarn build` output gets copied to (see DEPLOY.md) and how it's served.
ASSET_DIR = "whatsnext_frontend"
ASSET_URL_PREFIX = f"/assets/whatsnext/{ASSET_DIR}"


def get_context(context):
	# Deliberately NO Guest redirect here. Redirecting Guests server-side to
	# Frappe's generic /login makes the SPA's own branded LoginPage.vue
	# unreachable. Let the SPA render for everyone; its own Vue Router guard
	# (checking isLoggedIn()) handles showing the login form.
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.no_cache = 1

	entry = _resolve_built_assets()
	context.js_entry = entry["js"]
	context.css_entries = entry["css"]


def _manifest_path():
	# public/ is symlinked into sites/assets/whatsnext by `bench build`, but we
	# read the manifest straight from the app's own public folder so this
	# works immediately after `yarn build` too, before a bench build runs.
	app_path = frappe.get_app_path("whatsnext")
	return os.path.join(app_path, "public", ASSET_DIR, ".vite", "manifest.json")


def _resolve_built_assets():
	"""Falls back to a friendly placeholder if the frontend hasn't been built
	yet, instead of throwing — so `bench install-app` never fails because the
	SPA bundle doesn't exist yet."""
	path = _manifest_path()
	if not os.path.exists(path):
		return {"js": None, "css": []}

	with open(path) as f:  # nosemgrep: frappe-security-file-traversal -- path is built entirely from frappe.get_app_path() + hardcoded constants (ASSET_DIR, ".vite", "manifest.json"); no request/user input reaches this path
		manifest = json.load(f)

	entry = manifest.get("index.html") or next(iter(manifest.values()), {})
	js_file = entry.get("file")
	css_files = entry.get("css", [])

	return {
		"js": f"{ASSET_URL_PREFIX}/{js_file}" if js_file else None,
		"css": [f"{ASSET_URL_PREFIX}/{c}" for c in css_files],
	}
