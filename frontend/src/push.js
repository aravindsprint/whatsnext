import { call } from '@/api/frappe'
import { getActiveRegistration } from '@/lib/appUpdate'

// The Push API wants the VAPID public key as a Uint8Array, but the server
// hands it over as a URL-safe base64 string — this is the standard
// conversion (see MDN's push notification guides) between the two.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)))
}

export function pushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// 'granted' | 'denied' | 'default' | 'unsupported'
export function pushPermission() {
  return pushSupported() ? Notification.permission : 'unsupported'
}

export async function getExistingSubscription() {
  if (!pushSupported()) return null
  // Short timeout: this also runs on logout, which must never hang.
  const reg = await getActiveRegistration(3000).catch(() => null)
  return reg ? reg.pushManager.getSubscription() : null
}

// Requests notification permission, creates (or reuses) a push
// subscription, and registers it with the backend against the current
// user. Throws with a user-facing message on any failure so callers can
// surface it directly.
export async function enablePush() {
  if (!pushSupported()) {
    throw new Error('This browser does not support push notifications.')
  }

  const publicKey = await call('whatsnext.whatsnext.api.push.get_vapid_public_key', {}, 'GET')
  if (!publicKey) {
    throw new Error('Push notifications are not enabled for this site yet.')
  }

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error('Notification permission was not granted.')
  }

  // Not navigator.serviceWorker.ready: that only resolves for a page inside
  // the worker's scope (/whatsnext/), and a tab first opened at /whatsnext
  // (no trailing slash) stays outside it even after clicking through to
  // /whatsnext/settings, so enabling push waited forever on "Turning on…".
  // A push subscription only needs the registration itself, controlled
  // page or not.
  const reg = await getActiveRegistration(15000)
  let subscription = await reg.pushManager.getSubscription()
  if (!subscription) {
    subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    })
  }

  await call('whatsnext.whatsnext.api.push.save_push_subscription', {
    subscription: subscription.toJSON(),
  })

  return subscription
}

export async function disablePush() {
  const subscription = await getExistingSubscription()
  if (!subscription) return
  try {
    await call('whatsnext.whatsnext.api.push.remove_push_subscription', {
      endpoint: subscription.endpoint,
    })
  } finally {
    // Unsubscribe locally even if the server call fails (e.g. session
    // already expired) so the browser stops receiving pushes either way.
    await subscription.unsubscribe()
  }
}
