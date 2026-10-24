<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { call } from '@/api/frappe'
import { useAuthStore } from '@/stores/auth'
import { parseFrappeDate } from '@/lib/date'

// Event-driven WhatsApp messages (e.g. "send the invoice PDF when a Sales
// Invoice is submitted") — previously only configurable from Desk.
const API = 'whatsnext.whatsnext.api'
const auth = useAuthStore()

const list = ref([])
const loading = ref(false)
const templates = ref([])
const watched = ref([])
const showForm = ref(false)
const saving = ref(false)
const error = ref(null)
const doctypeFields = ref([])
const printFormats = ref([])
const isSubmittable = ref(false)
const doctypeMatches = ref([])

const EVENTS = ['After Insert', 'On Submit', 'On Update', 'On Change', 'Scheduled']

const blank = () => ({
  name: null,
  notification_name: '',
  enabled: 1,
  event: 'After Insert',
  reference_doctype: '',
  recipient_number_field: '',
  fixed_number: '',
  template: '',
  provider: '',
  attach_document_print: 0,
  print_format: '',
  condition: '',
  field_mapping: [],
})
const form = ref(blank())

const selectedTemplate = computed(() => templates.value.find((t) => t.name === form.value.template))
const isWatched = computed(() => watched.value.includes(form.value.reference_doctype))
const availableEvents = computed(() => {
  if (!form.value.reference_doctype || isWatched.value) {
    return EVENTS.filter((e) => e !== 'On Submit' || isSubmittable.value || !form.value.reference_doctype)
  }
  return ['Scheduled']
})
const templateVarCount = computed(() => {
  const nums = [...(selectedTemplate.value?.body || '').matchAll(/\{\{(\d+)\}\}/g)].map((m) => parseInt(m[1], 10))
  return nums.length ? Math.max(...nums) : 0
})
const phoneFields = computed(() =>
  doctypeFields.value.filter((f) => ['Data', 'Phone', 'Link', 'Dynamic Link', 'Small Text'].includes(f.fieldtype))
)

async function load() {
  loading.value = true
  try {
    list.value = await call(`${API}.list_notifications`, {}, 'GET')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (!auth.loaded) await auth.loadWhoAmI()
  if (!auth.isSystemManager) return
  load()
  templates.value = await call(`${API}.get_templates`, {}, 'GET')
  watched.value = (await call(`${API}.get_notification_options`, {}, 'GET')).watched_doctypes
})

async function loadDoctypeMeta(doctype) {
  doctypeFields.value = []
  printFormats.value = []
  isSubmittable.value = false
  if (!doctype) return
  try {
    const res = await call(`${API}.get_notification_options`, { doctype }, 'GET')
    doctypeFields.value = res.fields || []
    printFormats.value = res.print_formats || []
    isSubmittable.value = !!res.is_submittable
  } catch (e) {
    error.value = e.message
  }
}

watch(() => form.value.reference_doctype, (dt) => {
  loadDoctypeMeta(dt)
  if (dt && !availableEvents.value.includes(form.value.event)) form.value.event = availableEvents.value[0]
})

// Keep one mapping row per template variable.
watch(templateVarCount, (n) => {
  const rows = form.value.field_mapping
  for (let i = 1; i <= n; i++) {
    if (!rows.some((r) => String(r.template_variable) === String(i))) {
      rows.push({ template_variable: String(i), source_fieldname: '', static_value: '' })
    }
  }
  rows.sort((a, b) => Number(a.template_variable) - Number(b.template_variable))
})

let dtTimer
function onDoctypeInput(e) {
  const txt = e.target.value
  form.value.reference_doctype = txt
  clearTimeout(dtTimer)
  dtTimer = setTimeout(async () => {
    doctypeMatches.value = txt ? await call(`${API}.search_doctypes`, { txt }, 'GET') : []
  }, 250)
}
function pickDoctype(dt) {
  form.value.reference_doctype = dt
  doctypeMatches.value = []
}

function openNew() {
  form.value = blank()
  error.value = null
  showForm.value = true
}

async function openEdit(row) {
  error.value = null
  form.value = { ...blank(), ...(await call(`${API}.get_notification`, { name: row.name }, 'GET')) }
  form.value.field_mapping = form.value.field_mapping || []
  showForm.value = true
}

async function save() {
  error.value = null
  if (!form.value.notification_name || !form.value.reference_doctype || !form.value.template) {
    error.value = 'Name, document type and template are required.'
    return
  }
  if (!form.value.recipient_number_field && !form.value.fixed_number) {
    error.value = 'Choose the field holding the customer’s number, or a fixed number.'
    return
  }
  saving.value = true
  try {
    await call(`${API}.save_notification`, { data: form.value })
    showForm.value = false
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row) {
  const data = await call(`${API}.get_notification`, { name: row.name }, 'GET')
  data.enabled = row.enabled ? 0 : 1
  try {
    await call(`${API}.save_notification`, { data })
  } catch (e) {
    error.value = e.message
  }
  await load()
}

async function remove(row) {
  if (!confirm(`Delete notification "${row.notification_name}"?`)) return
  await call(`${API}.delete_notification`, { name: row.name })
  await load()
}
</script>

<template>
  <div class="wn-notifs">
    <div v-if="auth.loaded && !auth.isSystemManager" class="wn-card wn-muted">
      Only System Managers can set up automatic notifications.
    </div>
    <template v-else>
      <div class="wn-toolbar">
        <p class="wn-muted">Send a WhatsApp template automatically when a document is created, submitted or changed.</p>
        <button class="primary" @click="openNew">+ New Notification</button>
      </div>
      <p v-if="error && !showForm" class="wn-error">{{ error }}</p>

      <div class="wn-card">
        <table class="wn-table">
          <thead>
            <tr><th>Name</th><th>Document</th><th>Event</th><th>Template</th><th>Enabled</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="n in list" :key="n.name">
              <td><a href="#" @click.prevent="openEdit(n)">{{ n.notification_name }}</a></td>
              <td>{{ n.reference_doctype }}</td>
              <td>
                {{ n.event }}
                <div v-if="n.event === 'Scheduled' && n.last_polled" class="wn-muted-small">checked {{ parseFrappeDate(n.last_polled).toLocaleTimeString() }}</div>
              </td>
              <td>{{ n.template }}</td>
              <td><input type="checkbox" :checked="!!n.enabled" @change="toggleEnabled(n)" /></td>
              <td><button class="ghost small danger" @click="remove(n)">Delete</button></td>
            </tr>
            <tr v-if="!loading && !list.length"><td colspan="6" class="wn-muted">No notifications yet.</td></tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-if="showForm" class="wn-modal-backdrop" @click.self="showForm = false">
      <div class="wn-modal">
        <h3>{{ form.name ? `Edit "${form.name}"` : 'New Notification' }}</h3>

        <label>Name</label>
        <input v-model="form.notification_name" :disabled="!!form.name" placeholder="Invoice submitted" />

        <label>Document type</label>
        <div class="wn-autocomplete">
          <input :value="form.reference_doctype" placeholder="Sales Invoice" @input="onDoctypeInput" />
          <div v-if="doctypeMatches.length" class="wn-ac-list">
            <button v-for="d in doctypeMatches" :key="d" type="button" @click="pickDoctype(d)">
              {{ d }} <span v-if="watched.includes(d)" class="wn-badge green">instant</span>
            </button>
          </div>
        </div>
        <p v-if="form.reference_doctype && !isWatched" class="wn-muted-small">
          This type isn't wired for instant events, so it's checked for changes every 5 minutes ("Scheduled").
        </p>

        <div class="wn-flex">
          <div>
            <label>When</label>
            <select v-model="form.event">
              <option v-for="e in availableEvents" :key="e">{{ e }}</option>
            </select>
          </div>
          <div>
            <label>Template</label>
            <select v-model="form.template">
              <option value="" disabled>Select…</option>
              <option v-for="t in templates" :key="t.name" :value="t.name">{{ t.template_name }}{{ t.approval_status !== 'Approved' ? ` (${t.approval_status})` : '' }}</option>
            </select>
          </div>
          <div v-if="auth.providers.length > 1">
            <label>Send via</label>
            <select v-model="form.provider">
              <option value="">Default</option>
              <option v-for="p in auth.providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
        </div>

        <div class="wn-flex">
          <div>
            <label>Customer number field</label>
            <select v-model="form.recipient_number_field">
              <option value="">— none —</option>
              <option v-for="f in phoneFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }} ({{ f.fieldname }})</option>
            </select>
          </div>
          <div>
            <label>…or a fixed number</label>
            <input v-model="form.fixed_number" placeholder="919876543210" />
          </div>
        </div>
        <p class="wn-muted-small">If the field is empty, the linked Contact Person's mobile is used.</p>

        <template v-if="form.field_mapping.length">
          <label>Template variables</label>
          <div v-for="row in form.field_mapping" :key="row.template_variable" class="wn-flex wn-map-row">
            <span class="wn-var" v-text="'{{' + row.template_variable + '}}'"></span>
            <select v-model="row.source_fieldname">
              <option value="">Fixed text →</option>
              <option v-for="f in doctypeFields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</option>
            </select>
            <input v-model="row.static_value" :placeholder="row.source_fieldname ? 'Fallback if empty' : 'Text'" />
          </div>
        </template>

        <template v-if="selectedTemplate?.header_type === 'Document'">
          <label class="wn-check"><input v-model="form.attach_document_print" type="checkbox" :true-value="1" :false-value="0" /> Attach the document as a PDF</label>
          <select v-if="form.attach_document_print" v-model="form.print_format">
            <option value="">Default print format</option>
            <option v-for="p in printFormats" :key="p">{{ p }}</option>
          </select>
        </template>

        <label>Condition (optional Python expression)</label>
        <input v-model="form.condition" placeholder="doc.grand_total > 1000" />

        <label class="wn-check"><input v-model="form.enabled" type="checkbox" :true-value="1" :false-value="0" /> Enabled</label>

        <p v-if="error" class="wn-error">{{ error }}</p>
        <div class="wn-modal-actions">
          <button class="ghost" @click="showForm = false">Cancel</button>
          <button class="primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-notifs { display: flex; flex-direction: column; gap: 16px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 16px; overflow-x: auto; }
.wn-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.wn-table th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--wn-text-muted); padding: 8px; border-bottom: 1px solid var(--wn-border); }
.wn-table td { padding: 10px 8px; border-bottom: 1px solid var(--wn-border); }
.wn-table a { color: var(--wn-teal); font-weight: 600; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }
.wn-muted-small { font-size: 11.5px; color: var(--wn-text-muted); margin: 4px 0 0; }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-modal-backdrop { position: fixed; inset: 0; background: rgba(15,61,62,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.wn-modal { background: white; border-radius: 14px; padding: 24px; width: 560px; max-width: 94vw; max-height: 90vh; overflow-y: auto; }
.wn-modal h3 { margin-top: 0; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 12px 0 4px; }
.wn-modal input:not([type="checkbox"]), .wn-modal select { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; box-sizing: border-box; }
.wn-flex { display: flex; gap: 10px; }
.wn-flex > * { flex: 1; min-width: 0; }
.wn-map-row { align-items: center; margin-bottom: 6px; }
.wn-var { flex: 0 0 44px !important; font-family: monospace; font-size: 12px; color: var(--wn-text-muted); }
.wn-check { display: flex !important; align-items: center; gap: 6px; }
.wn-autocomplete { position: relative; }
.wn-ac-list { position: absolute; left: 0; right: 0; top: 100%; background: white; border: 1px solid var(--wn-border); border-radius: 8px; z-index: 5; max-height: 200px; overflow-y: auto; }
.wn-ac-list button { display: block; width: 100%; text-align: left; background: none; border: none; padding: 8px 10px; font-size: 13px; }
.wn-ac-list button:hover { background: var(--wn-bg); }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
@media (max-width: 600px) { .wn-flex { flex-direction: column; gap: 0; } }
</style>
