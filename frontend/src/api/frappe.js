let csrfToken = null

// Frappe sets a plain, readable (non-HttpOnly) user_id cookie on every
// session alongside the HttpOnly sid cookie. window.frappeSession is only
// ever populated by the real Jinja-rendered whatsnext.html (see
// www/whatsnext.py) — Vite's own dev index.html never sets it — so this is
// the fallback that lets isLoggedIn()/getSessionUser() work correctly when
// running under `npm run dev` instead of always reporting logged-out and
// bouncing the router back to /login right after a successful login.
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

export function ensureCSRF() {
  if (window.csrf_token && window.csrf_token !== '{{ csrf_token }}') {
    csrfToken = window.csrf_token
    return Promise.resolve(csrfToken)
  }
  if (csrfToken) return Promise.resolve(csrfToken)

  return call('whatsnext.whatsnext.api.get_csrf_token', {}, 'GET').then((token) => {
    csrfToken = token
    return token
  })
}

export function isLoggedIn() {
  const sessionUser = window.frappeSession?.user
  if (sessionUser) return sessionUser !== 'Guest'
  const cookieUser = getCookie('user_id')
  return !!cookieUser && cookieUser !== 'Guest'
}

export function getSessionUser() {
  return window.frappeSession?.user || getCookie('user_id') || null
}

function buildUrl(method, params, httpMethod) {
  const url = `/api/method/${method}`
  if (httpMethod === 'GET' && params && Object.keys(params).length) {
    const qs = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : v])
    )
    return `${url}?${qs.toString()}`
  }
  return url
}

export async function call(method, params = {}, httpMethod = 'POST') {
  const isMutating = httpMethod !== 'GET'
  if (isMutating) await ensureCSRF()

  const headers = { Accept: 'application/json' }
  if (isMutating) {
    headers['Content-Type'] = 'application/json'
    headers['X-Frappe-CSRF-Token'] = csrfToken || window.csrf_token || ''
  }

  const res = await fetch(buildUrl(method, params, httpMethod), {
    method: httpMethod,
    credentials: 'include',
    headers,
    body: isMutating ? JSON.stringify(params) : undefined,
  })

  if (!res.ok) {
    let detail = ''
    try {
      const errJson = await res.json()
      detail = errJson.exception || errJson.message || JSON.stringify(errJson)
    } catch {
      detail = await res.text()
    }
    throw new Error(detail || `Request failed: ${res.status}`)
  }

  const data = await res.json()
  return data.message
}

export async function login(usr, pwd) {
  const res = await fetch('/api/method/login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ usr, pwd }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.message || 'Invalid login')
  }
  // Full navigation after login — reusing SPA in-memory state right after
  // login has proven unreliable; this also picks up the fresh csrf_token
  // server-rendered into the shell.
  window.location.href = '/whatsnext'
}

export async function logout() {
  try {
    await fetch('/api/method/logout', { credentials: 'include' })
  } catch {
    /* proceed to navigate regardless */
  }
  window.location.href = '/whatsnext/login'
}