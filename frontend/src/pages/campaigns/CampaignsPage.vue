<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { call } from '@/api/frappe'
import { useCampaignsStore } from '@/stores/campaigns'
import { useRecipientListsStore } from '@/stores/recipientLists'
import { parseRecipientsCsv, recipientsToCsv } from '@/lib/csv'
import { toFrappeDatetime } from '@/lib/templateVars'
import { parseFrappeDate } from '@/lib/date'
import { useAuthStore } from '@/stores/auth'

const campaigns = useCampaignsStore()
const auth = useAuthStore()
const rowBusy = ref(null)
const rowError = ref(null)
const recipientLists = useRecipientListsStore()
const showForm = ref(false)
const templates = ref([])
const error = ref(null)
const launching = ref(false)
const selectedList = ref('')
let pollTimer = null

const form = ref({
  campaign_name: '',
  template: '',
  csvText: '',
  provider: '',
  scheduleOn: false,
  scheduleAt: '',
})

const parsedRecipients = computed(() => parseRecipientsCsv(form.value.csvText))
const invalidRecipients = computed(() => parsedRecipients.value.filter((r) => !r.valid))
const selectedTemplate = computed(() => templates.value.find((t) => t.name === form.value.template))

async function loadTemplates() {
  templates.value = await call('whatsnext.whatsnext.api.get_templates', {}, 'GET')
}

async function loadFromList() {
  if (!selectedList.value) return
  const doc = await recipientLists.get(selectedList.value)
  form.value.csvText = recipientsToCsv(doc.recipients)
}

async function onFileUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  form.value.csvText = await file.text()
}

function openNew() {
  form.value = { campaign_name: '', template: '', csvText: '', provider: '', scheduleOn: false, scheduleAt: '' }
  error.value = null
  selectedList.value = ''
  showForm.value = true
  if (!templates.value.length) loadTemplates()
  if (!recipientLists.lists.length) recipientLists.load()
}

async function launch() {
  error.value = null
  if (!form.value.campaign_name || !form.value.template) {
    error.value = 'Campaign name and template are required.'
    return
  }
  const recipients = parsedRecipients.value
  if (!recipients.length) {
    error.value = 'Add at least one recipient.'
    return
  }
  if (invalidRecipients.value.length) {
    error.value = `${invalidRecipients.value.length} recipient(s) have an invalid phone number — check the highlighted rows below.`
    return
  }
  if (form.value.scheduleOn && !form.value.scheduleAt) {
    error.value = 'Pick a date and time, or turn off scheduling.'
    return
  }
  launching.value = true
  try {
    try {
      await campaigns.create(form.value.campaign_name, form.value.template, recipients, {
        provider: form.value.provider || undefined,
        scheduledTime: form.value.scheduleOn ? toFrappeDatetime(form.value.scheduleAt) : undefined,
      })
    } catch (e) {
      // A previous attempt may have created the campaign and then failed to
      // start it; launching again should start that draft, not error out.
      const existing = (e.message || '').includes('DuplicateEntryError')
        && campaigns.campaigns.find((c) => c.name === form.value.campaign_name && c.status === 'Draft')
      if (!existing) throw e
    }
    await campaigns.start(form.value.campaign_name)
    showForm.value = false
    await campaigns.load()
    startPolling()
  } catch (e) {
    if (e.message && e.message.includes('DuplicateEntryError')) {
      error.value = `A campaign named "${form.value.campaign_name}" already exists — pick a different name.`
    } else {
      error.value = e.message
    }
  } finally {
    launching.value = false
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    await campaigns.load()
    const stillRunning = campaigns.campaigns.some((c) => ['Queued', 'Sending', 'Scheduled'].includes(c.status))
    if (!stillRunning) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 3000)
}

onMounted(async () => {
  await campaigns.load()
  const running = campaigns.campaigns.some((c) => ['Queued', 'Sending', 'Scheduled'].includes(c.status))
  if (running) startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

function downloadResults(campaignName, format) {
  const url = `/api/method/whatsnext.whatsnext.api.export_campaign_results?campaign_name=${encodeURIComponent(campaignName)}&format=${format}`
  window.open(url, '_blank')
}
const openDownloadMenu = ref(null)

function processed(c) {
  return (c.sent_count || 0) + (c.failed_count || 0) + (c.skipped_count || 0)
}

function progressPct(c) {
  if (!c.total_recipients) return 0
  return Math.round((processed(c) / c.total_recipients) * 100)
}

async function rowAction(c, action) {
  if (action === 'cancel' && !confirm(`Cancel campaign "${c.campaign_name}"? Recipients not yet messaged won't be sent.`)) return
  rowBusy.value = c.name
  rowError.value = null
  try {
    await campaigns[action](c.name)
    await campaigns.load()
    startPolling()
  } catch (e) {
    rowError.value = e.message
  } finally {
    rowBusy.value = null
  }
}
</script>

<template>
  <div class="wn-campaigns">
    <div class="wn-toolbar">
      <p class="wn-muted">Send a template message to many recipients at once, paced to avoid provider rate limits.</p>
      <button class="primary" @click="openNew">+ New Campaign</button>
    </div>

    <div class="wn-card">
      <table v-table-labels class="wn-table wn-stack wn-stack-lg">
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Template</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Sent</th>
            <th>Delivered</th>
            <th>Failed</th>
            <th>Skipped</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in campaigns.campaigns" :key="c.name">
            <td>{{ c.campaign_name }}</td>
            <td>{{ c.template }}</td>
            <td>
              <span class="wn-status" :class="(c.status || '').toLowerCase()">{{ c.status }}</span>
              <div v-if="c.status === 'Scheduled' && c.scheduled_time" class="wn-muted-small">{{ parseFrappeDate(c.scheduled_time).toLocaleString() }}</div>
            </td>
            <td class="wn-progress-cell">
              <div class="wn-progress-bar"><div class="wn-progress-fill" :style="{ width: progressPct(c) + '%' }"></div></div>
              <span class="wn-progress-label">{{ processed(c) }}/{{ c.total_recipients }}</span>
            </td>
            <td>{{ c.sent_count }}</td>
            <td>{{ c.delivered_count || 0 }}</td>
            <td>{{ c.failed_count }}</td>
            <td>{{ c.skipped_count || 0 }}</td>
            <td class="wn-download-cell">
              <div class="wn-row-actions">
                <button v-if="['Queued','Sending','Scheduled'].includes(c.status)" class="ghost small" :disabled="rowBusy === c.name" @click="rowAction(c, 'pause')">Pause</button>
                <button v-if="['Paused','Draft'].includes(c.status)" class="ghost small" :disabled="rowBusy === c.name" @click="rowAction(c, 'start')">{{ c.status === 'Paused' ? 'Resume' : 'Start' }}</button>
                <button v-if="c.failed_count && ['Completed','Failed','Paused'].includes(c.status)" class="ghost small" :disabled="rowBusy === c.name" @click="rowAction(c, 'retryFailed')">Retry failed</button>
                <button v-if="!['Completed','Cancelled'].includes(c.status)" class="ghost small danger" :disabled="rowBusy === c.name" @click="rowAction(c, 'cancel')">Cancel</button>
              </div>
              <div class="wn-download-menu">
                <button class="ghost small" @click="openDownloadMenu = openDownloadMenu === c.name ? null : c.name">Download ▾</button>
                <div v-if="openDownloadMenu === c.name" class="wn-download-options" @mouseleave="openDownloadMenu = null">
                  <button @click="downloadResults(c.name, 'xlsx'); openDownloadMenu = null">Excel (.xlsx)</button>
                  <button @click="downloadResults(c.name, 'pdf'); openDownloadMenu = null">PDF</button>
                </div>
              </div>
            </td>
          </tr>
          <tr v-if="!campaigns.loading && !campaigns.campaigns.length">
            <td colspan="9" class="wn-muted">No campaigns yet.</td>
          </tr>
        </tbody>
      </table>
      <p v-if="rowError" class="wn-error">{{ rowError }}</p>
    </div>

    <div v-if="showForm" class="wn-modal-backdrop" @click.self="showForm = false">
      <div class="wn-modal">
        <h3>New Campaign</h3>

        <label>Campaign Name</label>
        <input v-model="form.campaign_name" placeholder="August promo" />

        <label>Template</label>
        <select v-model="form.template">
          <option value="" disabled>Select a template</option>
          <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.template_name }} ({{ t.provider }}{{ t.approval_status !== 'Approved' ? ' · ' + t.approval_status : '' }})</option>
        </select>
        <p v-if="selectedTemplate?.category === 'Marketing'" class="wn-muted-small">
          Marketing template — numbers that opted out are skipped automatically.
        </p>

        <template v-if="auth.providers.length > 1">
          <label>Send via</label>
          <select v-model="form.provider">
            <option value="">Default ({{ auth.defaultProvider }})</option>
            <option v-for="p in auth.providers" :key="p" :value="p">{{ p }}</option>
          </select>
        </template>

        <label class="wn-check"><input v-model="form.scheduleOn" type="checkbox" /> Schedule for later</label>
        <input v-if="form.scheduleOn" v-model="form.scheduleAt" type="datetime-local" />

        <label>
          Recipients — paste CSV or upload a file. First column is the phone number;
          optional header row starting with "phone" or "to"; remaining columns fill
          <code v-pre>{{1}}</code>, <code v-pre>{{2}}</code>… in order (or name header columns
          <code>1</code>, <code>2</code>, <code>header_1</code>, <code>button_0</code> to target them).
        </label>
        <div class="wn-load-list-row">
          <select v-model="selectedList" @change="loadFromList">
            <option value="">Or load a saved recipient list…</option>
            <option v-for="l in recipientLists.lists" :key="l.name" :value="l.list_name">
              {{ l.list_name }} ({{ l.recipient_count }})
            </option>
          </select>
        </div>
        <textarea v-model="form.csvText" rows="6" placeholder="phone,1,2&#10;+919876543210,John,INV-1001&#10;+919812345678,Priya,INV-1002"></textarea>
        <input type="file" accept=".csv,text/csv" @change="onFileUpload" />

        <p class="wn-preview-count">
          {{ parsedRecipients.length }} recipient(s) parsed
          <span v-if="invalidRecipients.length" class="wn-preview-invalid">— {{ invalidRecipients.length }} invalid number(s)</span>
        </p>
        <table v-if="parsedRecipients.length" class="wn-preview-table">
          <tbody>
            <tr v-for="(r, i) in parsedRecipients.slice(0, 5)" :key="i" :class="{ 'wn-row-invalid': !r.valid }">
              <td>{{ r.to_number }} <span v-if="!r.valid" class="wn-invalid-tag">not a phone number</span></td>
              <td>{{ Object.values(r.parameters).join(', ') }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="parsedRecipients.length > 5" class="wn-muted">…and {{ parsedRecipients.length - 5 }} more</p>

        <p v-if="error" class="wn-error">{{ error }}</p>

        <div class="wn-modal-actions">
          <button class="ghost" @click="showForm = false">Cancel</button>
          <button class="primary" :disabled="launching || invalidRecipients.length > 0" @click="launch">{{ launching ? 'Launching…' : (form.scheduleOn ? 'Schedule Campaign' : 'Launch Campaign') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-campaigns { display: flex; flex-direction: column; gap: 16px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }
button.primary { background: var(--wn-teal); color: white; border: none; padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 13px; }
button.ghost { background: white; border: 1px solid var(--wn-border); padding: 10px 16px; border-radius: 10px; font-size: 13px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); overflow-x: auto; }
.wn-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.wn-table th { text-align: left; padding: 12px 14px; font-size: 11px; text-transform: uppercase; color: var(--wn-text-muted); border-bottom: 1px solid var(--wn-border); }
.wn-table td { padding: 10px 14px; border-bottom: 1px solid var(--wn-border); }
.wn-status { font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #eef2f2; }
.wn-status.completed { background: #e6f7f4; color: var(--wn-teal); }
.wn-status.failed { background: #fee2e2; color: var(--wn-red); }
.wn-status.sending, .wn-status.queued { background: #fef3c7; color: var(--wn-amber); }
.wn-progress-cell { display: flex; align-items: center; gap: 8px; min-width: 160px; }
.wn-progress-bar { flex: 1; height: 6px; background: #eef2f2; border-radius: 4px; overflow: hidden; }
.wn-progress-fill { height: 100%; background: var(--wn-teal); transition: width 0.3s; }
.wn-progress-label { font-size: 11px; color: var(--wn-text-muted); white-space: nowrap; }
.wn-download-cell { position: relative; }
button.ghost.small { padding: 6px 10px; font-size: 12px; border-radius: 8px; }
.wn-download-menu { position: relative; display: inline-block; }
.wn-download-options {
  position: absolute; top: 100%; right: 0; margin-top: 4px; z-index: 10;
  background: white; border: 1px solid var(--wn-border); border-radius: 8px;
  box-shadow: var(--wn-shadow); display: flex; flex-direction: column; min-width: 130px; overflow: hidden;
}
.wn-download-options button {
  background: none; border: none; text-align: left; padding: 8px 12px; font-size: 12.5px; cursor: pointer;
}
.wn-download-options button:hover { background: #f2f7f7; }

.wn-modal-backdrop { position: fixed; inset: 0; background: rgba(15,61,62,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.wn-modal { background: white; border-radius: 14px; padding: 24px; width: 520px; max-width: 92vw; max-height: 88vh; overflow-y: auto; }
.wn-modal h3 { margin-top: 0; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 12px 0 4px; line-height: 1.5; }
.wn-modal input, .wn-modal select, .wn-modal textarea { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; font-family: inherit; }
.wn-modal textarea { font-family: ui-monospace, monospace; font-size: 12px; }
.wn-preview-count { font-size: 12px; color: var(--wn-teal); font-weight: 600; margin-top: 10px; }
.wn-preview-invalid { color: var(--wn-red); }
.wn-row-invalid { background: #fef2f2; }
.wn-invalid-tag { color: var(--wn-red); font-size: 10.5px; font-weight: 600; margin-left: 6px; }
.wn-preview-table { width: 100%; font-size: 12px; margin-top: 6px; }
.wn-preview-table td { padding: 4px 6px; border-bottom: 1px solid var(--wn-border); }
.wn-load-list-row { margin-bottom: 8px; }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }
.wn-row-actions { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.wn-muted-small { font-size: 11px; color: var(--wn-text-muted); margin-top: 2px; }
.wn-check { display: flex !important; align-items: center; gap: 6px; }
.wn-check input { width: auto !important; }
.wn-status.scheduled, .wn-status.paused { background: #e0e7ff; color: #3730a3; }
.wn-status.cancelled { background: var(--wn-bg); color: var(--wn-text-muted); }
.wn-card { overflow-x: auto; }
</style>
