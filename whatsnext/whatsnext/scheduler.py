import frappe
from frappe.utils import now_datetime, add_to_date

# Most documents a Scheduled notification handles per 5-minute run (sends are
# synchronous here, so this keeps a run inside the job time limit); any
# remainder is picked up by the following runs.
POLL_BATCH_LIMIT = 200


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
	from whatsnext.whatsnext.conversations import touch_conversation
	from whatsnext.whatsnext.doctype.whatsnext_message.whatsnext_message import publish_message_event

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
		# Place it in the chat timeline (and at the top of the chat list) when
		# it actually goes out, not when it was scheduled.
		frappe.db.set_value("Whatsnext Message", msg.name, "creation", now_datetime(), update_modified=False)
		msg.reload()
		touch_conversation(msg, sending_scheduled=True)
		# Media-header templates need their header URL back, which lives on
		# the message's attach field -- without it Meta rejects the send.
		_dispatch(msg, template_doc=template_doc, params=params, header_media_url=msg.attach or None)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job, one message at a time

		msg.reload()
		publish_message_event(msg, event="whatsnext_new_message")


def start_scheduled_campaigns():
	"""Runs every 5 minutes. Starts campaigns whose scheduled_time has arrived."""
	due = frappe.get_all(
		"Whatsnext Campaign",
		filters={"status": "Scheduled", "scheduled_time": ["<=", now_datetime()]},
		pluck="name",
	)
	if not due:
		return

	from whatsnext.whatsnext.campaign_engine import start_campaign

	for name in due:
		# Re-check under a row lock: the campaign may have been started,
		# paused or cancelled by hand since the list above was read.
		if frappe.db.get_value("Whatsnext Campaign", name, "status", for_update=True) != "Scheduled":
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job; release the row lock
			continue
		frappe.db.set_value("Whatsnext Campaign", name, "status", "Queued")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job; status must land before the worker picks it up
		start_campaign(name)


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
		fields=["name", "conversation_id", "type"],
	)
	from whatsnext.whatsnext.conversations import record_outgoing_failed

	for row in stuck:
		frappe.db.set_value(
			"Whatsnext Message", row.name,
			{"status": "Failed", "error_message": "Stuck in Pending/Queued for >30min — auto-marked Failed by safety-net job."},
			update_modified=True,
		)
		if row.type == "Outgoing":
			record_outgoing_failed(row.conversation_id)
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


def dispatch_scheduled_doctype_notifications():
	"""Runs every 5 minutes. Polling counterpart to the realtime doc_events
	wired in hooks.py: covers any Whatsnext Notification configured with
	Event = "Scheduled", which is how a doctype outside hooks.py's curated
	WATCHED_DOCTYPES list still gets full coverage instead of silently
	doing nothing (see whatsnext_notification.py's validate(), which
	refuses to save any other combination for an unwatched doctype).

	Approximate by nature: this catches anything with `modified` newer than
	the notification's own last_polled timestamp, so distinct inserts vs.
	updates aren't distinguished the way realtime on_submit/on_update are —
	same document changed twice inside one polling window only notifies
	once. That tradeoff is what makes arbitrary-doctype coverage possible
	without a dedicated doc_events hook for each one.
	"""
	from whatsnext.whatsnext.notification_engine import _fire

	notifications = frappe.get_all(
		"Whatsnext Notification",
		filters={"event": "Scheduled", "enabled": 1},
		fields=["name", "reference_doctype", "last_polled"],
	)
	if not notifications:
		return

	# Upper bound fixed once per run: a document saved while this run is
	# going belongs to the next run. Without it, a save landing between the
	# query and the bookmark update was notified twice.
	now = now_datetime()
	for row in notifications:
		if not row.reference_doctype:
			continue

		since = row.last_polled or add_to_date(now, minutes=-5)
		try:
			# Oldest first, and no silent cap: with a 200-row limit and the
			# bookmark then jumped to `now`, every change past the 200th in a
			# 5-minute window was skipped for good.
			changed = frappe.get_all(
				row.reference_doctype,
				filters=[["modified", ">", since], ["modified", "<=", now]],
				fields=["name", "modified"],
				order_by="modified asc, name asc",
				limit_page_length=POLL_BATCH_LIMIT,
			)
		except Exception:
			# Doctype renamed/removed since this notification was configured,
			# or some other lookup failure — log once and move on rather than
			# letting one bad config break the whole polling run.
			frappe.log_error(
				frappe.get_traceback(),
				f"Whatsnext Scheduled notification '{row.name}': couldn't query '{row.reference_doctype}'",
			)
			continue

		if changed:
			notif = frappe.get_cached_doc("Whatsnext Notification", row.name)
			for c in changed:
				doc = frappe.get_doc(row.reference_doctype, c.name)
				try:
					_fire(notif, doc)
				except Exception:
					frappe.log_error(
						frappe.get_traceback(),
						f"Whatsnext Scheduled notification '{row.name}' failed for {row.reference_doctype} {c.name}",
					)

		# A full batch means there may be more: resume after the last one
		# handled next run rather than skipping past the rest.
		bookmark = changed[-1].modified if len(changed) >= POLL_BATCH_LIMIT else now
		frappe.db.set_value("Whatsnext Notification", row.name, "last_polled", bookmark, update_modified=False)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job


def refresh_template_approval_status():
	"""Daily: pull Meta template approval statuses so locally-created templates
	reflect real WhatsApp Business Manager review outcomes, and refresh the
	header sample links. Those links expire after about a month, and image,
	video and document templates are sent with them (from chat and
	campaigns), so without this every such send started failing once the
	link ran out unless someone remembered to re-sync."""
	settings = frappe.get_cached_doc("Whatsnext Settings")
	if not settings.meta_enabled:
		return

	from whatsnext.whatsnext.provider_engine import MetaProvider

	try:
		remote_templates = MetaProvider(settings).fetch_templates()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Whatsnext: failed to refresh Meta template statuses")
		return

	from whatsnext.whatsnext.api import is_meta_hosted_url, meta_header_sample_url

	status_map = {"APPROVED": "Approved", "PENDING": "Pending", "REJECTED": "Rejected"}
	for t in remote_templates:
		local = frappe.db.get_value(
			"Whatsnext Message Template", {"meta_template_id": t.get("id")},
			["name", "header_example_url"], as_dict=True,
		)
		if not local:
			continue
		updates = {}
		new_status = status_map.get(t.get("status"))
		if new_status:
			updates["approval_status"] = new_status
		sample_url = meta_header_sample_url(t)
		if sample_url and sample_url != local.header_example_url and is_meta_hosted_url(local.header_example_url):
			updates["header_example_url"] = sample_url
		if updates:
			frappe.db.set_value("Whatsnext Message Template", local.name, updates)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job
