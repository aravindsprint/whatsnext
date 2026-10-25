"""Regression tests for the fixes from the October 2026 code review."""

import datetime as dt
import json
import re
import sqlite3
import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from whatsnext.whatsnext import campaign_engine, contacts, conversations, notification_engine, scheduler
from whatsnext.whatsnext.api import webhook


class FakeCache:
	def __init__(self):
		self.store = {}

	def get_value(self, key):
		return self.store.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.store[key] = value

	def delete_value(self, key):
		self.store.pop(key, None)


@pytest.fixture
def cache(frappe):
	fake = FakeCache()
	frappe.cache = lambda: fake
	yield fake
	del frappe.cache


# 1. Date/Datetime/Decimal values in notification parameters --------------

def test_param_text_formats_non_string_values(frappe, monkeypatch):
	monkeypatch.setattr(frappe.utils, "formatdate", lambda d: d.strftime("%d-%m-%Y"), raising=False)
	monkeypatch.setattr(frappe.utils, "format_datetime", lambda d: d.strftime("%d-%m-%Y %H:%M"), raising=False)

	assert notification_engine.param_text(dt.date(2026, 10, 25)) == "25-10-2026"
	assert notification_engine.param_text(dt.datetime(2026, 10, 25, 9, 30)) == "25-10-2026 09:30"
	assert notification_engine.param_text(Decimal("1500.50")) == "1500.50"
	assert notification_engine.param_text(dt.time(9, 30)) == "09:30:00"
	assert notification_engine.param_text("SINV-1") == "SINV-1"
	assert notification_engine.param_text(1500.5) == 1500.5
	assert notification_engine.param_text(None) is None


def test_fire_sends_json_serializable_params_for_date_fields(frappe, monkeypatch):
	monkeypatch.setattr(frappe.utils, "formatdate", lambda d: d.isoformat(), raising=False)
	sent = {}
	from whatsnext.whatsnext import api

	monkeypatch.setattr(api, "send_template_message", lambda **kw: sent.update(kw))

	notif = frappe._dict(
		name="Invoice due", condition=None, fixed_number=None, recipient_number_field="contact_mobile",
		attach_document_print=0, template="invoice_due", provider=None,
		field_mapping=[
			frappe._dict(template_variable="1", source_fieldname="name", static_value=None),
			frappe._dict(template_variable="2", source_fieldname="due_date", static_value=None),
		],
	)
	doc = frappe._dict(doctype="Sales Invoice", name="SINV-1", contact_mobile="9876543210", due_date=dt.date(2026, 11, 1))

	notification_engine._fire(notif, doc)

	assert sent["parameters"] == {"1": "SINV-1", "2": "2026-11-01"}
	json.dumps(sent["parameters"])  # used to raise TypeError for the date


# 3. Contact lookup ignores how the stored number is formatted -------------

@pytest.mark.parametrize("stored", ["+91 98765 43210", "+91-98765-43210", "(+91) 98765.43210", "919876543210"])
def test_resolve_contact_matches_formatted_numbers(frappe, stored):
	db = sqlite3.connect(":memory:")
	db.execute("CREATE TABLE `tabContact Phone` (parent, parenttype, phone, is_primary_mobile_no, is_primary_phone)")
	db.execute("INSERT INTO `tabContact Phone` VALUES ('Ravi', 'Contact', ?, 1, 0)", (stored,))

	frappe.db.sql = lambda query, values: db.execute(query.replace("%s", "?"), values).fetchall()

	assert contacts.resolve_contact_from_phone("919876543210") == "Ravi"
	assert contacts.resolve_contact_from_phone("1234567890") is None


# 4. Outbound normalization of trunk "0" and international "00" ------------

@pytest.mark.parametrize("raw,expected", [
	("09876543210", "919876543210"),
	("0 98765 43210", "919876543210"),
	("0091 98765 43210", "919876543210"),
	("0044 7911 123456", "447911123456"),
	("9876543210", "919876543210"),
	("+91 98765 43210", "919876543210"),
])
def test_normalize_handles_dialling_prefixes(frappe, raw, expected):
	assert contacts.normalize_outbound_number(raw) == expected
	# Normalizing an already-normalized number must not change it.
	assert contacts.normalize_outbound_number(expected) == expected


# 2. Long campaigns hand off to a new job instead of being killed ----------

def _campaign(frappe, monkeypatch, rows):
	campaign = MagicMock(status="Queued", template="promo", provider=None, recipients=rows)
	campaign.name = "Diwali"
	template = MagicMock(category="Utility", language="en", header_example_url=None, header_type=None, body="Hi")
	template.name = "promo"
	frappe.get_doc = MagicMock(side_effect=lambda doctype, name=None: campaign if doctype == "Whatsnext Campaign" else template)
	frappe.db.sql = MagicMock(return_value=[])
	monkeypatch.setattr(campaign_engine.time, "sleep", lambda s: None)
	return campaign


def test_campaign_hands_off_before_job_timeout(frappe, monkeypatch):
	rows = [MagicMock(status="Pending", parameters="{}", to_number="919876543210") for _ in range(3)]
	_campaign(frappe, monkeypatch, rows)
	provider = MagicMock()
	monkeypatch.setattr(campaign_engine, "get_provider", lambda name=None: provider)
	clock = iter([0, campaign_engine.RUN_BUDGET_SECONDS + 1])
	monkeypatch.setattr(campaign_engine.time, "monotonic", lambda: next(clock))

	campaign_engine.run_campaign("Diwali")

	provider.send_template.assert_not_called()
	frappe.enqueue.assert_called_once()
	assert frappe.enqueue.call_args.args[0] == "whatsnext.whatsnext.campaign_engine.run_campaign"
	assert frappe.enqueue.call_args.kwargs["campaign_name"] == "Diwali"
	assert campaign_engine.RUN_BUDGET_SECONDS < campaign_engine.JOB_TIMEOUT_SECONDS


# 5. Scheduled-notification polling keeps its place --------------------------

def _poll(frappe, monkeypatch, changed_count):
	notif_row = frappe._dict(name="Daily", reference_doctype="Issue", last_polled=dt.datetime(2026, 10, 24, 11, 55))
	changed = [
		frappe._dict(name=f"ISS-{i}", modified=dt.datetime(2026, 10, 24, 11, 56) + dt.timedelta(seconds=i))
		for i in range(changed_count)
	]
	calls = []

	def get_all(doctype, **kwargs):
		calls.append((doctype, kwargs))
		return [notif_row] if doctype == "Whatsnext Notification" else changed

	frappe.get_all = get_all
	frappe.get_cached_doc = MagicMock()
	frappe.get_doc = MagicMock()
	monkeypatch.setattr(notification_engine, "_fire", lambda notif, doc: None)
	scheduler.dispatch_scheduled_doctype_notifications()
	bookmark = frappe.db.set_value.call_args.args[3]
	return calls[1][1], changed, bookmark


def test_poll_resumes_after_a_full_batch(frappe, monkeypatch):
	query, changed, bookmark = _poll(frappe, monkeypatch, scheduler.POLL_BATCH_LIMIT)
	assert query["order_by"] == "modified asc, name asc"
	assert bookmark == changed[-1].modified  # not "now": the rest come next run


def test_poll_bounds_the_window_and_advances_to_now(frappe, monkeypatch):
	query, _, bookmark = _poll(frappe, monkeypatch, 3)
	now = frappe.utils.now_datetime()
	assert ["modified", "<=", now] in query["filters"]
	assert bookmark == now


# 6. Concurrency guards take a row lock -------------------------------------

def test_start_campaign_locks_the_row(frappe):
	from whatsnext.whatsnext import api

	frappe.get_doc = MagicMock()
	frappe.db.get_value = MagicMock(return_value=("Queued", None))
	with pytest.raises(Exception, match="already queued"):
		api.start_campaign("Diwali")
	assert frappe.db.get_value.call_args.kwargs.get("for_update") is True


def test_away_reply_claim_locks_the_row(frappe, monkeypatch):
	frappe.settings.away_enabled = 1
	frappe.settings.away_message = "We're closed"
	frappe.settings.away_cooldown_hours = 12
	monkeypatch.setattr(conversations, "is_business_hours", lambda s: False)
	frappe.db.get_value = MagicMock(return_value=dt.datetime(2026, 10, 24, 11, 0))  # replied an hour ago

	conversations.send_away_reply("919876543210")

	assert frappe.db.get_value.call_args.kwargs.get("for_update") is True
	frappe.db.set_value.assert_not_called()


# 7. Receipts that arrive before the message id is saved ---------------------

def test_early_receipt_is_kept_and_replayed(frappe, cache, monkeypatch):
	frappe.get_all = MagicMock(return_value=[])
	frappe.db.get_value = MagicMock(return_value=None)

	webhook._apply_status_update("wamid.1", "Delivered")

	frappe.db.set_value.assert_not_called()
	assert cache.store["whatsnext:early_status:wamid.1"] == [{"status": "Delivered", "error": None}]

	row = frappe._dict(name="MSG-1", status="Sent", conversation_id="919876543210", type="Outgoing",
	                   customer=None, reference_doctype=None, reference_name=None)
	frappe.db.get_value = MagicMock(return_value=row)

	webhook.apply_early_statuses("wamid.1")

	frappe.db.set_value.assert_called_once_with("Whatsnext Message", "MSG-1", {"status": "Delivered"})
	assert "whatsnext:early_status:wamid.1" not in cache.store


def test_receipt_found_on_recheck_is_applied_now(frappe, cache):
	frappe.get_all = MagicMock(return_value=[])
	row = frappe._dict(name="MSG-1", status="Sent", conversation_id="919876543210", type="Outgoing",
	                   customer=None, reference_doctype=None, reference_name=None)
	# Not visible on the first read; committed by the sender before the re-read.
	frappe.db.get_value = MagicMock(side_effect=[None, row])

	webhook._apply_status_update("wamid.2", "Read")

	frappe.db.set_value.assert_called_once_with("Whatsnext Message", "MSG-1", {"status": "Read"})
	assert cache.store == {}


# 8, 9. Notes and permission checks ----------------------------------------

def test_delete_missing_note_gives_a_clear_error(frappe):
	from whatsnext.whatsnext import api

	frappe.db.get_value = MagicMock(return_value=None)
	with pytest.raises(frappe.ValidationError, match="no longer exists"):
		api.delete_note("gone")


def test_update_template_provider_ids_checks_write_permission(frappe):
	from whatsnext.whatsnext import api

	template = MagicMock()
	template.check_permission.side_effect = frappe.PermissionError("no")
	frappe.get_doc = MagicMock(return_value=template)
	with pytest.raises(frappe.PermissionError):
		api.update_template_provider_ids("promo", "HX123")
	template.check_permission.assert_called_once_with("write")
	frappe.db.set_value.assert_not_called()


def test_get_campaign_checks_read_permission(frappe):
	from whatsnext.whatsnext import api

	campaign = MagicMock()
	campaign.check_permission.side_effect = frappe.PermissionError("no")
	frappe.get_doc = MagicMock(return_value=campaign)
	with pytest.raises(frappe.PermissionError):
		api.get_campaign("Diwali")
	campaign.check_permission.assert_called_once_with("read")


# 10. Missing Meta App Secret is flagged --------------------------------------

def test_settings_warns_without_meta_app_secret(frappe):
	from whatsnext.whatsnext.doctype.whatsnext_settings.whatsnext_settings import WhatsnextSettings

	frappe.msgprint = MagicMock()
	settings = WhatsnextSettings()
	settings.meta_enabled, settings.twilio_enabled, settings.meta_phone_number_id = 1, 0, "PNID"
	passwords = {"meta_access_token": "TOKEN"}
	settings.get_password = lambda key, raise_exception=True: passwords.get(key)

	settings.validate()
	assert "Meta App Secret" in frappe.msgprint.call_args.args[0]

	frappe.msgprint.reset_mock()
	passwords["meta_app_secret"] = "SECRET"
	settings.validate()
	frappe.msgprint.assert_not_called()


def test_unsigned_webhook_is_logged_once_a_day(frappe, cache):
	frappe.local.request = types.SimpleNamespace(headers={}, get_data=lambda: b"{}")
	assert webhook._meta_signature_ok()
	assert webhook._meta_signature_ok()
	assert frappe.log_error.call_count == 1
