import { precacheAndRoute } from 'workbox-precaching'

// Injected at build time by vite-plugin-pwa (injectManifest strategy) with
// the hashed list of built assets to precache for offline use. URLs are
// rewritten to their real absolute location (see modifyURLPrefix in
// vite.config.js) since this script itself is served from /whatsnext/sw.js
// — a different directory than the assets it's precaching.
precacheAndRoute(self.__WB_MANIFEST)

// No offline navigation/app-shell fallback here on purpose: the page at
// /whatsnext is rendered server-side by a Jinja template (www/whatsnext.py)
// that injects a live CSRF token and session info. The static index.html
// vite itself builds alongside the assets is a different, incomplete file
// that was never actually served to anyone — precaching it and using it as
// an offline fallback would silently serve a broken shell instead of
// genuinely helping offline use. Precaching the real JS/CSS/icon assets
// above still lets an already-loaded page keep working offline; it just
// doesn't extend to a fresh cold-start navigation with no network.

self.skipWaiting()
self.addEventListener('activate', () => self.clients.claim())

// Real-time chat alerts: the backend sends a Web Push message (see
// whatsnext.whatsnext.push_engine.send_push_to_users) for every inbound
// WhatsApp message. This fires even when no tab is open, which is the
// whole point of push over the in-app socket.io listener in realtime.js —
// that one only works while a tab is already open and connected.
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: 'Whatsnext', body: event.data ? event.data.text() : 'New message' }
  }

  const title = data.title || 'Whatsnext'
  const options = {
    body: data.body || '',
    // Absolute path matching the real served location
    // (/assets/whatsnext/whatsnext_frontend/icons/...) — this file can't
    // use a relative path or vite's base-prefixing the way vite.config.js's
    // manifest icons do, since injectManifest only injects the precache
    // list into this file, not rewrite arbitrary string literals in it.
    icon: '/assets/whatsnext/whatsnext_frontend/icons/icon-192.png',
    badge: '/assets/whatsnext/whatsnext_frontend/icons/icon-192.png',
    tag: data.tag || 'whatsnext',
    renotify: true,
    data: { url: data.url || '/whatsnext' },
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

// Clicking the notification focuses an already-open Whatsnext tab (and
// routes it to the right conversation) instead of always opening a new one.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = event.notification.data?.url || '/whatsnext'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientsList) => {
      for (const client of clientsList) {
        if (client.url.includes('/whatsnext') && 'focus' in client) {
          if ('navigate' in client) client.navigate(targetUrl)
          return client.focus()
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl)
    })
  )
})
