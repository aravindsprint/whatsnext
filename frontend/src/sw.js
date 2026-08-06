import { precacheAndRoute, createHandlerBoundToURL } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'

// Injected at build time by vite-plugin-pwa (injectManifest strategy) with
// the hashed list of built assets to precache for offline use.
precacheAndRoute(self.__WB_MANIFEST)

// Offline/SPA-navigation fallback: serve the cached app shell for any
// navigation that isn't one of these paths, mirroring the denylist the
// previous generateSW config used (the server already resolves all of
// these routes itself when online — this only matters offline).
const denylist = [/^\/api/, /^\/files/, /^\/app/, /^\/whatsnext\/settings/, /^\/whatsnext\/templates/]
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), { denylist }))

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
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
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
