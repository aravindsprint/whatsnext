"""Lightweight stand-in for the `frappe` package so the app's pure logic
(payload building, parsing, permission gating, scheduling rules) can be
unit-tested in CI without a bench, MariaDB or Redis.

Integration tests that need a real site live in
whatsnext/whatsnext/tests/ and run with `bench run-tests --app whatsnext`.
"""

import datetime as dt
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)


class _Dict(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class PermissionError(Exception):
	pass


class ValidationError(Exception):
	pass


class DuplicateEntryError(Exception):
	pass


def _throw(msg, exc=ValidationError, title=None):
	raise exc(msg)


def _make_frappe():
	frappe = types.ModuleType("frappe")
	frappe._dict = _Dict
	frappe.PermissionError = PermissionError
	frappe.ValidationError = ValidationError
	frappe.DuplicateEntryError = DuplicateEntryError
	frappe.throw = _throw
	frappe.whitelist = lambda *a, **k: (lambda f: f)
	frappe.local = types.SimpleNamespace(request=None, site="test.site")
	frappe.session = types.SimpleNamespace(user="agent@example.com")
	frappe.form_dict = _Dict()
	frappe.flags = _Dict()
	frappe.db = MagicMock(name="frappe.db")
	frappe.log_error = MagicMock(name="log_error")
	frappe.enqueue = MagicMock(name="enqueue")
	frappe.publish_realtime = MagicMock(name="publish_realtime")
	frappe.get_roles = MagicMock(return_value=["Whatsnext User"])
	frappe.get_traceback = lambda: "traceback"
	def _module_getattr(name):
		# Real Frappe exposes frappe.request as a proxy to frappe.local.request.
		if name == "request":
			return frappe.local.request
		raise AttributeError(name)

	frappe.__getattr__ = _module_getattr
	frappe.get_request_header = lambda name: (frappe.local.request.headers or {}).get(name) if frappe.local.request else None

	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: dt.datetime(2026, 10, 24, 12, 0, 0)

	def add_to_date(date, days=0, hours=0, minutes=0, **_):
		return date + dt.timedelta(days=days, hours=hours, minutes=minutes)

	def get_datetime(value):
		if isinstance(value, dt.datetime):
			return value
		return dt.datetime.fromisoformat(str(value))

	def get_time(value):
		return value if isinstance(value, dt.time) else dt.time.fromisoformat(str(value))

	def getdate(value=None):
		if value is None:
			return dt.date(2026, 10, 24)
		if isinstance(value, dt.datetime):
			return value.date()
		if isinstance(value, dt.date):
			return value
		return dt.date.fromisoformat(str(value)[:10])

	utils.add_to_date = add_to_date
	utils.get_datetime = get_datetime
	utils.get_time = get_time
	utils.getdate = getdate
	utils.date_diff = lambda a, b: (getdate(a) - getdate(b)).days
	utils.get_fullname = lambda user: user
	utils.get_url = lambda path="": "https://test.site" + (path or "")
	frappe.utils = utils

	safe_exec = types.ModuleType("frappe.utils.safe_exec")
	safe_exec.safe_eval = lambda expr, ctx=None: eval(expr, {}, ctx or {})  # test stand-in only
	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = object

	sys.modules.update({
		"frappe": frappe,
		"frappe.utils": utils,
		"frappe.utils.safe_exec": safe_exec,
		"frappe.model": model,
		"frappe.model.document": document,
	})
	return frappe


FRAPPE = _make_frappe()


def make_settings(**overrides):
	"""A Whatsnext Settings stand-in with sensible defaults."""
	values = {
		"meta_enabled": 1,
		"twilio_enabled": 0,
		"meta_phone_number_id": "PNID",
		"meta_waba_id": "WABA",
		"meta_app_id": "APP",
		"meta_api_version": "v20.0",
		"default_provider": "Meta",
		"default_country_code": "91",
		"twilio_account_sid": "AC123",
		"twilio_whatsapp_number": "+14155238886",
		"twilio_verify_signature": 0,
		"campaign_send_interval": 1,
		"opt_out_enabled": 1,
		"away_enabled": 0,
		"business_days": "Mon,Tue,Wed,Thu,Fri,Sat",
		"business_hours_start": "09:00:00",
		"business_hours_end": "18:00:00",
		"holiday_list": None,
	}
	passwords = {
		"meta_access_token": "TOKEN",
		"twilio_auth_token": "TWILIO_TOKEN",
		"meta_app_secret": overrides.pop("meta_app_secret", None),
	}
	values.update(overrides)
	ns = types.SimpleNamespace(**values)
	ns.get = lambda key, default=None: getattr(ns, key, default)
	ns.get_password = lambda key, raise_exception=True: passwords.get(key)
	return ns


@pytest.fixture
def frappe():
	"""Fresh mocks per test; default settings available via get_cached_doc."""
	FRAPPE.db = MagicMock(name="frappe.db")
	FRAPPE.log_error = MagicMock(name="log_error")
	FRAPPE.enqueue = MagicMock(name="enqueue")
	FRAPPE.get_roles = MagicMock(return_value=["Whatsnext User"])
	FRAPPE.get_hooks = MagicMock(return_value=[])
	FRAPPE.local.request = None
	FRAPPE.form_dict = _Dict()
	FRAPPE.session.user = "agent@example.com"
	settings = make_settings()
	FRAPPE.get_cached_doc = MagicMock(return_value=settings)
	FRAPPE.settings = settings
	return FRAPPE
