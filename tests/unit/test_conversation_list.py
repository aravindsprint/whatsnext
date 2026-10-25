import datetime as dt
from types import SimpleNamespace

import pytest

from whatsnext.whatsnext import conversations as conv
from whatsnext.whatsnext.api import build_conversation_where


def test_unrestricted_all_hides_closed_only():
	where, params = build_conversation_where(None, filter="all")
	assert where == "(status IS NULL OR status != 'Closed')"
	assert params == {}


def test_restricted_user_scope():
	where, params = build_conversation_where(["CUST-1", "CUST-2"], filter="all")
	assert "customer IN %(customers)s" in where
	assert params["customers"] == ("CUST-1", "CUST-2")
	where, _ = build_conversation_where([], filter="all")
	assert "(customer IS NULL OR customer = '')" in where


@pytest.mark.parametrize("flt,fragment", [
	("closed", "status = 'Closed'"),
	("unread", "unread_count > 0"),
	("mine", "assigned_to = %(user)s"),
	("incoming", "last_message_type = 'Incoming'"),
	("outgoing", "last_message_type = 'Outgoing'"),
])
def test_filters(flt, fragment):
	where, params = build_conversation_where(None, filter=flt, user="me@example.com")
	assert fragment in where
	if flt == "mine":
		assert params["user"] == "me@example.com"
	if flt != "closed":
		assert "status != 'Closed'" in where


def test_search_and_stats_mode():
	where, params = build_conversation_where(None, search="ravi")
	assert where == "(name LIKE %(search)s OR profile_name LIKE %(search)s)"  # no open/closed filter for header totals
	assert params["search"] == "%ravi%"


def test_unknown_filter_rejected(frappe):
	with pytest.raises(frappe.ValidationError):
		build_conversation_where(None, filter="drop table")


@pytest.mark.parametrize("msg,expected", [
	({"message": "Hello\nthere"}, "Hello there"),
	({"message": "", "template": "order_update"}, "📋 order_update"),
	({"message": "", "content_type": "image"}, "📷 Photo"),
	({"message": "", "content_type": "location"}, "📍 Location"),
	({"message": "x" * 300}, "x" * 140),
])
def test_message_preview(msg, expected):
	assert conv.message_preview(msg) == expected


def _msg(**kw):
	base = dict(name="M1", conversation_id="919876543210", type="Incoming", status="Delivered",
	            creation=dt.datetime(2026, 10, 25, 9, 0), customer=None, contact=None,
	            profile_name="Ravi", message="Hi", template=None, content_type="text", scheduled_time=None)
	base.update(kw)
	ns = SimpleNamespace(**base)
	ns.get = lambda k, d=None: getattr(ns, k, d)
	return ns


def _sql_calls(frappe):
	return [c.args[0] for c in frappe.db.sql.call_args_list]


def test_incoming_bumps_unread_atomically(frappe):
	frappe.db.exists.return_value = True
	conv.touch_conversation(_msg())
	updates = frappe.db.set_value.call_args.args[2]
	assert updates["last_message"] == "Hi"
	assert updates["last_message_type"] == "Incoming"
	assert updates["status"] == "Open"
	(sql,) = _sql_calls(frappe)
	assert "unread_count" in sql and "+ %(delta)s" in sql
	assert frappe.db.sql.call_args.args[1]["delta"] == 1


def test_outgoing_bumps_sent_count(frappe):
	frappe.db.exists.return_value = True
	conv.touch_conversation(_msg(type="Outgoing", status="Pending", profile_name=None))
	assert "outgoing_count" in _sql_calls(frappe)[0]
	assert "status" not in frappe.db.set_value.call_args.args[2]  # our message doesn't reopen a closed chat


def test_unsent_scheduled_message_is_ignored_until_sent(frappe):
	scheduled = _msg(type="Outgoing", status="Pending", scheduled_time=dt.datetime(2026, 10, 26))
	conv.touch_conversation(scheduled)
	frappe.db.set_value.assert_not_called()
	frappe.db.exists.return_value = True
	conv.touch_conversation(scheduled, sending_scheduled=True)
	frappe.db.set_value.assert_called()


def test_failed_send_decrements_but_never_below_zero(frappe):
	conv.record_outgoing_failed("919876543210")
	sql = _sql_calls(frappe)[0]
	assert "GREATEST(" in sql and frappe.db.sql.call_args.args[1]["delta"] == -1
