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
