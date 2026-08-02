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

from whatsnext.whatsnext.provider_engine import get_provider, WhatsAppSendError

# Conservative default: 1 message/second stays well under Meta's lowest
# messaging tier (250 unique recipients/24h has no per-second cap, but
# bursting fast against Twilio's default trial rate limits fails fast).
# Override via WhatsApp Settings in a future iteration if a client needs
# faster throughput and has a qualified/verified sending number.
SEND_INTERVAL_SECONDS = 1.0


def start_campaign(campaign_name: str):
	"""Enqueues the actual send loop. Kept separate from create_campaign so
	campaigns can be re-queued (e.g. retry failed recipients) without
	recreating the doc."""
	frappe.enqueue(
		"whatsnext.whatsnext.campaign_engine.run_campaign",
		queue="long",
		timeout=3600,
		job_name=f"whatsnext-campaign-{campaign_name}",
		campaign_name=campaign_name,
	)


def run_campaign(campaign_name: str):
	campaign = frappe.get_doc("Whatsnext Campaign", campaign_name)
	campaign.db_set("status", "Sending", update_modified=False)

	template = frappe.get_doc("Whatsnext Message Template", campaign.template)
	provider_name = campaign.provider or None

	sent = delivered = failed = 0

	for row in campaign.recipients:
		if row.status != "Pending":
			# already processed (e.g. this is a retry run) — just fold its
			# current status into the running totals and move on
			if row.status == "Failed":
				failed += 1
			else:
				sent += 1
			continue

		params = {}
		if row.parameters:
			try:
				params = json.loads(row.parameters) if isinstance(row.parameters, str) else row.parameters
			except Exception:
				params = {}

		try:
			provider = get_provider(provider_name)
			result = provider.send_template(row.to_number, template.name, params, template.language)

			msg = frappe.get_doc({
				"doctype": "Whatsnext Message",
				"type": "Outgoing",
				"provider": provider.name,
				"status": "Sent",
				"to_number": row.to_number,
				"message": template.body,
				"message_type": "Template",
				"content_type": "text",
				"template": template.name,
				"template_parameters": json.dumps(params),
				"reference_doctype": "Whatsnext Campaign",
				"reference_name": campaign.name,
			})
			msg.insert(ignore_permissions=True)

			provider_message_id = _extract_provider_message_id(provider.name, result)
			if provider_message_id:
				msg.db_set("provider_message_id", provider_message_id, update_modified=False)

			row.db_set("status", "Sent", update_modified=False)
			row.db_set("message", msg.name, update_modified=False)
			sent += 1

		except WhatsAppSendError as e:
			row.db_set("status", "Failed", update_modified=False)
			row.db_set("error_message", str(e)[:140], update_modified=False)
			failed += 1
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Whatsnext campaign send failed: {campaign_name} -> {row.to_number}")
			row.db_set("status", "Failed", update_modified=False)
			row.db_set("error_message", str(e)[:140], update_modified=False)
			failed += 1

		# write progress after every send so the frontend's poll reflects
		# reality, not just the final count once the whole job finishes
		campaign.db_set("sent_count", sent, update_modified=False)
		campaign.db_set("failed_count", failed, update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long-running background job, must persist progress incrementally

		time.sleep(SEND_INTERVAL_SECONDS)

	campaign.db_set("status", "Completed" if failed == 0 else "Failed" if sent == 0 else "Completed", update_modified=False)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- final state must land


def _extract_provider_message_id(provider_name, result):
	if provider_name == "Meta":
		msgs = result.get("messages") or []
		return msgs[0].get("id") if msgs else None
	if provider_name == "Twilio":
		return result.get("sid")
	return None
