import frappe
from frappe.utils import now_datetime, add_to_date


def dispatch_scheduled_messages():
	"""Runs every 5 minutes. Sends any Pending message whose scheduled_time has arrived."""
	due = frappe.get_all(
		"Whatsnext Message",
		filters={"status": "Pending", "scheduled_time": ["<=", now_datetime()]},
		fields=["name"],
		limit_page_length=200,
	)
	if not due:
		return

	from whatsnext.whatsnext.api import _dispatch

	for row in due:
		msg = frappe.get_doc("Whatsnext Message", row.name)
		template_doc = frappe.get_doc("Whatsnext Message Template", msg.template) if msg.template else None
		params = {}
		if msg.template_parameters:
			import json
			try:
				params = json.loads(msg.template_parameters)
			except Exception:
				params = {}
		_dispatch(msg, template_doc=template_doc, params=params)


def recover_stuck_messages():
	"""Safety net per build spec §10: anything stuck 'Queued'/'Pending' for more
	than 30 minutes without a scheduled_time (i.e. should have gone out
	immediately) is force-marked Failed so it doesn't sit invisibly forever."""
	cutoff = add_to_date(now_datetime(), minutes=-30)
	stuck = frappe.get_all(
		"Whatsnext Message",
		filters={
			"status": ["in", ["Pending", "Queued"]],
			"scheduled_time": ["is", "not set"],
			"modified": ["<", cutoff],
		},
		pluck="name",
	)
	for name in stuck:
		frappe.db.set_value(
			"Whatsnext Message", name,
			{"status": "Failed", "error_message": "Stuck in Pending/Queued for >30min — auto-marked Failed by safety-net job."},
			update_modified=True,
		)
	if stuck:
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job, no request-level auto-commit to rely on

	_recover_stuck_campaigns(cutoff)


def _recover_stuck_campaigns(cutoff):
	"""A campaign job can die mid-run if a worker restarts. Anything left in
	Queued/Sending well past when it should have finished gets force-marked
	Failed so it's visible on the dashboard instead of silently stuck."""
	stuck_campaigns = frappe.get_all(
		"Whatsnext Campaign",
		filters={"status": ["in", ["Queued", "Sending"]], "modified": ["<", cutoff]},
		pluck="name",
	)
	for name in stuck_campaigns:
		frappe.db.set_value("Whatsnext Campaign", name, "status", "Failed", update_modified=True)
	if stuck_campaigns:
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job


def refresh_template_approval_status():
	"""Daily: pull Meta template approval statuses so locally-created templates
	reflect real WhatsApp Business Manager review outcomes."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.meta_enabled:
		return

	from whatsnext.whatsnext.provider_engine import MetaProvider

	try:
		remote_templates = MetaProvider(settings).fetch_templates()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: failed to refresh Meta template statuses")
		return

	status_map = {"APPROVED": "Approved", "PENDING": "Pending", "REJECTED": "Rejected"}
	for t in remote_templates:
		local_name = frappe.db.get_value("Whatsnext Message Template", {"meta_template_id": t.get("id")})
		if not local_name:
			continue
		new_status = status_map.get(t.get("status"))
		if new_status:
			frappe.db.set_value("Whatsnext Message Template", local_name, "approval_status", new_status)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job
