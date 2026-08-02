import { defineStore } from 'pinia'
import { call } from '@/api/frappe'

export const useRecipientListsStore = defineStore('recipientLists', {
  state: () => ({
    lists: [],
    loading: false,
  }),
  actions: {
    async load() {
      this.loading = true
      try {
        this.lists = await call('whatsnext.whatsnext.api.list_recipient_lists', {}, 'GET')
      } finally {
        this.loading = false
      }
    },
    async save(listName, recipients, description) {
      const doc = await call('whatsnext.whatsnext.api.save_recipient_list', {
        list_name: listName,
        recipients,
        description,
      })
      await this.load()
      return doc
    },
    async get(listName) {
      return call('whatsnext.whatsnext.api.get_recipient_list', { list_name: listName }, 'GET')
    },
    async remove(listName) {
      await call('whatsnext.whatsnext.api.delete_recipient_list', { list_name: listName })
      await this.load()
    },
  },
})
