<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { call } from '@/api/frappe'
import { useCampaignsStore } from '@/stores/campaigns'
import { useRecipientListsStore } from '@/stores/recipientLists'
import { parseRecipientsCsv, recipientsToCsv } from '@/lib/csv'

const campaigns = useCampaignsStore()
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
})

const parsedRecipients = computed(() => parseRecipientsCsv(form.value.csvText))
const invalidRecipients = computed(() => parsedRecipients.value.filter((r) => !r.valid))

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
  form.value = { campaign_name: '', template: '', csvText: '' }
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
  launching.value = true
  try {
    await campaigns.create(form.value.campaign_name, form.value.template, recipients)
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
    const stillRunning = campaigns.campaigns.some((c) => c.status === 'Queued' || c.status === 'Sending')
    if (!stillRunning) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }, 3000)
}

onMounted(async () => {
  await campaigns.load()
  const running = campaigns.campaigns.some((c) => c.status === 'Queued' || c.status === 'Sending')
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

function progressPct(c) {
  if (!c.total_recipients) return 0
  return Math.round(((c.sent_count + c.failed_count) / c.total_recipients) * 100)
}
</script>

<template>
  <div class="wn-campaigns">
    <div class="wn-toolbar">
      <p class="wn-muted">Send a template message to many recipients at once, paced to avoid provider rate limits.</p>
      <button class="primary" @click="openNew">+ New Campaign</button>
    </div>

    <div class="wn-card">
      <table class="wn-table">
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Template</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Sent</th>
            <th>Failed</th>
            <th>Results</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in campaigns.campaigns" :key="c.name">
            <td>{{ c.campaign_name }}</td>
            <td>{{ c.template }}</td>
            <td><span class="wn-status" :class="c.status.toLowerCase()">{{ c.status }}</span></td>
            <td class="wn-progress-cell">
              <div class="wn-progress-bar"><div class="wn-progress-fill" :style="{ width: progressPct(c) + '%' }"></div></div>
              <span class="wn-progress-label">{{ c.sent_count + c.failed_count }}/{{ c.total_recipients }}</span>
            </td>
            <td>{{ c.sent_count }}</td>
            <td>{{ c.failed_count }}</td>
            <td class="wn-download-cell">
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
            <td colspan="7" class="wn-muted">No campaigns yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showForm" class="wn-modal-backdrop" @click.self="showForm = false">
      <div class="wn-modal">
        <h3>New Campaign</h3>

        <label>Campaign Name</label>
        <input v-model="form.campaign_name" placeholder="August promo" />

        <label>Template</label>
        <select v-model="form.template">
          <option value="" disabled>Select a template</option>
          <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.template_name }} ({{ t.provider }})</option>
        </select>

        <label>
          Recipients — paste CSV or upload a file. First column is the phone number;
          optional header row starting with "phone" or "to"; remaining columns fill
          <code v-pre>{{1}}</code>, <code v-pre>{{2}}</code>… in order.
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
          <button class="primary" :disabled="launching || invalidRecipients.length > 0" @click="launch">{{ launching ? 'Launching…' : 'Launch Campaign' }}</button>
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
</style>
