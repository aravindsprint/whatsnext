import frappe
from frappe.model.document import Document


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
		# Scoped to this document: Frappe only delivers to sessions permitted to
		# read this Whatsnext Message (via the has_permission/
		# permission_query_conditions hooks already registered for this
		# doctype), instead of broadcasting to every connected user on the site.
		frappe.publish_realtime(
			event="whatsnext_new_message",
			message={
				"name": self.name,
				"conversation_id": self.conversation_id,
				"type": self.type,
				"status": self.status,
			},
			doctype=self.doctype,
			docname=self.name,
			after_commit=True,
		)

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
