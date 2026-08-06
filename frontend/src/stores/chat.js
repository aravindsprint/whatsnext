import { defineStore } from 'pinia'
import { call } from '@/api/frappe'
import { cacheConversations, getCachedConversations, cacheMessages, getCachedMessages } from '@/db'
import { onNewMessage } from '@/realtime'

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: [],
    activeConversationId: null,
    messagesByConversation: {},
    loadingConversations: false,
    loadingMessages: false,
    search: '',
    filter: 'all',
    stats: { total: 0, unread: 0, sent: 0 },
  }),
  getters: {
    activeMessages: (state) => state.messagesByConversation[state.activeConversationId] || [],
  },
  actions: {
    async loadConversations() {
      this.loadingConversations = true
      // Show cached data immediately, then refresh from the server
      this.conversations = await getCachedConversations()
      try {
        const res = await call('whatsnext.whatsnext.api.get_conversations', {
          limit: 100,
          offset: 0,
          search: this.search || undefined,
          filter: this.filter === 'all' ? undefined : this.filter,
        }, 'GET')
        this.conversations = res.data
        cacheConversations(res.data)
      } finally {
        this.loadingConversations = false
      }
    },
    async loadStats() {
      this.stats = await call('whatsnext.whatsnext.api.get_conversation_stats', {}, 'GET')
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
      try {
        const messages = await call(
          'whatsnext.whatsnext.api.get_messages',
          { conversation_id: conversationId, limit: 200 },
          'GET'
        )
        this.messagesByConversation[conversationId] = messages
        cacheMessages(conversationId, messages)
        await call('whatsnext.whatsnext.api.mark_as_read', { conversation_id: conversationId })
      } finally {
        this.loadingMessages = false
      }
    },
    async sendText(to, message, referenceDoctype, referenceName) {
      const msg = await call('whatsnext.whatsnext.api.send_message', {
        to,
        message,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
      })
      const list = this.messagesByConversation[this.activeConversationId] || []
      this.messagesByConversation[this.activeConversationId] = [...list, msg]
      return msg
    },
    async sendMedia(to, mediaUrl, mediaType, caption, referenceDoctype, referenceName) {
      const msg = await call('whatsnext.whatsnext.api.send_media_message', {
        to,
        media_url: mediaUrl,
        media_type: mediaType,
        caption: caption || '',
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
      })
      const list = this.messagesByConversation[this.activeConversationId] || []
      this.messagesByConversation[this.activeConversationId] = [...list, msg]
      return msg
    },
    // Called once on app mount. The backend already emits a realtime event
    // on every new Whatsnext Message (see WhatsnextMessage.after_insert) --
    // previously nothing listened for it, so incoming messages only ever
    // showed up after a manual page reload. Wiring this up keeps both the
    // open conversation and the sidebar list/unread counts live.
    subscribeRealtime() {
      if (this._unsubscribeRealtime) return
      this._unsubscribeRealtime = onNewMessage(async (evt) => {
        if (evt.conversation_id === this.activeConversationId) {
          const messages = await call(
            'whatsnext.whatsnext.api.get_messages',
            { conversation_id: this.activeConversationId, limit: 200 },
            'GET'
          )
          this.messagesByConversation[this.activeConversationId] = messages
          cacheMessages(this.activeConversationId, messages)
          if (evt.type === 'Incoming') {
            await call('whatsnext.whatsnext.api.mark_as_read', { conversation_id: this.activeConversationId })
          }
        }
        this.loadConversations()
        this.loadStats()
      })
    },
    async sendTemplate(to, template, parameters, referenceDoctype, referenceName, headerMediaUrl) {
      const msg = await call('whatsnext.whatsnext.api.send_template_message', {
        to,
        template,
        parameters,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
        header_media_url: headerMediaUrl,
      })
      const list = this.messagesByConversation[this.activeConversationId] || []
      this.messagesByConversation[this.activeConversationId] = [...list, msg]
      return msg
    },
  },
})
