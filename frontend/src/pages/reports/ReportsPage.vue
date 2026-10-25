<script setup>
import { computed, onMounted, ref } from 'vue'
import { call } from '@/api/frappe'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

function isoDate(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const today = new Date()
const weekAgo = new Date()
weekAgo.setDate(today.getDate() - 6)

const fromDate = ref(isoDate(weekAgo))
const toDate = ref(isoDate(today))
const report = ref(null)
const loading = ref(false)
const error = ref(null)

const RANGES = [
  ['Today', 0], ['7 days', 6], ['30 days', 29], ['90 days', 89],
]
function setRange(days) {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - days)
  fromDate.value = isoDate(start)
  toDate.value = isoDate(end)
  load()
}

async function load() {
  loading.value = true
  error.value = null
  try {
    report.value = await call('whatsnext.whatsnext.api.agent_report', { from_date: fromDate.value, to_date: toDate.value }, 'GET')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

function minutes(value) {
  if (value === null || value === undefined) return '—'
  if (value < 1) return '< 1 min'
  if (value < 60) return `${Math.round(value)} min`
  const h = Math.floor(value / 60)
  const m = Math.round(value % 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

const totals = computed(() => {
  const agents = report.value?.agents || []
  const replies = agents.reduce((s, a) => s + a.replies, 0)
  const weighted = agents.reduce((s, a) => s + (a.avg_response_minutes || 0) * a.replies, 0)
  return {
    sent: agents.reduce((s, a) => s + a.messages_sent, 0),
    replies,
    avg: replies ? weighted / replies : null,
  }
})
</script>

<template>
  <div class="wn-reports">
    <div class="wn-toolbar">
      <div class="wn-range">
        <button v-for="[label, days] in RANGES" :key="label" class="ghost small" @click="setRange(days)">{{ label }}</button>
      </div>
      <div class="wn-dates">
        <input v-model="fromDate" type="date" @change="load" />
        <span>to</span>
        <input v-model="toDate" type="date" @change="load" />
      </div>
    </div>

    <p class="wn-muted">
      Agent activity in the chat: messages typed by people (notifications, campaigns and auto-replies excluded),
      and how long customers waited for the first reply after writing.
      <template v-if="!auth.isSystemManager">You're seeing your own numbers.</template>
    </p>
    <p v-if="error" class="wn-error">{{ error }}</p>

    <div v-if="report" class="wn-tiles">
      <div class="wn-tile"><div class="wn-tile-value">{{ totals.sent }}</div><div class="wn-tile-label">Messages sent by agents</div></div>
      <div class="wn-tile"><div class="wn-tile-value">{{ minutes(totals.avg) }}</div><div class="wn-tile-label">Average first response</div></div>
      <template v-if="report.totals">
        <div class="wn-tile"><div class="wn-tile-value">{{ report.totals.incoming_messages }}</div><div class="wn-tile-label">Customer messages</div></div>
        <div class="wn-tile" :class="{ warn: report.totals.chats_waiting_for_reply }">
          <div class="wn-tile-value">{{ report.totals.chats_waiting_for_reply }}</div><div class="wn-tile-label">Chats left without a reply</div>
        </div>
        <div class="wn-tile"><div class="wn-tile-value">{{ report.totals.unassigned_open_chats }}</div><div class="wn-tile-label">Open chats unassigned (now)</div></div>
      </template>
    </div>

    <div class="wn-card">
      <table v-table-labels class="wn-table wn-stack">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Messages sent</th>
            <th>Chats handled</th>
            <th>Replies</th>
            <th>Avg first response</th>
            <th>Median</th>
            <th>Open chats assigned</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in report?.agents || []" :key="a.user">
            <td><strong>{{ a.full_name || a.user }}</strong><div class="wn-muted-small">{{ a.user }}</div></td>
            <td>{{ a.messages_sent }}</td>
            <td>{{ a.chats_handled }}</td>
            <td>{{ a.replies }}</td>
            <td>{{ minutes(a.avg_response_minutes) }}</td>
            <td>{{ minutes(a.median_response_minutes) }}</td>
            <td>{{ a.open_assigned }}</td>
          </tr>
          <tr v-if="!loading && report && !report.agents.length">
            <td colspan="7" class="wn-muted">No agent activity in this period.</td>
          </tr>
          <tr v-if="loading"><td colspan="7" class="wn-muted">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.wn-reports { display: flex; flex-direction: column; gap: 14px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.wn-range { display: flex; gap: 6px; flex-wrap: wrap; }
.wn-dates { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--wn-text-muted); }
.wn-dates input { padding: 7px 9px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; margin: 0; }
.wn-muted-small { font-size: 11px; color: var(--wn-text-muted); }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.wn-tile { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 14px 16px; }
.wn-tile.warn .wn-tile-value { color: var(--wn-amber); }
.wn-tile-value { font-size: 22px; font-weight: 700; color: var(--wn-navy); }
.wn-tile-label { font-size: 12px; color: var(--wn-text-muted); margin-top: 2px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 12px 16px; overflow-x: auto; }
.wn-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 640px; }
.wn-table th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--wn-text-muted); padding: 8px; border-bottom: 1px solid var(--wn-border); }
.wn-table td { padding: 10px 8px; border-bottom: 1px solid var(--wn-border); }
</style>
