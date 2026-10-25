import datetime as dt
import types

import pytest

from conftest import make_settings
from whatsnext.whatsnext import campaign_engine, permissions
from whatsnext.whatsnext.api import _render_body
from whatsnext.whatsnext.contacts import _normalize_phone, normalize_outbound_number
from whatsnext.whatsnext.conversations import is_business_hours


def test_render_body_fills_known_variables():
	assert _render_body("Hi {{1}}, order {{2}} {{3}}", {"1": "Ravi", "2": "SO-1"}) == "Hi Ravi, order SO-1 {{3}}"


@pytest.mark.parametrize("raw,expected", [
	("9894088422", "919894088422"),
	("+91 98940 88422", "919894088422"),
	("919894088422", "919894088422"),
	("+1 (415) 523-8886", "14155238886"),
])
def test_normalize_outbound_number(frappe, raw, expected):
	assert normalize_outbound_number(raw) == expected


def test_normalize_phone_matches_on_last_ten_digits():
	assert _normalize_phone("+91 98765 43210") == _normalize_phone("09876543210") == "9876543210"


@pytest.mark.parametrize("when,expected", [
	(dt.datetime(2026, 10, 24, 10, 0), True),    # Saturday, open
	(dt.datetime(2026, 10, 24, 18, 0), False),   # closing time is exclusive
	(dt.datetime(2026, 10, 25, 10, 0), False),   # Sunday
	(dt.datetime(2026, 10, 26, 8, 59), False),   # Monday before opening
])
def test_business_hours(frappe, when, expected):
	assert is_business_hours(make_settings(), when) is expected


def test_overnight_business_hours(frappe):
	s = make_settings(business_days="", business_hours_start="20:00:00", business_hours_end="02:00:00")
	assert is_business_hours(s, dt.datetime(2026, 10, 24, 23, 0))
	assert is_business_hours(s, dt.datetime(2026, 10, 24, 1, 0))
	assert not is_business_hours(s, dt.datetime(2026, 10, 24, 3, 0))


def test_holiday_closes_the_day(frappe):
	frappe.db.exists.return_value = True
	assert not is_business_hours(make_settings(holiday_list="India 2026"), dt.datetime(2026, 10, 24, 10, 0))


@pytest.mark.parametrize("value,expected", [(None, 1.0), ("", 1.0), (0.5, 0.5), (0, 0.1), ("abc", 1.0), (2, 2.0)])
def test_campaign_send_interval(frappe, value, expected):
	frappe.settings.campaign_send_interval = value
	assert campaign_engine._send_interval() == expected


def _req(path):
	return types.SimpleNamespace(path=path)


def test_require_app_user_blocks_portal_users(frappe):
	frappe.local.request = _req("/api/method/whatsnext.whatsnext.api.send_message")
	frappe.get_roles.return_value = ["Customer"]
	frappe.session.user = "customer@example.com"
	with pytest.raises(frappe.PermissionError):
		permissions.require_app_user()


def test_require_app_user_allows_agents_and_internal_calls(frappe):
	frappe.get_roles.return_value = ["Customer"]
	frappe.session.user = "customer@example.com"
	# Internal call from a webhook request (opt-out confirmation, away reply)
	frappe.local.request = _req("/api/method/whatsnext.whatsnext.api.webhook.meta_webhook")
	permissions.require_app_user()
	# Internal call during a Desk save (notification enqueue path)
	frappe.local.request = _req("/api/method/frappe.desk.form.save.savedocs")
	permissions.require_app_user()
	# Background job: no request at all
	frappe.local.request = None
	permissions.require_app_user()
	# Agents pass
	frappe.local.request = _req("/api/v2/method/whatsnext.whatsnext.api.send_message")
	frappe.get_roles.return_value = ["Whatsnext User"]
	permissions.require_app_user()
	# v2 path for a non-agent is blocked too
	frappe.get_roles.return_value = ["Customer"]
	with pytest.raises(frappe.PermissionError):
		permissions.require_app_user()


def test_whoami_hides_staff_list_from_non_agents(frappe):
	from unittest.mock import MagicMock

	from whatsnext.whatsnext import api

	frappe.get_all = MagicMock(return_value=["agent@example.com"])
	frappe.get_roles.return_value = ["Customer"]
	frappe.session.user = "customer@example.com"
	result = api.whoami()
	assert result["has_access"] is False
	assert result["agents"] == []
	frappe.get_all.assert_not_called()

	frappe.get_roles.return_value = ["Whatsnext User"]
	frappe.get_all = MagicMock(side_effect=[["agent@example.com"], [{"name": "agent@example.com", "full_name": "Agent"}]])
	result = api.whoami()
	assert result["has_access"] is True
	assert result["agents"] == [{"name": "agent@example.com", "full_name": "Agent"}]
