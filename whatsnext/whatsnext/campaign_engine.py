"""Bulk campaign dispatch.

Runs as a background job (queue="long") so a campaign of hundreds/thousands
of recipients doesn't block a web worker or hit the request timeout. Sends
are deliberately paced (SEND_INTERVAL_SECONDS between each) — WhatsApp
Business API rate limits are tiered by phone number quality/volume, and
blasting as fast as possible is the single most common way integrations get
throttled or the number gets flagged. Progress is written back to the
Campaign doc after every send so the frontend can poll and show a live
progress bar instead of waiting for the whole batch to finish.
"""

import json
import time

import frappe

from whatsnext.whatsnext.contacts import normalize_outbound_number, resolve_customer_from_phone
from whatsnext.whatsnext.provider_engine import get_provider, WhatsAppSendError

# Conservative default: 1 message/second stays well under Meta's lowest
# messaging tier (250 unique recipients/24h has no per-second cap, but
# bursting fast against Twilio's default trial rate limits fails fast).
# Adjustable via Whatsnext Settings → Campaign Send Interval for a client
# with a qualified/verified, higher-tier sending number.
SEND_INTERVAL_SECONDS = 1.0
MIN_SEND_INTERVAL_SECONDS = 0.1

# The worker kills a job after JOB_TIMEOUT_SECONDS. At 1 send/second a
# campaign of more than ~3,600 recipients used to be killed mid-run, left
# "Sending", then force-failed by the stuck-campaign safety net with the rest
# of its recipients never messaged. Each run now stops well inside the limit
# and queues a fresh job that carries on with the recipients still Pending.
JOB_TIMEOUT_SECONDS = 3600
RUN_BUDGET_SECONDS = 45 * 60


def _send_interval():
	"""Configurable in Whatsnext Settings (Campaign Send Interval)."""
	value = frappe.get_cached_doc("Whatsnext Settings").get("campaign_send_interval")
	try:
		value = float(value) if value not in (None, "") else SEND_INTERVAL_SECONDS
	except (TypeError, ValueError):
		value = SEND_INTERVAL_SECONDS
	return max(MIN_SEND_INTERVAL_SECONDS, value)


def start_campaign(campaign_name: str):
	"""Enqueues the actual send loop. Kept separate from create_campaign so
	campaigns can be re-queued (e.g. retry failed recipients) without
	recreating the doc."""
	frappe.enqueue(
		"whatsnext.whatsnext.campaign_engine.run_campaign",
		queue="long",
		timeout=JOB_TIMEOUT_SECONDS,
		job_name=f"whatsnext-campaign-{campaign_name}",
		campaign_name=campaign_name,
	)


def _recount(campaign_name):
	"""Counts straight from the recipient rows. Delivery webhooks move rows
	on (Delivered/Read, or Failed after Sent) while a run is in progress, so
	running totals kept in memory drift."""
	counts = dict(frappe.db.sql(
		"""SELECT status, COUNT(*) FROM `tabWhatsnext Campaign Recipient`
		WHERE parent = %s AND parenttype = 'Whatsnext Campaign' GROUP BY status""",
		(campaign_name,),
	))
	delivered = counts.get("Delivered", 0) + counts.get("Read", 0)
	return {
		"sent_count": counts.get("Sent", 0) + delivered,
		"delivered_count": delivered,
		"failed_count": counts.get("Failed", 0),
		"skipped_count": counts.get("Skipped", 0),
		"pending": counts.get("Pending", 0),
	}


def run_campaign(campaign_name: str):
	from whatsnext.whatsnext.api import _render_body
	from whatsnext.whatsnext.conversations import is_opted_out

	campaign = frappe.get_doc("Whatsnext Campaign", campaign_name)
	if campaign.status not in ("Queued", "Sending"):
		return  # paused/cancelled before the job started
	# update_modified=True throughout: scheduler.recover_stuck_messages marks
	# any campaign whose `modified` is >30 minutes old as Failed. With
	# update_modified=False a healthy campaign of more than ~1,800
	# recipients (paced at 1/s) was force-failed mid-run.
	campaign.db_set("status", "Sending")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job, status must be visible to the UI's poll

	template = frappe.get_doc("Whatsnext Message Template", campaign.template)
	provider_name = campaign.provider or None
	respect_opt_out = template.category == "Marketing"
	interval = _send_interval()
	started = time.monotonic()

	for i, row in enumerate(campaign.recipients):
		if row.status != "Pending":
			continue  # already processed (e.g. a resumed or retried run)

		if time.monotonic() - started > RUN_BUDGET_SECONDS:
			# Out of time for this job: save progress and continue in a new
			# one (status stays "Sending", so the next job proceeds).
			campaign.db_set(_counts_only(campaign_name))
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job, hand-off must see saved progress
			start_campaign(campaign_name)
			return

		# Pause/cancel is checked between sends so it takes effect within a
		# second instead of after the whole list.
		if i % 5 == 0:
			current = frappe.db.get_value("Whatsnext Campaign", campaign_name, "status")
			if current in ("Paused", "Cancelled"):
				campaign.db_set(_counts_only(campaign_name))
				frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job
				return

		params = {}
		if row.parameters:
			try:
				params = json.loads(row.parameters) if isinstance(row.parameters, str) else row.parameters
			except Exception:
				params = {}

		to_number = normalize_outbound_number(row.to_number)

		if respect_opt_out and is_opted_out(to_number):
			row.db_set({"status": "Skipped", "error_message": "Opted out of promotional messages"}, update_modified=False)
			campaign.db_set(_counts_only(campaign_name))
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job
			continue

		try:
			provider = get_provider(provider_name)
			# Media-header templates need a header link (same fallback the
			# chat UI pre-fills); without one Meta rejects every send.
			result = provider.send_template(
				to_number, template.name, params, template.language or "en",
				header_media_url=template.header_example_url or None,
				header_type=template.header_type,
			)

			msg = frappe.get_doc({
				"doctype": "Whatsnext Message",
				"type": "Outgoing",
				"provider": provider.name,
				"status": "Sent",
				"to_number": to_number,
				# Linked to the customer like every other outgoing message, so
				# campaign sends appear in the assigned Sales Person's chats.
				"customer": resolve_customer_from_phone(to_number),
				"message": _render_body(template.body, params),
				"message_type": "Template",
				"content_type": "text",
				"template": template.name,
				"template_parameters": json.dumps(params, default=str),
				"reference_doctype": "Whatsnext Campaign",
				"reference_name": campaign.name,
				"is_automated": 1,
			})
			msg.insert(ignore_permissions=True)

			provider_message_id = _extract_provider_message_id(provider.name, result)
			if provider_message_id:
				msg.db_set("provider_message_id", provider_message_id, update_modified=False)

			row.db_set({"status": "Sent", "message": msg.name, "error_message": ""}, update_modified=False)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job; receipts must be able to match this message
			if provider_message_id:
				from whatsnext.whatsnext.api.webhook import apply_early_statuses

				apply_early_statuses(provider_message_id)

		except WhatsAppSendError as e:
			row.db_set({"status": "Failed", "error_message": str(e)[:140]}, update_modified=False)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Whatsnext campaign send failed: {campaign_name} -> {row.to_number}")
			row.db_set({"status": "Failed", "error_message": str(e)[:140]}, update_modified=False)

		# write progress after every send so the frontend's poll reflects
		# reality, not just the final count once the whole job finishes
		campaign.db_set(_counts_only(campaign_name))
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long-running background job, must persist progress incrementally

		time.sleep(interval)

	counts = _counts_only(campaign_name)
	counts["status"] = "Failed" if counts["sent_count"] == 0 and counts["failed_count"] else "Completed"
	campaign.db_set(counts)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- final state must land


def _counts_only(campaign_name):
	counts = _recount(campaign_name)
	counts.pop("pending")
	return counts


def _extract_provider_message_id(provider_name, result):
	if provider_name == "Meta":
		msgs = result.get("messages") or []
		return msgs[0].get("id") if msgs else None
	if provider_name == "Twilio":
		return result.get("sid")
	return None
