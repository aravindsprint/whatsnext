# Whatsnext

A standalone WhatsApp Business messaging hub for ERPNext — built as a decoupled
Vue 3 SPA + Frappe app, integrating **both Meta's WhatsApp Cloud API and
Twilio** without depending on any third-party WhatsApp integration app.

### Why Whatsnext

Most WhatsApp-for-ERPNext tools stop at "send a templated message when X happens." Whatsnext starts there — but the core of the app is a genuine conversation view: incoming replies, outgoing messages, media, and history, all threaded per customer, with an offline-capable chat list that works like a proper messaging app, not a report screen.

## Features

- **Two-way chat, not just outbound sends** — a real conversation UI (inbox, threads, media, read/delivered status) synced to ERPNext documents (Customers, Contacts, Leads, etc.), not a one-way notification log
- Meta WhatsApp Cloud API and Twilio support, selectable per-message or system-wide
- Reusable message templates with `{{1}}`, `{{2}}` variable substitution
- Event-driven notifications — fire a WhatsApp message automatically on
  Sales Order, Sales Invoice, Delivery Note, Quotation, Payment Entry,
  Purchase Order, Purchase Invoice, Lead, Opportunity, Customer, or Supplier
  Submit / Update / Change via the **WhatsApp Notification** doctype
- Scheduled sends, with a safety-net job that recovers stuck messages
- Dashboard: message queue, delivery status donut, weekly trend, top templates,
  recent activity
- Offline-friendly conversation list (Dexie/IndexedDB cache) and installable PWA

## Architecture

Classic Frappe app (`whatsnext/`) + fully decoupled Vue 3 SPA (`frontend/`),
served at `/whatsnext`. See the accompanying build spec this app follows for
folder conventions, auth/CSRF pattern, and deploy checklist.

## Configure

1. Go to **WhatsApp Settings** (Desk, System Manager only, or `/whatsnext/settings` in the SPA).
2. Enable Meta and/or Twilio, fill in credentials.
3. Meta webhook URL (set in Meta App dashboard → WhatsApp → Configuration):
   `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.meta_webhook`
4. Twilio webhook URLs (set in Twilio Console → WhatsApp Sender):
   - Inbound: `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.twilio_webhook`
   - Status callback: `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.twilio_status_callback`

## Frontend dev

```bash
cd frontend
yarn install
yarn dev   # proxies /api to http://localhost:8000 by default
```

See `DEPLOY.md` for the production build/deploy checklist.
