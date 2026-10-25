// Turns a Frappe error response into the message a person should read.
//
// Frappe puts the user-facing text in `_server_messages` (for frappe.throw /
// msgprint) and the raw "module.path.ClassName: text" in `exception`.
// Showing `exception` as-is leaked internal names like
// "frappe.exceptions.ValidationError: ..." into the chat UI.

const CLASS_PREFIX = /^[A-Za-z_]\w*(\.\w+)+:\s*/

function stripHtml(text) {
  return String(text).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim()
}

export function errorMessage(errJson, status) {
  if (errJson && typeof errJson === 'object') {
    try {
      const messages = JSON.parse(errJson._server_messages || '[]')
      for (let i = messages.length - 1; i >= 0; i--) {
        const parsed = typeof messages[i] === 'string' ? JSON.parse(messages[i]) : messages[i]
        const text = stripHtml(parsed?.message || '')
        if (text) return text
      }
    } catch {
      // fall through to the other fields
    }
    if (errJson.exception) return String(errJson.exception).replace(CLASS_PREFIX, '').trim()
    if (typeof errJson.message === 'string' && errJson.message) return errJson.message
  }
  return status ? `Request failed (${status})` : 'Request failed'
}
