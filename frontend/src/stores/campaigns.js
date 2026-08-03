import { defineStore } from 'pinia'
import { call } from '@/api/frappe'

export const useCampaignsStore = defineStore('campaigns', {
  state: () => ({
    campaigns: [],
    loading: false,
    activePoll: null,
  }),
  actions: {
    async load() {
      this.loading = true
      try {
        this.campaigns = await call('whatsnext.whatsnext.api.list_campaigns', {}, 'GET')
      } finally {
        this.loading = false
      }
    },
    async create(campaignName, template, recipients) {
      return call('whatsnext.whatsnext.api.create_campaign', {
        campaign_name: campaignName,
        template,
        recipients,
      })
    },
    async start(campaignName) {
      return call('whatsnext.whatsnext.api.start_campaign', { campaign_name: campaignName })
    },
    async getStatus(campaignName) {
      return call('whatsnext.whatsnext.api.get_campaign', { campaign_name: campaignName }, 'GET')
    },
  },
})
