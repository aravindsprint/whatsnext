"""End-to-end checks against a real site:

	bench --site <test-site> run-tests --app whatsnext

Provider HTTP calls are mocked, so nothing is sent to Meta or Twilio. Use a
test site — these tests change Whatsnext Settings.
"""

import json
from unittest.mock import MagicMock, patch

import frappe
try:
	# Frappe v16+: FrappeTestCase is a deprecated compatibility alias.
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v14/v15
	from frappe.tests.utils import FrappeTestCase

from whatsnext.whatsnext.api import send_message, send_template_message
from whatsnext.whatsnext.api.webhook import _apply_status_update, _save_incoming_meta_message

TEST_PREFIX = "9199999"  # every test number starts with this, for cleanup


def _number(suffix):
	return f"{TEST_PREFIX}{suffix:05d}"


def _meta_ok(message_id="wamid.TEST"):
	resp = MagicMock(status_code=200, text="{}")
	resp.json.return_value = {"messages": [{"id": message_id}]}
	return resp


class TestMessaging(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_single("Whatsnext Settings")
		settings.default_provider = "Meta"
		settings.meta_enabled = 1
		settings.meta_phone_number_id = "TESTPNID"
		settings.meta_waba_id = "TESTWABA"
		settings.meta_access_token = "test-token"
		settings.twilio_enabled = 0
		settings.opt_out_enabled = 1
		settings.away_enabled = 0
		settings.send_read_receipts = 0
		settings.notify_on_failure = 0
		settings.save(ignore_permissions=True)

		if not frappe.db.exists("Whatsnext Message Template", "wn_test_promo"):
			frappe.get_doc({
				"doctype": "Whatsnext Message Template",
				"template_name": "wn_test_promo",
				"provider": "Meta",
				"language": "en",
				"category": "Marketing",
				"body": "Hi {{1}}, our sale is on!",
			}).insert(ignore_permissions=True)
		frappe.db.set_value("Whatsnext Message Template", "wn_test_promo", "approval_status", "Approved")
		frappe.db.commit()

	def setUp(self):
		self.post = patch("whatsnext.whatsnext.provider_engine.requests.post", return_value=_meta_ok()).start()
		patch("frappe.enqueue").start()
		self.addCleanup(patch.stopall)

	def tearDown(self):
		like = f"{TEST_PREFIX}%"
		for name in frappe.get_all("Whatsnext Message", filters={"conversation_id": ["like", like]}, pluck="name"):
			frappe.delete_doc("Whatsnext Message", name, force=True, ignore_permissions=True)
		for dt in ("Whatsnext Conversation", "Whatsnext Opt Out"):
			for name in frappe.get_all(dt, filters={"name": ["like", like]}, pluck="name"):
				frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _incoming(self, number, text, msg_id):
		_save_incoming_meta_message(
			{"from": number, "id": msg_id, "type": "text", "text": {"body": text}},
			{"contacts": [{"wa_id": number, "profile": {"name": "Test Customer"}}], "metadata": {"display_phone_number": "910000000000"}},
		)

	def test_incoming_creates_message_and_conversation(self):
		number = _number(1)
		self._incoming(number, "Hello", "wamid.in1")
		msg = frappe.get_last_doc("Whatsnext Message", filters={"conversation_id": number})
		self.assertEqual(msg.type, "Incoming")
		self.assertEqual(msg.message, "Hello")
		conv = frappe.get_doc("Whatsnext Conversation", number)
		self.assertEqual(conv.status, "Open")
		self.assertEqual(conv.profile_name, "Test Customer")
		self.assertTrue(conv.last_incoming_at)

	def test_duplicate_webhook_is_ignored(self):
		number = _number(2)
		self._incoming(number, "Hello", "wamid.dup")
		self._incoming(number, "Hello", "wamid.dup")
		self.assertEqual(frappe.db.count("Whatsnext Message", {"conversation_id": number}), 1)

	def test_free_text_needs_open_window(self):
		number = _number(3)
		with self.assertRaises(frappe.ValidationError):
			send_message(to=number, message="Hi there")
		self.post.assert_not_called()

		self._incoming(number, "Hi", "wamid.in3")
		result = send_message(to=number, message="Hi there")
		self.assertEqual(result["status"], "Sent")
		self.assertEqual(result["provider_message_id"], "wamid.TEST")
		payload = json.loads(self.post.call_args.kwargs["data"])
		self.assertEqual(payload["text"]["body"], "Hi there")

	def test_reply_sends_context(self):
		number = _number(4)
		self._incoming(number, "Where is my order?", "wamid.q1")
		quoted = frappe.db.get_value("Whatsnext Message", {"provider_message_id": "wamid.q1"})
		send_message(to=number, message="On its way", reply_to=quoted)
		payload = json.loads(self.post.call_args.kwargs["data"])
		self.assertEqual(payload["context"], {"message_id": "wamid.q1"})

	def test_stop_keyword_opts_out_and_blocks_marketing(self):
		number = _number(5)
		self._incoming(number, "STOP", "wamid.stop")
		self.assertEqual(frappe.db.get_value("Whatsnext Opt Out", number, "opted_out"), 1)
		# a confirmation reply was sent
		self.assertTrue(self.post.called)
		with self.assertRaises(frappe.ValidationError):
			send_template_message(to=number, template="wn_test_promo", parameters={"1": "Ravi"})

		self._incoming(number, "START", "wamid.start")
		self.assertEqual(frappe.db.get_value("Whatsnext Opt Out", number, "opted_out"), 0)
		result = send_template_message(to=number, template="wn_test_promo", parameters={"1": "Ravi"})
		self.assertEqual(result["status"], "Sent")
		self.assertEqual(result["message"], "Hi Ravi, our sale is on!")

	def test_template_outside_window_is_allowed(self):
		result = send_template_message(to=_number(6), template="wn_test_promo", parameters={"1": "Ravi"})
		self.assertEqual(result["status"], "Sent")

	def test_status_never_moves_backwards(self):
		number = _number(7)
		self._incoming(number, "Hi", "wamid.in7")
		self.post.return_value = _meta_ok("wamid.out7")
		send_message(to=number, message="Hello")
		_apply_status_update("wamid.out7", "Read")
		_apply_status_update("wamid.out7", "Delivered")
		self.assertEqual(frappe.db.get_value("Whatsnext Message", {"provider_message_id": "wamid.out7"}, "status"), "Read")

	def test_scheduled_message_waits(self):
		number = _number(8)
		self._incoming(number, "Hi", "wamid.in8")
		later = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=2)
		result = send_message(to=number, message="Later", scheduled_time=str(later))
		self.assertEqual(result["status"], "Pending")
		self.post.assert_not_called()

	def test_provider_failure_is_recorded(self):
		number = _number(9)
		self._incoming(number, "Hi", "wamid.in9")
		bad = MagicMock(status_code=400, text="{}")
		bad.json.return_value = {"error": {"message": "Recipient not on WhatsApp"}}
		self.post.return_value = bad
		result = send_message(to=number, message="Hello")
		status, error = frappe.db.get_value("Whatsnext Message", result["name"], ["status", "error_message"])
		self.assertEqual(status, "Failed")
		self.assertIn("Recipient not on WhatsApp", error)


	def test_notes_are_internal(self):
		from whatsnext.whatsnext.api import add_note, get_notes

		number = _number(10)
		self._incoming(number, "Hi", "wamid.in10")
		self.post.reset_mock()
		add_note(conversation_id=number, note="Called him, sending quote tomorrow")
		self.assertEqual([n.note for n in get_notes(conversation_id=number)], ["Called him, sending quote tomorrow"])
		self.post.assert_not_called()  # nothing went to WhatsApp
		for n in frappe.get_all("Whatsnext Conversation Note", filters={"conversation_id": number}, pluck="name"):
			frappe.delete_doc("Whatsnext Conversation Note", n, force=True, ignore_permissions=True)

	def test_save_number_as_contact_links_chat(self):
		from whatsnext.whatsnext.api import save_number_as_contact

		number = _number(11)
		self._incoming(number, "Hi, I need a quote", "wamid.in11")
		info = save_number_as_contact(conversation_id=number, first_name="WN Test", last_name="Buyer")
		self.addCleanup(frappe.delete_doc, "Contact", info["contact"], force=True, ignore_permissions=True)
		self.assertTrue(info["contact"])
		self.assertEqual(frappe.db.get_value("Whatsnext Message", {"conversation_id": number}, "contact"), info["contact"])
		with self.assertRaises(frappe.ValidationError):
			save_number_as_contact(conversation_id=number, first_name="Again")


	def test_chat_list_reads_conversation_summary(self):
		from whatsnext.whatsnext.api import get_conversation_stats, get_conversations, mark_as_read

		a, b = _number(12), _number(13)
		self._incoming(a, "First chat", "wamid.l1")
		self._incoming(b, "Second chat", "wamid.l2")
		self._incoming(b, "Still there?", "wamid.l3")

		page = get_conversations(limit=200, search=TEST_PREFIX)
		ids = [r.conversation_id for r in page["data"]]
		self.assertLess(ids.index(b), ids.index(a))  # newest activity first
		row_b = next(r for r in page["data"] if r.conversation_id == b)
		self.assertEqual(row_b.message, "Still there?")
		self.assertTrue(row_b.is_unread)
		self.assertEqual(frappe.db.get_value("Whatsnext Conversation", b, "unread_count"), 2)

		mark_as_read(conversation_id=b)
		self.assertEqual(frappe.db.get_value("Whatsnext Conversation", b, "unread_count"), 0)
		unread_ids = [r.conversation_id for r in get_conversations(limit=200, filter="unread", search=TEST_PREFIX)["data"]]
		self.assertIn(a, unread_ids)
		self.assertNotIn(b, unread_ids)

		before = get_conversation_stats()["sent"]
		send_message(to=b, message="Yes, here")
		self.assertEqual(get_conversation_stats()["sent"], before + 1)
		self.assertEqual(get_conversations(limit=1, search=b)["data"][0].type, "Outgoing")

	def test_chat_list_paging(self):
		from whatsnext.whatsnext.api import get_conversations

		for i in range(3):
			self._incoming(_number(30 + i), f"Hi {i}", f"wamid.p{i}")
		first = get_conversations(limit=2, offset=0, search=TEST_PREFIX + "000")
		second = get_conversations(limit=2, offset=2, search=TEST_PREFIX + "000")
		self.assertEqual(len(first["data"]), 2)
		self.assertTrue(first["has_more"])
		self.assertFalse(second["has_more"])
		self.assertFalse({r.conversation_id for r in first["data"]} & {r.conversation_id for r in second["data"]})

	def test_failed_send_not_counted_as_sent(self):
		from whatsnext.whatsnext.api import get_conversation_stats

		number = _number(14)
		self._incoming(number, "Hi", "wamid.in14")
		before = get_conversation_stats()["sent"]
		bad = MagicMock(status_code=400, text="{}")
		bad.json.return_value = {"error": {"message": "Recipient not on WhatsApp"}}
		self.post.return_value = bad
		send_message(to=number, message="Hello")
		self.assertEqual(get_conversation_stats()["sent"], before)


class TestCampaign(FrappeTestCase):
	def setUp(self):
		patch("whatsnext.whatsnext.provider_engine.requests.post", return_value=_meta_ok()).start()
		patch("whatsnext.whatsnext.campaign_engine.time.sleep").start()
		patch("frappe.enqueue").start()
		self.addCleanup(patch.stopall)
		TestMessaging.setUpClass()

	def tearDown(self):
		frappe.delete_doc("Whatsnext Campaign", "wn_test_campaign", force=True, ignore_permissions=True) if frappe.db.exists("Whatsnext Campaign", "wn_test_campaign") else None
		TestMessaging.tearDown(self)

	def test_campaign_skips_opted_out_numbers(self):
		from whatsnext.whatsnext.api import create_campaign
		from whatsnext.whatsnext.campaign_engine import run_campaign
		from whatsnext.whatsnext.conversations import set_opt_out

		opted_out, subscribed = _number(20), _number(21)
		set_opt_out(opted_out, True)
		create_campaign(
			campaign_name="wn_test_campaign", template="wn_test_promo",
			recipients=[{"to_number": opted_out, "parameters": {"1": "A"}}, {"to_number": subscribed, "parameters": {"1": "B"}}],
		)
		frappe.db.set_value("Whatsnext Campaign", "wn_test_campaign", "status", "Queued")
		run_campaign("wn_test_campaign")

		statuses = dict(frappe.get_all(
			"Whatsnext Campaign Recipient", filters={"parent": "wn_test_campaign"}, fields=["to_number", "status"], as_list=True,
		))
		self.assertEqual(statuses[opted_out], "Skipped")
		self.assertEqual(statuses[subscribed], "Sent")
		campaign = frappe.get_doc("Whatsnext Campaign", "wn_test_campaign")
		self.assertEqual(campaign.status, "Completed")
		self.assertEqual(campaign.skipped_count, 1)
		self.assertEqual(campaign.sent_count, 1)
