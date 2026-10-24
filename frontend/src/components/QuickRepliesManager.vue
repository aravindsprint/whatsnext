<script setup>
import { onMounted, ref } from 'vue'
import { call } from '@/api/frappe'

const API = 'whatsnext.whatsnext.api'
const replies = ref([])
const editing = ref(null) // null | { name?, title, shortcut, message }
const saving = ref(false)
const error = ref(null)

async function load() {
  replies.value = await call(`${API}.list_quick_replies`, {}, 'GET')
}
onMounted(load)

function startNew() {
  editing.value = { name: null, title: '', shortcut: '', message: '' }
  error.value = null
}
function startEdit(r) {
  editing.value = { ...r }
  error.value = null
}

async function save() {
  const e = editing.value
  if (!e.title.trim() || !e.message.trim()) {
    error.value = 'Title and message are required.'
    return
  }
  saving.value = true
  error.value = null
  try {
    await call(`${API}.save_quick_reply`, { name: e.name || undefined, title: e.title.trim(), shortcut: e.shortcut, message: e.message })
    editing.value = null
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function remove(r) {
  if (!confirm(`Delete quick reply "${r.title}"?`)) return
  await call(`${API}.delete_quick_reply`, { name: r.name })
  await load()
}
</script>

<template>
  <div class="wn-card">
    <div class="wn-card-top">
      <h3>Quick Replies</h3>
      <button v-if="!editing" class="ghost small" @click="startNew">+ Add</button>
    </div>
    <p class="wn-hint">
      Saved answers for the chat composer — tap ⚡ or type <code>/</code> and the shortcut.
      <code>{name}</code> becomes the customer's first name. Shared with the whole team.
    </p>

    <div v-if="editing" class="wn-qr-form">
      <div class="wn-qr-row">
        <input v-model="editing.title" :disabled="!!editing.name" placeholder="Title, e.g. Thanks" />
        <input v-model="editing.shortcut" placeholder="Shortcut, e.g. thanks" />
      </div>
      <textarea v-model="editing.message" rows="3" placeholder="Thanks {name}! We'll get back to you shortly."></textarea>
      <p v-if="error" class="wn-error">{{ error }}</p>
      <div class="wn-qr-actions">
        <button class="ghost small" @click="editing = null">Cancel</button>
        <button class="primary small" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      </div>
    </div>

    <div v-for="r in replies" :key="r.name" class="wn-qr-line">
      <div class="wn-qr-main" @click="startEdit(r)">
        <strong>{{ r.title }}</strong>
        <span v-if="r.shortcut" class="wn-qr-short">/{{ r.shortcut }}</span>
        <div class="wn-qr-msg">{{ r.message }}</div>
      </div>
      <button class="ghost small danger" @click="remove(r)">Delete</button>
    </div>
    <p v-if="!replies.length && !editing" class="wn-hint">No quick replies yet.</p>
  </div>
</template>

<style scoped>
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 20px; }
.wn-card-top { display: flex; justify-content: space-between; align-items: center; }
.wn-card h3 { margin: 0 0 12px; font-size: 15px; }
.wn-hint { font-size: 12px; color: var(--wn-text-muted); }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-qr-form { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.wn-qr-row { display: flex; gap: 8px; }
.wn-qr-row input { flex: 1; min-width: 0; }
.wn-qr-form input, .wn-qr-form textarea { padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; font-family: inherit; box-sizing: border-box; width: 100%; }
.wn-qr-actions { display: flex; justify-content: flex-end; gap: 8px; }
.wn-qr-line { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-top: 1px solid var(--wn-border); }
.wn-qr-main { flex: 1; min-width: 0; cursor: pointer; font-size: 13px; }
.wn-qr-short { margin-left: 6px; color: var(--wn-teal); font-size: 12px; }
.wn-qr-msg { color: var(--wn-text-muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
