import frappe
from frappe.model.document import Document


def publish_message_event(msg, event="whatsnext_message_update"):
	"""Send a realtime event to every user permitted to see this message's
	conversation. Published per user (their own socket room) rather than to
	the document's room: nobody is subscribed to a brand-new document's
	room, so doc-scoped events were never delivered to any open chat.
	`msg` can be a Document or a dict with the same keys."""
	from whatsnext.whatsnext.permissions import users_who_can_see

	get = msg.get
	payload = {
		"name": get("name"),
		"conversation_id": get("conversation_id"),
		"type": get("type"),
		"status": get("status"),
	}
	for user in users_who_can_see(get("customer")):
		frappe.publish_realtime(event=event, message=payload, user=user, after_commit=True)


class WhatsnextMessage(Document):
	def before_insert(self):
		if not self.conversation_id:
			# Always group by the counterpart's WhatsApp number, never by
			# reference_name. Grouping by reference_name used to mean any
			# message tied to a business document (a Sales Invoice reminder,
			# a CRM Lead alert, a Quotation follow-up...) fragmented into its
			# own separate "conversation" instead of joining the same real
			# contact's thread -- one customer could show up as half a dozen
			# different sidebar rows depending on which document last
			# messaged them. reference_doctype/reference_name are still
			# stored on every message for traceability; they just no longer
			# drive chat grouping.
			self.conversation_id = self.to_number or self.from_number

	def after_insert(self):
		# Delivered only to users permitted to see this conversation, never
		# broadcast site-wide (see publish_message_event).
		publish_message_event(self, event="whatsnext_new_message")

		# Push a real OS notification for inbound messages (outbound/sent
		# messages don't need one -- the sender already knows they sent it).
		# Enqueued as a background job, not called inline: it fans out to
		# every subscribed user's push service over HTTP, which can be slow
		# or flaky, and this fires from the inbound webhook handler where
		# that latency would otherwise delay the response Meta/Twilio expect.
		if self.type == "Incoming":
			frappe.enqueue(
				"whatsnext.whatsnext.push_engine.notify_new_message",
				queue="short",
				enqueue_after_commit=True,
				message_name=self.name,
				conversation_id=self.conversation_id,
				customer=self.customer,
				text=self.message,
				profile_name=self.profile_name,
				from_number=self.from_number,
			)
