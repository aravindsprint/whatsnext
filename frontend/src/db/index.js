import Dexie from 'dexie'

export const db = new Dexie('whatsnext')

db.version(1).stores({
  conversations: 'conversation_id, modified',
  messages: 'name, conversation_id, creation',
})

export async function cacheConversations(list) {
  if (!list?.length) return
  await db.conversations.bulkPut(
    list.map((c) => ({ ...c, conversation_id: c.conversation_id || c.name }))
  )
}

export async function getCachedConversations() {
  return db.conversations.orderBy('modified').reverse().toArray()
}

export async function cacheMessages(conversationId, list) {
  if (!list?.length) return
  await db.messages.bulkPut(list)
}

export async function getCachedMessages(conversationId) {
  return db.messages.where('conversation_id').equals(conversationId).sortBy('creation')
}

// The cache is per browser, not per user. Clear it when someone logs out,
// and when a different user's session appears (e.g. the previous user's
// session expired instead of logging out), so one person never sees
// another's cached chats on a shared computer.
const OWNER_KEY = 'wn-cache-owner'

export async function clearCache() {
  try {
    await Promise.all([db.conversations.clear(), db.messages.clear()])
  } catch {
    /* IndexedDB unavailable (private mode) — nothing cached anyway */
  }
  try {
    localStorage.removeItem(OWNER_KEY)
  } catch {
    /* ignore */
  }
}

export async function ensureCacheOwner(user) {
  if (!user || user === 'Guest') return
  let owner = null
  try {
    owner = localStorage.getItem(OWNER_KEY)
  } catch {
    /* ignore */
  }
  if (owner && owner !== user) await clearCache()
  try {
    localStorage.setItem(OWNER_KEY, user)
  } catch {
    /* ignore */
  }
}
