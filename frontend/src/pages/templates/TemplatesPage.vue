<script setup>
import { onMounted, ref, computed } from 'vue'
import { call } from '@/api/frappe'
import { useAuthStore } from '@/stores/auth'
import { templateInputs } from '@/lib/templateVars'

const auth = useAuthStore()
const submitting = ref(null)
const submitResult = ref(null)

const templates = ref([])
const search = ref('')
const filteredTemplates = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return templates.value
  return templates.value.filter((t) =>
    (t.template_name || '').toLowerCase().includes(q) ||
    (t.body || '').toLowerCase().includes(q)
  )
})
const loading = ref(false)
const showForm = ref(false)
const saving = ref(false)
const error = ref(null)
const editingName = ref(null)
const syncing = ref(false)
const syncResult = ref(null)

const blank = () => ({
  template_name: '',
  provider: 'Both',
  language: 'en',
  category: 'Utility',
  header_type: 'None',
  header_text: '',
  header_example_url: '',
  body: '',
  footer_text: '',
  twilio_content_sid: '',
  buttons: [],
  samples: {},
})
const form = ref(blank())

const needsTwilioSid = computed(() => ['Twilio', 'Both'].includes(form.value.provider))
// Example values Meta requires at review time for every {{n}} (and a text
// header's {{1}}); stored in variables_sample.
const sampleInputs = computed(() =>
  templateInputs({ ...form.value, buttons: [] }).map((i) => ({ ...i, label: i.label.replace('Variable', 'Example for') }))
)
function parseSamples(v) {
  try { return typeof v === 'string' ? JSON.parse(v || '{}') : (v || {}) } catch { return {} }
}
function addButton() {
  form.value.buttons.push({ button_type: 'Quick Reply', button_text: '', button_value: '' })
}
function canSubmitToMeta(t) {
  return auth.isSystemManager && auth.providers.includes('Meta') && ['Meta', 'Both'].includes(t.provider)
    && (!t.meta_template_id || ['Draft', 'Rejected'].includes(t.approval_status))
}
async function submitToMeta(t) {
  submitting.value = t.name
  submitResult.value = null
  error.value = null
  try {
    const res = await call('whatsnext.whatsnext.api.submit_template_to_meta', { template: t.name })
    submitResult.value = `"${t.template_name}" submitted to Meta as ${res.meta_name} — status: ${res.status}.`
    await load()
  } catch (e) {
    submitResult.value = null
    error.value = e.message
  } finally {
    submitting.value = null
  }
}

async function load() {
  loading.value = true
  try {
    templates.value = await call('whatsnext.whatsnext.api.get_templates', {}, 'GET')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openNew() {
  editingName.value = null
  form.value = blank()
  error.value = null
  showForm.value = true
}

function openEdit(t) {
  editingName.value = t.name
  form.value = {
    template_name: t.template_name,
    provider: t.provider,
    language: t.language,
    category: t.category,
    header_type: t.header_type || 'None',
    header_text: t.header_text || '',
    header_example_url: t.header_example_url || '',
    body: t.body,
    footer_text: t.footer_text || '',
    twilio_content_sid: t.twilio_content_sid || '',
    buttons: (t.buttons || []).map((b) => ({ button_type: b.type, button_text: b.text, button_value: b.value || '' })),
    samples: parseSamples(t.variables_sample),
  }
  error.value = null
  showForm.value = true
}

async function save() {
  saving.value = true
  error.value = null
  try {
    const { samples, ...fields } = form.value
    const keys = new Set(sampleInputs.value.map((i) => i.key))
    await call('whatsnext.whatsnext.api.save_template', {
      data: {
        ...fields,
        name: editingName.value || undefined,
        variables_sample: Object.fromEntries(Object.entries(samples || {}).filter(([k]) => keys.has(k))),
      },
    })
    showForm.value = false
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function syncFromMeta() {
  syncing.value = true
  syncResult.value = null
  error.value = null
  try {
    const res = await call('whatsnext.whatsnext.api.sync_templates_from_meta', {})
    syncResult.value = res
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    syncing.value = false
  }
}

function statusTone(status) {
  return { Approved: 'delivered', Pending: 'pending', Rejected: 'failed', Draft: 'pending' }[status] || 'pending'
}
</script>

<template>
  <div class="wn-templates">
    <div class="wn-toolbar">
      <p class="wn-muted">Manage WhatsApp message templates for Meta and Twilio.</p>
      <input v-model="search" type="text" class="wn-template-search" placeholder="Search templates by name or content" />
      <div class="wn-toolbar-actions">
        <button class="ghost" :disabled="syncing" @click="syncFromMeta">{{ syncing ? 'Syncing…' : 'Sync from Meta' }}</button>
        <button class="primary" @click="openNew">+ New Template</button>
      </div>
    </div>
    <p v-if="submitResult" class="wn-sync-result">{{ submitResult }}</p>
    <p v-if="error && !showForm" class="wn-error">{{ error }}</p>
    <p v-if="syncResult" class="wn-sync-result">
      Synced from Meta: {{ syncResult.created }} new, {{ syncResult.updated }} updated ({{ syncResult.total_fetched }} total on Meta).
    </p>

    <div class="wn-template-grid">
      <p v-if="!filteredTemplates.length" class="wn-muted">No templates match your search.</p>
      <div v-for="t in filteredTemplates" :key="t.name" class="wn-card wn-template-card" @click="openEdit(t)">
        <div class="wn-template-top">
          <strong>{{ t.template_name }}</strong>
          <span class="wn-status" :class="statusTone(t.approval_status)">{{ t.approval_status }}</span>
        </div>
        <div class="wn-template-meta">{{ t.provider }} · {{ t.language }} · {{ t.category }}</div>
        <p class="wn-template-body">{{ t.body }}</p>
        <div class="wn-template-ids">
          <span v-if="['Meta','Both'].includes(t.provider)" :class="{ 'wn-id-missing': !t.meta_template_id }">
            Meta: {{ t.meta_template_id || 'not synced' }}
          </span>
          <span v-if="['Twilio','Both'].includes(t.provider)" :class="{ 'wn-id-missing': !t.twilio_content_sid }">
            Twilio SID: {{ t.twilio_content_sid || 'not set' }}
          </span>
        </div>
        <p v-if="t.approval_status === 'Rejected' && t.rejection_reason" class="wn-reject">Rejected: {{ t.rejection_reason }}</p>
        <button v-if="canSubmitToMeta(t)" class="ghost small" :disabled="submitting === t.name" @click.stop="submitToMeta(t)">
          {{ submitting === t.name ? 'Submitting…' : (t.meta_template_id ? 'Resubmit to Meta' : 'Submit to Meta') }}
        </button>
      </div>
      <p v-if="!loading && !templates.length" class="wn-muted">No templates yet — create your first one.</p>
    </div>

    <div v-if="showForm" class="wn-modal-backdrop" @click.self="showForm = false">
      <div class="wn-modal">
        <h3>{{ editingName ? `Edit "${editingName}"` : 'New Template' }}</h3>
        <label>Template Name (unique, lowercase_underscore)</label>
        <input v-model="form.template_name" :disabled="!!editingName" placeholder="order_confirmation" />

        <div class="wn-row">
          <div>
            <label>Provider</label>
            <select v-model="form.provider">
              <option>Both</option>
              <option>Meta</option>
              <option>Twilio</option>
            </select>
          </div>
          <div>
            <label>Category</label>
            <select v-model="form.category">
              <option>Utility</option>
              <option>Marketing</option>
              <option>Authentication</option>
            </select>
          </div>
          <div>
            <label>Language</label>
            <input v-model="form.language" />
          </div>
        </div>

        <div class="wn-flex">
          <div>
            <label>Header</label>
            <select v-model="form.header_type">
              <option>None</option>
              <option>Text</option>
              <option>Image</option>
              <option>Video</option>
              <option>Document</option>
            </select>
          </div>
          <div v-if="form.header_type === 'Text'" class="wn-grow">
            <label>Header text (may use <code v-pre>{{1}}</code>)</label>
            <input v-model="form.header_text" />
          </div>
          <div v-else-if="form.header_type !== 'None'" class="wn-grow">
            <label>Example {{ form.header_type.toLowerCase() }} URL (sent for review, and the default at send time)</label>
            <input v-model="form.header_example_url" placeholder="https://example.com/sample.jpg" />
          </div>
        </div>

        <label>Body — use <code v-pre>{{1}}</code>, <code v-pre>{{2}}</code> for variables</label>
        <textarea v-model="form.body" rows="4" placeholder="Hi {1}, your order {2} has shipped."></textarea>

        <template v-if="sampleInputs.length">
          <label>Example values (Meta requires one per variable for review)</label>
          <div class="wn-flex wn-wrap">
            <input v-for="i in sampleInputs" :key="i.key" v-model="form.samples[i.key]" :placeholder="i.label" />
          </div>
        </template>

        <label>Footer (optional)</label>
        <input v-model="form.footer_text" />

        <label>Buttons (optional)</label>
        <div v-for="(b, idx) in form.buttons" :key="idx" class="wn-flex wn-btn-row">
          <select v-model="b.button_type">
            <option>Quick Reply</option>
            <option>URL</option>
            <option>Phone Number</option>
          </select>
          <input v-model="b.button_text" placeholder="Button text" />
          <input v-if="b.button_type !== 'Quick Reply'" v-model="b.button_value"
                 :placeholder="b.button_type === 'URL' ? 'https://example.com/track/{{1}}' : '+919876543210'" />
          <button class="ghost small danger" type="button" @click="form.buttons.splice(idx, 1)">✕</button>
        </div>
        <button v-if="form.buttons.length < 10" class="ghost small" type="button" @click="addButton">+ Add button</button>

        <template v-if="needsTwilioSid">
          <label>
            Twilio Content SID
            <span class="wn-hint-inline">— from Twilio Console → Content Editor, starts with "HX"</span>
          </label>
          <input v-model="form.twilio_content_sid" placeholder="HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" />
        </template>

        <p v-if="['Meta','Both'].includes(form.provider)" class="wn-hint">
          After saving, use “Submit to Meta” on the template card to send it for review. Changing an
          approved template's text sets it back to Draft until you resubmit.
        </p>

        <p v-if="error" class="wn-error">{{ error }}</p>

        <div class="wn-modal-actions">
          <button class="ghost" @click="showForm = false">Cancel</button>
          <button class="primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save Template' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-templates { display: flex; flex-direction: column; gap: 16px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.wn-toolbar-actions { display: flex; gap: 10px; flex-shrink: 0; }
.wn-template-search { flex: 1; min-width: 220px; max-width: 360px; padding: 9px 12px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-sync-result { font-size: 12.5px; color: var(--wn-teal); margin: -6px 0 0; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }
button.primary { background: var(--wn-teal); color: white; border: none; padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 13px; }
button.ghost { background: white; border: 1px solid var(--wn-border); padding: 10px 16px; border-radius: 10px; font-size: 13px; }
.wn-template-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 16px; cursor: pointer; }
.wn-card:hover { box-shadow: 0 2px 8px rgba(15,61,62,0.12); }
.wn-template-top { display: flex; justify-content: space-between; align-items: center; }
.wn-template-meta { font-size: 11.5px; color: var(--wn-text-muted); margin: 6px 0; }
.wn-template-body { font-size: 13px; margin: 8px 0 0; white-space: pre-wrap; }
.wn-template-ids { display: flex; flex-direction: column; gap: 2px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--wn-border); font-size: 11px; color: var(--wn-text-muted); }
.wn-id-missing { color: var(--wn-amber); }
.wn-status { font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: #eef2f2; }
.wn-status.delivered { background: #e6f7f4; color: var(--wn-teal); }
.wn-status.failed { background: #fee2e2; color: var(--wn-red); }
.wn-status.pending { background: #fef3c7; color: var(--wn-amber); }

.wn-modal-backdrop { position: fixed; inset: 0; background: rgba(15,61,62,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.wn-modal { background: white; border-radius: 14px; padding: 24px; width: 480px; max-width: 92vw; max-height: 88vh; overflow-y: auto; }
.wn-modal h3 { margin-top: 0; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 12px 0 4px; }
.wn-modal input, .wn-modal select, .wn-modal textarea { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; font-family: inherit; }
.wn-modal input:disabled { background: var(--wn-bg); color: var(--wn-text-muted); }
.wn-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.wn-hint-inline { font-weight: 400; color: var(--wn-text-muted); text-transform: none; }
.wn-hint { font-size: 11.5px; color: var(--wn-text-muted); margin-top: 10px; line-height: 1.5; }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.wn-error { color: var(--wn-red); font-size: 12.5px; }
.wn-flex { display: flex; gap: 10px; }
.wn-flex > * { min-width: 0; }
.wn-grow { flex: 2; }
.wn-wrap > input { flex: 1 1 140px; }
.wn-wrap { flex-wrap: wrap; }
.wn-btn-row { align-items: center; margin-bottom: 6px; }
.wn-btn-row select { flex: 0 0 130px; }
.wn-reject { font-size: 12px; color: var(--wn-red); margin: 6px 0; }
.wn-error { color: var(--wn-red); font-size: 13px; }
</style>
