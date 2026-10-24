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
    async create(campaignName, template, recipients, { provider, scheduledTime } = {}) {
      return call('whatsnext.whatsnext.api.create_campaign', {
        campaign_name: campaignName,
        template,
        recipients,
        provider,
        scheduled_time: scheduledTime,
      })
    },
    async pause(campaignName) {
      return call('whatsnext.whatsnext.api.pause_campaign', { campaign_name: campaignName })
    },
    async cancel(campaignName) {
      return call('whatsnext.whatsnext.api.cancel_campaign', { campaign_name: campaignName })
    },
    async retryFailed(campaignName) {
      return call('whatsnext.whatsnext.api.retry_failed_campaign', { campaign_name: campaignName })
    },
    async start(campaignName) {
      return call('whatsnext.whatsnext.api.start_campaign', { campaign_name: campaignName })
    },
    async getStatus(campaignName) {
      return call('whatsnext.whatsnext.api.get_campaign', { campaign_name: campaignName }, 'GET')
    },
  },
})
