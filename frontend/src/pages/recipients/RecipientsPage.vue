<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRecipientListsStore } from '@/stores/recipientLists'
import { parseRecipientsCsv, recipientsToCsv } from '@/lib/csv'

const store = useRecipientListsStore()
const showForm = ref(false)
const saving = ref(false)
const error = ref(null)
const editingListName = ref(null)

const form = ref({
  list_name: '',
  description: '',
  csvText: '',
})

const parsedRecipients = computed(() => parseRecipientsCsv(form.value.csvText))

onMounted(() => store.load())

function openNew() {
  editingListName.value = null
  form.value = { list_name: '', description: '', csvText: '' }
  error.value = null
  showForm.value = true
}

async function openEdit(listName) {
  error.value = null
  const doc = await store.get(listName)
  editingListName.value = listName
  form.value = {
    list_name: doc.list_name,
    description: doc.description || '',
    csvText: recipientsToCsv(doc.recipients),
  }
  showForm.value = true
}

async function onFileUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  form.value.csvText = await file.text()
}

async function save() {
  error.value = null
  if (!form.value.list_name) {
    error.value = 'List name is required.'
    return
  }
  const recipients = parsedRecipients.value
  if (!recipients.length) {
    error.value = 'Add at least one recipient.'
    return
  }
  saving.value = true
  try {
    await store.save(form.value.list_name, recipients, form.value.description)
    showForm.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function remove(listName) {
  if (!confirm(`Delete recipient list "${listName}"? This can't be undone.`)) return
  await store.remove(listName)
}
</script>

<template>
  <div class="wn-recipients">
    <div class="wn-toolbar">
      <p class="wn-muted">Save recipient groups once, then reuse them across campaigns.</p>
      <button class="primary" @click="openNew">+ New List</button>
    </div>

    <div class="wn-card">
      <table class="wn-table">
        <thead>
          <tr>
            <th>List Name</th>
            <th>Description</th>
            <th>Recipients</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in store.lists" :key="l.name">
            <td>{{ l.list_name }}</td>
            <td class="wn-muted">{{ l.description || '—' }}</td>
            <td>{{ l.recipient_count }}</td>
            <td class="wn-row-actions">
              <button class="ghost small" @click="openEdit(l.list_name)">Edit</button>
              <button class="ghost small danger" @click="remove(l.list_name)">Delete</button>
            </td>
          </tr>
          <tr v-if="!store.loading && !store.lists.length">
            <td colspan="4" class="wn-muted">No saved lists yet — create one to reuse across campaigns.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showForm" class="wn-modal-backdrop" @click.self="showForm = false">
      <div class="wn-modal">
        <h3>{{ editingListName ? `Edit "${editingListName}"` : 'New Recipient List' }}</h3>

        <label>List Name</label>
        <input v-model="form.list_name" :disabled="!!editingListName" placeholder="VIP Customers" />

        <label>Description (optional)</label>
        <input v-model="form.description" placeholder="Top-tier customers, Tirupur region" />

        <label>
          Recipients — paste CSV or upload a file. Optional header row:
          <code v-pre>name,phone,1,2</code> or <code v-pre>phone,1,2</code>. Numbered columns
          fill template variables <code v-pre>{{1}}</code>, <code v-pre>{{2}}</code>… when used in a campaign.
        </label>
        <textarea v-model="form.csvText" rows="8" placeholder="name,phone,1&#10;John Doe,+919876543210,INV-1001&#10;Priya S,+919812345678,INV-1002"></textarea>
        <input type="file" accept=".csv,text/csv" @change="onFileUpload" />

        <p class="wn-preview-count">{{ parsedRecipients.length }} recipient(s) parsed</p>
        <table v-if="parsedRecipients.length" class="wn-preview-table">
          <tbody>
            <tr v-for="(r, i) in parsedRecipients.slice(0, 6)" :key="i">
              <td>{{ r.contact_name || '—' }}</td>
              <td>{{ r.to_number }}</td>
              <td>{{ Object.values(r.parameters).join(', ') }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="parsedRecipients.length > 6" class="wn-muted">…and {{ parsedRecipients.length - 6 }} more</p>

        <p v-if="error" class="wn-error">{{ error }}</p>

        <div class="wn-modal-actions">
          <button class="ghost" @click="showForm = false">Cancel</button>
          <button class="primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save List' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-recipients { display: flex; flex-direction: column; gap: 16px; }
.wn-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }
button.primary { background: var(--wn-teal); color: white; border: none; padding: 10px 16px; border-radius: 10px; font-weight: 600; font-size: 13px; }
button.ghost { background: white; border: 1px solid var(--wn-border); padding: 8px 14px; border-radius: 8px; font-size: 12.5px; }
button.ghost.small { padding: 6px 12px; font-size: 12px; }
button.ghost.danger { color: var(--wn-red); border-color: #fecaca; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); overflow-x: auto; }
.wn-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.wn-table th { text-align: left; padding: 12px 14px; font-size: 11px; text-transform: uppercase; color: var(--wn-text-muted); border-bottom: 1px solid var(--wn-border); }
.wn-table td { padding: 10px 14px; border-bottom: 1px solid var(--wn-border); }
.wn-row-actions { display: flex; gap: 8px; }

.wn-modal-backdrop { position: fixed; inset: 0; background: rgba(15,61,62,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.wn-modal { background: white; border-radius: 14px; padding: 24px; width: 560px; max-width: 92vw; max-height: 88vh; overflow-y: auto; }
.wn-modal h3 { margin-top: 0; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 12px 0 4px; line-height: 1.5; }
.wn-modal input, .wn-modal textarea { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; font-family: inherit; }
.wn-modal input:disabled { background: var(--wn-bg); color: var(--wn-text-muted); }
.wn-modal textarea { font-family: ui-monospace, monospace; font-size: 12px; }
.wn-preview-count { font-size: 12px; color: var(--wn-teal); font-weight: 600; margin-top: 10px; }
.wn-preview-table { width: 100%; font-size: 12px; margin-top: 6px; }
.wn-preview-table td { padding: 4px 6px; border-bottom: 1px solid var(--wn-border); }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }
</style>
