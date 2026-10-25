import { io } from 'socket.io-client'

// Frappe's socketio server sits behind the same origin at /socket.io in
// standard bench/production setups (see frappe's nginx template + Procfile).
// The connection authenticates itself off the existing "sid" session cookie
// (withCredentials), so no manual login/room-join handshake is needed: the
// backend publishes each event to the personal room of every user allowed
// to see that conversation (see publish_message_event in
// whatsnext_message.py), which this socket joins automatically.
let socket = null

// Frappe v15+ serves realtime on a per-site namespace ("/<site name>") and
// rejects connections to the default "/" namespace, so on v15 the socket
// never authenticated and no live updates ever arrived. v14 only serves "/".
function namespace() {
  const session = window.frappeSession || {}
  const major = Number(session.frappeMajorVersion || 0)
  const site = session.site || window.location.hostname
  return major && major < 15 ? '/' : `/${site}`
}

export function getSocket() {
  if (socket) return socket
  socket = io(namespace(), {
    path: '/socket.io',
    withCredentials: true,
    transports: ['websocket', 'polling'],
  })
  return socket
}

export function onNewMessage(callback) {
  const s = getSocket()
  s.on('whatsnext_new_message', callback)
  return () => s.off('whatsnext_new_message', callback)
}

export function onMessageUpdate(callback) {
  const s = getSocket()
  s.on('whatsnext_message_update', callback)
  return () => s.off('whatsnext_message_update', callback)
}

export function onNote(callback) {
  const s = getSocket()
  s.on('whatsnext_note', callback)
  return () => s.off('whatsnext_note', callback)
}
