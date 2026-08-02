import { defineStore } from 'pinia'
import { call } from '@/api/frappe'
import { cacheConversations, getCachedConversations, cacheMessages, getCachedMessages } from '@/db'

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: [],
    activeConversationId: null,
    messagesByConversation: {},
    loadingConversations: false,
    loadingMessages: false,
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
        const res = await call('whatsnext.whatsnext.api.get_conversations', { limit: 100, offset: 0 }, 'GET')
        this.conversations = res.data
        cacheConversations(res.data)
      } finally {
        this.loadingConversations = false
      }
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
    async sendTemplate(to, template, parameters, referenceDoctype, referenceName) {
      const msg = await call('whatsnext.whatsnext.api.send_template_message', {
        to,
        template,
        parameters,
        reference_doctype: referenceDoctype,
        reference_name: referenceName,
      })
      const list = this.messagesByConversation[this.activeConversationId] || []
      this.messagesByConversation[this.activeConversationId] = [...list, msg]
      return msg
    },
  },
})
