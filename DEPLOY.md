# Deploy checklist

```bash
cd frontend
rm -rf node_modules/.vite      # Vite's build cache can go stale and silently skip real changes
yarn install
yarn build

cd ..
mkdir -p whatsnext/public/whatsnext_frontend
cp -r frontend/dist/* whatsnext/public/whatsnext_frontend/

cd ..                                # back to bench root
bench build --app whatsnext          # rebuilds Desk assets + relinks public/ — does NOT touch the SPA source
bench --site <site> migrate          # required after any doctype/field/fixture change
bench --site <site> clear-cache
bench restart
```

`www/whatsnext.py` reads `whatsnext/public/whatsnext_frontend/.vite/manifest.json`
(emitted because `vite.config.js` sets `build.manifest: true`) to find the
current hashed JS/CSS filenames at request time. You never need to hand-edit
a filename into `whatsnext.html` — that was the earlier fragile approach and
it's why the build failed before; this manifest lookup fixes it for good. If
you visit `/whatsnext` and see "frontend not built yet", it means the copy
step above didn't run or landed in the wrong folder.

## Push notifications

Real-time chat alerts (OS-level notifications even when the tab/app is
closed) need one extra Python dependency, since it isn't part of a stock
bench environment:

```bash
bench pip install pywebpush
```

Then, as a System Manager, open Whatsnext → Settings → General and:
1. Check **Enable push notifications site-wide**.
2. Set a **VAPID Subject** — a `mailto:you@example.com` (or `https://` URL)
   push services can use to contact you if there's ever a problem with your
   traffic. Required by the Web Push spec.
3. Save. A VAPID keypair is generated automatically on first use and stored
   on Whatsnext Settings — nothing else to configure.

Each user then turns notifications on for their own device from the
**Notifications** card at the top of the same Settings page (this works for
every logged-in user, not just System Managers). The browser will prompt
for notification permission; once granted, the subscription is registered
against that user and that device.

Notes:
- HTTPS is required — the Push API refuses to work over plain HTTP except
  on `localhost`.
- On iOS, Safari only supports web push for a PWA that's been **added to
  the Home Screen** (Safari 16.4+); it won't work in a regular browser tab.
- Only *incoming* WhatsApp messages trigger a push — outgoing ones don't,
  since the sender already knows they sent it.

After deploying any frontend change, **test in an Incognito/Private tab first**.
This app is a PWA with a service worker; a browser that already has it
installed will keep serving the old cached bundle even after a fully
successful rebuild. If Incognito shows the fix but a regular tab doesn't,
that confirms it's the service worker, not a deploy failure — clear it via
DevTools → Application → Service Workers → Unregister, then Storage → Clear
site data, then hard refresh.
