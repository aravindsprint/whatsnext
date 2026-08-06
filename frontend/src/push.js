import { call } from '@/api/frappe'

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
  const reg = await navigator.serviceWorker.ready
  return reg.pushManager.getSubscription()
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

  const reg = await navigator.serviceWorker.ready
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
  await call('whatsnext.whatsnext.api.push.remove_push_subscription', {
    endpoint: subscription.endpoint,
  })
  await subscription.unsubscribe()
}
