<script setup>
import { onMounted, computed } from 'vue'
import { useDashboardStore } from '@/stores/dashboard'
import StatCard from '@/components/StatCard.vue'
import DonutChart from '@/components/DonutChart.vue'
import LineChart from '@/components/LineChart.vue'
import { useRouter } from 'vue-router'

const dashboard = useDashboardStore()
const router = useRouter()

onMounted(() => dashboard.load())

const donutSegments = computed(() => {
  const d = dashboard.stats?.delivery_status
  if (!d) return []
  return [
    { label: 'Delivered', value: d.delivered, color: '#16a394' },
    { label: 'Pending', value: d.pending, color: '#f59e0b' },
    { label: 'Failed', value: d.failed, color: '#ef4444' },
  ]
})

const weeklyPoints = computed(() =>
  (dashboard.stats?.weekly_overview || []).map((w) => ({
    label: new Date(w.day).toLocaleDateString(undefined, { weekday: 'short' }),
    value: w.sent,
  }))
)
</script>

<template>
  <div class="wn-dashboard">
    <div class="wn-stats-grid">
      <StatCard label="Message Queue" :value="dashboard.stats?.message_queue ?? '—'" icon="📨" tone="teal" />
      <StatCard label="Sent This Week" :value="dashboard.stats?.sent_this_week ?? '—'" icon="✅" tone="blue" />
      <StatCard label="Failed Messages" :value="dashboard.stats?.failed_messages ?? '—'" icon="⚠️" tone="red" />
      <StatCard label="Scheduled Jobs" :value="dashboard.stats?.scheduled_jobs ?? '—'" icon="⏰" tone="amber" />
    </div>

    <div class="wn-quick-actions">
      <button @click="router.push('/whatsnext')">Send Message</button>
      <button @click="router.push('/whatsnext/campaigns')">Create Campaign</button>
      <button class="ghost" @click="router.push('/whatsnext/templates')">Manage Templates</button>
    </div>

    <div class="wn-grid-2">
      <div class="wn-card">
        <h3>Delivery Status</h3>
        <DonutChart
          v-if="dashboard.stats"
          :segments="donutSegments"
          :center-value="dashboard.stats.delivery_status.delivered_pct + '%'"
          center-label="Delivered"
        />
      </div>

      <div class="wn-card">
        <h3>This Week Overview</h3>
        <LineChart v-if="weeklyPoints.length" :points="weeklyPoints" />
        <p v-else class="wn-muted">No data yet this week</p>
      </div>
    </div>

    <div class="wn-grid-2">
      <div class="wn-card">
        <h3>Top Templates</h3>
        <ul class="wn-simple-list">
          <li v-for="t in dashboard.stats?.top_templates || []" :key="t.template">
            <span>{{ t.template }}</span>
            <strong>{{ t.cnt }}</strong>
          </li>
          <li v-if="!dashboard.stats?.top_templates?.length" class="wn-muted">No template messages sent yet</li>
        </ul>
      </div>

      <div class="wn-card">
        <h3>Recent Messages</h3>
        <ul class="wn-simple-list">
          <li v-for="m in dashboard.stats?.recent_messages || []" :key="m.name">
            <span>{{ m.to_number }} — {{ m.template || (m.message || '').slice(0, 30) }}</span>
            <span class="wn-status" :class="m.status?.toLowerCase()">{{ m.status }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-dashboard { display: flex; flex-direction: column; gap: 20px; }
.wn-stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.wn-quick-actions { display: flex; gap: 10px; }
.wn-quick-actions button {
  padding: 10px 16px; border-radius: 10px; border: none; background: var(--wn-teal); color: white;
  font-weight: 600; font-size: 13px;
}
.wn-quick-actions button.ghost { background: white; color: var(--wn-teal); border: 1px solid var(--wn-teal); }
.wn-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 18px; }
.wn-card h3 { margin: 0 0 14px; font-size: 14px; color: var(--wn-navy); }
.wn-simple-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; font-size: 13px; }
.wn-simple-list li { display: flex; justify-content: space-between; gap: 10px; }
.wn-status { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #eef2f2; }
.wn-status.delivered, .wn-status.read { background: #e6f7f4; color: var(--wn-teal); }
.wn-status.failed { background: #fee2e2; color: var(--wn-red); }
.wn-status.pending, .wn-status.queued { background: #fef3c7; color: var(--wn-amber); }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }

@media (max-width: 900px) {
  .wn-stats-grid { grid-template-columns: repeat(2, 1fr); }
  .wn-grid-2 { grid-template-columns: 1fr; }
}
</style>
