import { io } from 'socket.io-client'

// Frappe's socketio server sits behind the same origin at /socket.io in
// standard bench/production setups (see frappe's nginx template + Procfile).
// The connection authenticates itself off the existing "sid" session cookie
// (withCredentials), so no manual login/room-join handshake is needed here —
// the server already knows which user this socket belongs to and only
// forwards events that user is permitted to see (this doctype already has
// has_permission/permission_query_conditions hooks registered, and
// WhatsnextMessage.after_insert calls publish_realtime scoped to the doc).
let socket = null

export function getSocket() {
  if (socket) return socket
  socket = io('/', {
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
