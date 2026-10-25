# Whatsnext

A standalone WhatsApp Business messaging hub for ERPNext — built as a decoupled
Vue 3 SPA + Frappe app, integrating **both Meta's WhatsApp Cloud API and
Twilio** without depending on any third-party WhatsApp integration app.

### Why Whatsnext

Most WhatsApp-for-ERPNext tools stop at "send a templated message when X happens." Whatsnext starts there — but the core of the app is a genuine conversation view: incoming replies, outgoing messages, media, and history, all threaded per customer, with an offline-capable chat list that works like a proper messaging app, not a report screen.

## Features

**Chat**
- **Two-way chat, not just outbound sends** — inbox, threads, media, read/delivered ticks, live updates
- Chats linked to the ERPNext **Contact** and **Customer** automatically by phone number
- **Assign** chats to team members, **close/reopen** them, filter by *Mine* / *Unread* / *Closed*
- **24-hour window awareness** — the composer switches to templates-only (with a clear banner) when WhatsApp no longer allows free-form replies
- **Schedule** a message or template for later; scheduled items can be cancelled from the chat
- Pick **Meta or Twilio per message** (when both are enabled), or use the default
- Incoming text, images, video, audio, documents, stickers, locations, shared contacts, reactions and **template quick-reply button taps**
- **Reply to a specific message** (quoted on the customer's phone with Meta), and see which message a customer replied to
- **Share a location** (current position, a pasted Maps link or coordinates) or a **contact card** from ERPNext Contacts
- **Internal notes** on a chat — visible to the team only, never sent to the customer
- **Save an unknown number** as an ERPNext Contact (optionally linked to a Customer) or create a **Lead**, right from the chat
- **Quick replies** — shared saved answers, inserted with ⚡ or by typing `/shortcut`; `{name}` fills the customer's first name
- **Read receipts** — customers see blue ticks when an agent opens the chat (Meta)
- **Away message** — automatic reply outside business hours / on holidays, at most once per cooldown
- Load earlier messages, Media & Files panel, offline-friendly chat list (IndexedDB), installable PWA, push notifications

**Templates**
- `{{1}}`, `{{2}}` body variables, text-header variables, dynamic URL-button suffixes, media headers
- Create a template in the app and **submit it to Meta for review**; approval/rejection updates arrive by webhook (plus a nightly refresh)
- Sync existing templates from Meta

**Campaigns**
- Bulk template sends from CSV or saved recipient lists, paced to respect rate limits
- **Schedule**, **pause/resume**, **cancel**, **retry failed**; delivered counts follow delivery receipts
- Adjustable send rate (Settings → Campaign Send Interval)
- Excel/PDF result export

**Automation**
- **Whatsnext Notification**: send a template when a document is created, submitted, updated or changed — instant for common doctypes (Sales Invoice, Sales Order, Delivery Note, Quotation, Payment Entry, Purchase Order/Invoice, Lead, Opportunity, Customer, Supplier, Issue, Employee…), every 5 minutes for any other doctype. Manage them in the app under **Notifications**.
- Attach the document's print as a PDF header
- **WhatsApp button on ERPNext forms** (Customer, Contact, Lead, Sales Invoice, Sales Order, Quotation, Delivery Note, Payment Entry…) to send a template — optionally with the document PDF — and jump to the chat

**Reports**
- Agent report: messages sent, chats handled, average/median first-response time, open chats assigned; automated sends excluded

**Compliance & security**
- **Opt-out handling**: replies like STOP/UNSUBSCRIBE opt the number out of Marketing templates and campaigns (START opts back in), with configurable keywords and confirmations
- Meta webhook **signature verification** (App Secret) and optional Twilio signature verification
- Per-Sales-Person visibility: users only see chats, dashboard figures and pushes for their own customers (System Managers see everything)

## Architecture

Classic Frappe app (`whatsnext/`) + fully decoupled Vue 3 SPA (`frontend/`),
served at `/whatsnext`. See the accompanying build spec this app follows for
folder conventions, auth/CSRF pattern, and deploy checklist.

## Configure

1. Open **Whatsnext Settings** (Desk, or `/whatsnext/settings` in the app — System Managers).
2. Enable Meta and/or Twilio and fill in the credentials. For Meta, also set the **App ID** (needed to submit media-header templates) and the **App Secret** (verifies webhooks).
3. Meta webhook URL (Meta App Dashboard → WhatsApp → Configuration), subscribed to `messages` and `message_template_status_update`:
   `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.meta_webhook`
4. Twilio webhook URLs (Twilio Console → WhatsApp Sender):
   - Inbound: `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.twilio_webhook`
   - Status callback: `https://<your-site>/api/method/whatsnext.whatsnext.api.webhook.twilio_status_callback`
   - Once these work, turn on **Verify Twilio Webhook Signatures**.
5. Give agents the **Whatsnext User** role — every Whatsnext API call requires it (or System Manager), so portal/website users can't reach the WhatsApp features. To scope what they see, link their Employee to a Sales Person and add that Sales Person to customers' Sales Team.
6. Review the **Opt-out** keywords and confirmation messages.

After updating the app run `bench --site <site> migrate` and restart workers.

## Frontend dev

```bash
cd frontend
yarn install
yarn dev   # proxies /api to http://localhost:8000 by default
```

See `DEPLOY.md` for the production build/deploy checklist.

## Tests

- **Unit tests** (no bench needed; run in CI on every PR):
  `pip install -r tests/requirements.txt && python -m pytest`
- **Frontend tests**: `cd frontend && npm test`
- **Integration tests** on a test site (provider calls are mocked; they change Whatsnext Settings, so never run them on production):
  `bench --site <test-site> run-tests --app whatsnext`
