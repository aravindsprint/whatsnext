import { defineStore } from 'pinia'
import { call } from '@/api/frappe'
import { cacheConversations, getCachedConversations, cacheMessages, getCachedMessages } from '@/db'
import { onNewMessage, onMessageUpdate } from '@/realtime'

const API = 'whatsnext.whatsnext.api'
const PAGE_SIZE = 50

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: [],
    activeConversationId: null,
    messagesByConversation: {},
    // conversation_id -> true while older pages may still exist
    hasOlderByConversation: {},
    infoByConversation: {},
    loadingConversations: false,
    loadingMessages: false,
    loadingOlder: false,
    search: '',
    filter: 'all',
    stats: { total: 0, unread: 0, sent: 0 },
    // Provider chosen in the composer ('' = default from Settings)
    provider: '',
  }),
  getters: {
    activeMessages: (state) => state.messagesByConversation[state.activeConversationId] || [],
    activeInfo: (state) => state.infoByConversation[state.activeConversationId] || null,
    activeHasOlder: (state) => !!state.hasOlderByConversation[state.activeConversationId],
  },
  actions: {
    async loadConversations() {
      this.loadingConversations = true
      // Each search keystroke / realtime event starts a new request; only
      // the newest may write, otherwise a slow earlier response (e.g. the
      // unfiltered list) could overwrite the results for the current search.
      const requestId = (this._conversationsRequestId = (this._conversationsRequestId || 0) + 1)
      // Show cached data immediately (first load only — the cache is
      // unfiltered, so showing it mid-search flashed the wrong list).
      if (!this.conversations.length && !this.search && this.filter === 'all') {
        this.conversations = await getCachedConversations()
      }
      try {
        const res = await call(`${API}.get_conversations`, {
          limit: 100,
          offset: 0,
          search: this.search || undefined,
          filter: this.filter === 'all' ? undefined : this.filter,
        }, 'GET')
        if (requestId !== this._conversationsRequestId) return
        this.conversations = res.data
        if (!this.search && this.filter === 'all') cacheConversations(res.data)
      } finally {
        if (requestId === this._conversationsRequestId) this.loadingConversations = false
      }
    },
    async loadStats() {
      this.stats = await call(`${API}.get_conversation_stats`, {}, 'GET')
    },
    setSearch(value) {
      this.search = value
      this.loadConversations()
    },
    setFilter(value) {
      this.filter = value
      this.loadConversations()
    },
    async openConversation(conversationId) {
      this.activeConversationId = conversationId
      this.loadingMessages = true
      this.messagesByConversation[conversationId] = await getCachedMessages(conversationId)
      this.loadInfo(conversationId)
      try {
        await this.refreshMessages(conversationId)
        await call(`${API}.mark_as_read`, { conversation_id: conversationId })
      } finally {
        this.loadingMessages = false
      }
    },
    // Latest page only; keeps already-loaded older pages in place.
    async refreshMessages(conversationId) {
      const latest = await call(`${API}.get_messages`, { conversation_id: conversationId, limit: PAGE_SIZE }, 'GET')
      const existing = this.messagesByConversation[conversationId] || []
      const latestNames = new Set(latest.map((m) => m.name))
      const oldestLatest = latest[0]?.creation
      const older = oldestLatest ? existing.filter((m) => !latestNames.has(m.name) && m.creation < oldestLatest) : []
      this.messagesByConversation[conversationId] = [...older, ...latest]
      if (!(conversationId in this.hasOlderByConversation)) {
        this.hasOlderByConversation[conversationId] = latest.length === PAGE_SIZE
      }
      cacheMessages(conversationId, latest)
    },
    async loadOlder() {
      const id = this.activeConversationId
      if (!id || this.loadingOlder || !this.hasOlderByConversation[id]) return
      this.loadingOlder = true
      try {
        const existing = this.messagesByConversation[id] || []
        const older = await call(`${API}.get_messages`, {
          conversation_id: id, limit: PAGE_SIZE, offset: existing.length,
        }, 'GET')
        const names = new Set(existing.map((m) => m.name))
        this.messagesByConversation[id] = [...older.filter((m) => !names.has(m.name)), ...existing]
        this.hasOlderByConversation[id] = older.length === PAGE_SIZE
        cacheMessages(id, older)
      } finally {
        this.loadingOlder = false
      }
    },
    async loadInfo(conversationId = this.activeConversationId) {
      if (!conversationId) return
      try {
        this.infoByConversation[conversationId] = await call(
          `${API}.get_conversation_info`, { conversation_id: conversationId }, 'GET'
        )
      } catch {
        /* non-fatal: header just shows less */
      }
    },
    async assign(user) {
      const id = this.activeConversationId
      this.infoByConversation[id] = await call(`${API}.assign_conversation`, { conversation_id: id, user: user || null })
      this.loadConversations()
    },
    async setStatus(status) {
      const id = this.activeConversationId
      this.infoByConversation[id] = await call(`${API}.set_conversation_status`, { conversation_id: id, status })
      this.loadConversations()
    },
    async setOptOut(optedOut) {
      const id = this.activeConversationId
      this.infoByConversation[id] = await call(`${API}.set_opt_out`, { conversation_id: id, opted_out: optedOut ? 1 : 0 })
    },
    async cancelScheduled(name) {
      await call(`${API}.cancel_scheduled_message`, { name })
      await this.loadInfo()
    },
    _appendSent(msg) {
      // Scheduled messages aren't in the timeline yet; they show under
      // "Scheduled" in the conversation info instead.
      if (msg.scheduled_time) {
        this.loadInfo()
        return
      }
      const id = msg.conversation_id || this.activeConversationId
      const list = this.messagesByConversation[id] || []
      if (!list.some((m) => m.name === msg.name)) this.messagesByConversation[id] = [...list, msg]
    },
    async sendText(to, message, { referenceDoctype, referenceName, scheduledTime, replyTo } = {}) {
      const msg = await call(`${API}.send_message`, {
        to,
        message,
        provider: this.provider || undefined,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
        scheduled_time: scheduledTime || undefined,
        reply_to: replyTo || undefined,
      })
      this._appendSent(msg)
      return msg
    },
    async sendMedia(to, mediaUrl, mediaType, caption, { referenceDoctype, referenceName, replyTo } = {}) {
      const msg = await call(`${API}.send_media_message`, {
        to,
        media_url: mediaUrl,
        media_type: mediaType,
        caption: caption || '',
        provider: this.provider || undefined,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
        reply_to: replyTo || undefined,
      })
      this._appendSent(msg)
      return msg
    },
    async sendLocation(to, { latitude, longitude, name, address, replyTo } = {}) {
      const msg = await call(`${API}.send_location`, {
        to, latitude, longitude, name, address,
        provider: this.provider || undefined,
        reply_to: replyTo || undefined,
      })
      this._appendSent(msg)
      return msg
    },
    async sendContactCard(to, { contact, name, phone, replyTo } = {}) {
      const msg = await call(`${API}.send_contact_card`, {
        to, contact, name, phone,
        provider: this.provider || undefined,
        reply_to: replyTo || undefined,
      })
      this._appendSent(msg)
      return msg
    },
    async sendTemplate(to, template, parameters, { referenceDoctype, referenceName, headerMediaUrl, scheduledTime, replyTo } = {}) {
      const msg = await call(`${API}.send_template_message`, {
        to,
        template,
        parameters,
        provider: this.provider || undefined,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
        header_media_url: headerMediaUrl,
        scheduled_time: scheduledTime || undefined,
        reply_to: replyTo || undefined,
      })
      this._appendSent(msg)
      return msg
    },
    // Called once on app mount. The backend emits a realtime event for every
    // new message and every delivery receipt (see publish_message_event).
    subscribeRealtime() {
      if (this._unsubscribeRealtime) return
      const offNew = onNewMessage(async (evt) => {
        if (evt.conversation_id === this.activeConversationId) {
          await this.refreshMessages(this.activeConversationId)
          if (evt.type === 'Incoming') {
            await call(`${API}.mark_as_read`, { conversation_id: this.activeConversationId })
            this.loadInfo()  // the 24-hour window just reopened
          }
        }
        this.loadConversations()
        this.loadStats()
      })
      // Delivery/read receipts for messages already on screen.
      const offUpdate = onMessageUpdate((evt) => {
        const list = this.messagesByConversation[evt.conversation_id]
        const msg = list?.find((m) => m.name === evt.name)
        if (msg) msg.status = evt.status
      })
      this._unsubscribeRealtime = () => { offNew(); offUpdate() }
    },
  },
})
