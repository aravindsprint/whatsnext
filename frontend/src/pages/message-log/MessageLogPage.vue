<script setup>
import { onMounted, ref, computed } from 'vue'
import { call } from '@/api/frappe'

const messages = ref([])
const loading = ref(false)
const statusFilter = ref('All')

async function load() {
  loading.value = true
  try {
    const res = await call('whatsnext.whatsnext.api.get_conversations', { limit: 200, offset: 0 }, 'GET')
    messages.value = res.data
  } finally {
    loading.value = false
  }
}
onMounted(load)

const filtered = computed(() => {
  if (statusFilter.value === 'All') return messages.value
  return messages.value.filter((m) => m.status === statusFilter.value)
})

const statuses = ['All', 'Pending', 'Queued', 'Sent', 'Delivered', 'Read', 'Failed']
</script>

<template>
  <div class="wn-log">
    <div class="wn-toolbar">
      <div class="wn-filters">
        <button v-for="s in statuses" :key="s" :class="{ active: statusFilter === s }" @click="statusFilter = s">{{ s }}</button>
      </div>
      <button class="ghost" @click="load">Refresh</button>
    </div>

    <div class="wn-card">
      <table class="wn-table">
        <thead>
          <tr>
            <th>To / From</th>
            <th>Type</th>
            <th>Provider</th>
            <th>Message</th>
            <th>Status</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in filtered" :key="m.name">
            <td>{{ m.to_number || m.from_number }}</td>
            <td>{{ m.type }}</td>
            <td>{{ m.provider || '—' }}</td>
            <td class="wn-msg-cell">{{ m.template ? '📋 ' + m.template : (m.message || '').slice(0, 60) }}</td>
            <td><span class="wn-status" :class="(m.status || '').toLowerCase()">{{ m.status }}</span></td>
            <td>{{ new Date(m.modified).toLocaleString() }}</td>
          </tr>
          <tr v-if="!loading && !filtered.length">
            <td colspan="6" class="wn-muted">No messages found.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.wn-log { display: flex; flex-direction: column; gap: 14px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.wn-filters { display: flex; gap: 6px; flex-wrap: wrap; }
.wn-filters button { padding: 6px 12px; border-radius: 16px; border: 1px solid var(--wn-border); background: white; font-size: 12px; }
.wn-filters button.active { background: var(--wn-navy); color: white; border-color: var(--wn-navy); }
button.ghost { background: white; border: 1px solid var(--wn-border); padding: 8px 14px; border-radius: 10px; font-size: 13px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); overflow-x: auto; }
.wn-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.wn-table th { text-align: left; padding: 12px 14px; font-size: 11px; text-transform: uppercase; color: var(--wn-text-muted); border-bottom: 1px solid var(--wn-border); }
.wn-table td { padding: 10px 14px; border-bottom: 1px solid var(--wn-border); }
.wn-msg-cell { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wn-status { font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #eef2f2; }
.wn-status.delivered, .wn-status.read { background: #e6f7f4; color: var(--wn-teal); }
.wn-status.failed { background: #fee2e2; color: var(--wn-red); }
.wn-status.pending, .wn-status.queued { background: #fef3c7; color: var(--wn-amber); }
.wn-muted { color: var(--wn-text-muted); text-align: center; padding: 24px !important; }
</style>
