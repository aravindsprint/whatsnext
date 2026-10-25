// Keeps every open Whatsnext tab on the latest deployed build, without
// anyone having to hard-refresh.
//
// How a stale build happened before:
//  - The service worker script was registered with the browser's default
//    updateViaCache ('imports'), and nothing ever called registration.update(),
//    so a tab left open (or an installed PWA) only noticed a new deploy when
//    the browser got round to its own periodic check, up to a day later.
//  - Even after the new worker took over, the page already running kept the
//    old JS in memory until someone reloaded it.
//  - Every build deletes the previous hashed chunks (emptyOutDir), so an old
//    tab that then opened another page asked for a file that no longer
//    existed, and the page failed to load.
//
// This module closes all three gaps.

const CHECK_EVERY_MS = 30 * 60 * 1000
const CHUNK_RELOAD_KEY = 'wn-chunk-reload-at'

let reloading = false

function reloadNow() {
  if (reloading) return
  reloading = true
  window.location.reload()
}

// A small bar at the bottom of the screen. Used when a new version takes over
// while the person is looking at the page, so a half-typed message is never
// thrown away by a surprise reload.
function showUpdateBar() {
  if (document.getElementById('wn-update-bar')) return
  const bar = document.createElement('div')
  bar.id = 'wn-update-bar'
  bar.setAttribute('role', 'status')
  bar.style.cssText = [
    'position:fixed', 'left:50%', 'bottom:16px', 'transform:translateX(-50%)',
    'z-index:10000', 'display:flex', 'align-items:center', 'gap:12px',
    'max-width:calc(100% - 32px)', 'padding:10px 14px', 'border-radius:10px',
    'background:#0F3D3E', 'color:#fff', 'font:500 13px/1.3 system-ui,sans-serif',
    'box-shadow:0 6px 20px rgba(0,0,0,.25)',
  ].join(';')
  const text = document.createElement('span')
  text.textContent = 'Whatsnext has been updated.'
  const button = document.createElement('button')
  button.type = 'button'
  button.textContent = 'Reload'
  button.style.cssText = 'border:0;border-radius:7px;padding:6px 12px;background:#2bb3a3;color:#fff;font:600 13px system-ui,sans-serif;cursor:pointer'
  button.addEventListener('click', reloadNow)
  bar.append(text, button)
  document.body.appendChild(bar)
}

// Called once a new service worker controls this page: the JS in memory is
// now older than what the server serves.
function onNewVersion() {
  if (document.visibilityState === 'hidden') {
    reloadNow()
    return
  }
  showUpdateBar()
  // If they switch away without clicking, reload quietly so the tab is fresh
  // when they come back.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') reloadNow()
  })
}

export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return

  const swUrl = import.meta.env.PROD ? '/whatsnext/sw.js' : '/sw.js'
  const scope = import.meta.env.PROD ? '/whatsnext/' : '/'

  // A page with no controller yet is a first install, not an update: the
  // worker taking control then must not trigger a reload.
  const hadController = !!navigator.serviceWorker.controller
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) onNewVersion()
  })

  navigator.serviceWorker
    // 'none': always fetch sw.js (and anything it imports) from the network
    // when checking for updates, never from the HTTP cache.
    .register(swUrl, { scope, updateViaCache: 'none' })
    .then((registration) => {
      const check = () => registration.update().catch(() => { /* offline: try next time */ })
      check()
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') check()
      })
      window.addEventListener('online', check)
      setInterval(check, CHECK_EVERY_MS)
    })
    .catch((err) => {
      console.error('Service worker registration failed:', err)
    })
}

function isMissingChunkError(err) {
  const message = String(err?.message || err || '')
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(message)
}

// An old tab asked for a page chunk the last deploy deleted. Reload once to
// pick up the current build. The timestamp guard stops a reload loop if the
// file is genuinely missing on the server.
export function recoverFromMissingChunks(router) {
  const tryReload = (err, targetPath) => {
    if (!isMissingChunkError(err)) return false
    let last = 0
    try {
      last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0)
    } catch { /* storage unavailable */ }
    if (Date.now() - last < 10000) return false
    try {
      sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()))
    } catch { /* storage unavailable */ }
    if (targetPath) window.location.assign(targetPath)
    else reloadNow()
    return true
  }

  router.onError((err, to) => {
    tryReload(err, to?.fullPath)
  })
  // Vite fires this when a lazy page's JS or CSS fails to preload.
  window.addEventListener('vite:preloadError', (event) => {
    if (tryReload(event.payload || event)) event.preventDefault()
  })
}
