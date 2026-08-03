# Privacy — Whatsnext

Whatsnext stores WhatsApp message content, phone numbers, and provider
credentials (Meta access token, Twilio auth token) within your own ERPNext
site's database. No data is sent to any third party other than the WhatsApp
provider(s) you explicitly configure (Meta WhatsApp Cloud API and/or Twilio).
Access tokens are stored using Frappe's Password fieldtype (encrypted at
rest). Site administrators are responsible for their own data retention and
regional privacy compliance (e.g. GDPR) obligations for message content.
