import { defineStore } from 'pinia'
import { call } from '@/api/frappe'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    stats: null,
    loading: false,
  }),
  actions: {
    async load() {
      this.loading = true
      try {
        this.stats = await call('whatsnext.whatsnext.api.dashboard_stats', {}, 'GET')
      } finally {
        this.loading = false
      }
    },
  },
})
