<script setup>
import { onMounted, ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { call } from '@/api/frappe'
import ConversationList from '@/components/ConversationList.vue'
import MessageBubble from '@/components/MessageBubble.vue'

const chat = useChatStore()
const draft = ref('')
const messagesEl = ref(null)
const showContactInfo = ref(false)
const showMediaPanel = ref(false)
const mediaTab = ref('media')
const mediaData = ref({ media: [], docs: [], audio: [] })
const mediaLoading = ref(false)

async function openMediaPanel() {
  showMediaPanel.value = true
  showContactInfo.value = false
  mediaTab.value = 'media'
  if (!activeConversation.value) return
  mediaLoading.value = true
  try {
    const convId = activeConversation.value.conversation_id || activeConversation.value.name
    mediaData.value = await call('whatsnext.whatsnext.api.get_conversation_media', { conversation_id: convId }, 'GET')
  } finally {
    mediaLoading.value = false
  }
}

// --- Emoji picker -----------------------------------------------------
const showEmojiPicker = ref(false)
const commonEmojis = ['😀','😁','😂','🤣','😊','😍','😘','😉','😎','🤔','😢','😡','👍','👎','🙏','👏','💪','🔥','✅','❌','⭐','🎉','❤️','💡','📌','⏰','📅','✨','🙌','👋']
function insertEmoji(e) {
  draft.value += e
  showEmojiPicker.value = false
}

// --- File attach --------------------------------------------------------
const fileInputEl = ref(null)
const attachSending = ref(false)
const attachError = ref(null)

function triggerFilePicker() {
  fileInputEl.value?.click()
}

function mediaTypeFromMime(mime) {
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  return 'document'
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file || !activeConversation.value) return

  attachSending.value = true
  attachError.value = null
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('is_private', '0')
    const res = await fetch('/api/method/upload_file', {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Frappe-CSRF-Token': window.csrf_token || '' },
      body: formData,
    })
    if (!res.ok) throw new Error('Upload failed')
    const data = await res.json()
    const fileUrl = window.location.origin + data.message.file_url

    const to = activeConversation.value.to_number || activeConversation.value.from_number
    const mediaType = mediaTypeFromMime(file.type)
    await chat.sendMedia(to, fileUrl, mediaType, '')
    scrollToBottom()
  } catch (err) {
    attachError.value = err.message
  } finally {
    attachSending.value = false
  }
}

// --- Template picker (send a template mid-conversation) --------------
const showTplPicker = ref(false)
const tplList = ref([])
const tplSelected = ref(null)
const tplVariables = ref([])
const tplHeaderMediaUrl = ref('')
const tplSending = ref(false)
const tplError = ref(null)

const tplNeedsHeaderMedia = computed(() =>
  tplSelected.value && !['None', 'Text'].includes(tplSelected.value.header_type)
)

async function openTplPicker() {
  showTplPicker.value = true
  tplSelected.value = null
  tplError.value = null
  try {
    tplList.value = await call('whatsnext.whatsnext.api.get_templates', { approved_only: true }, 'GET')
  } catch (e) {
    tplError.value = e.message
  }
}

function pickTplForSend(tpl) {
  tplSelected.value = tpl
  const matches = [...(tpl.body || '').matchAll(/\{\{(\d+)\}\}/g)]
  const count = matches.length ? Math.max(...matches.map((m) => parseInt(m[1], 10))) : 0
  tplVariables.value = Array.from({ length: count }, () => '')
  tplHeaderMediaUrl.value = tpl.header_example_url || ''
}

async function sendTplToActiveConversation() {
  if (!tplSelected.value || !activeConversation.value) return
  if (tplNeedsHeaderMedia.value && !tplHeaderMediaUrl.value.trim()) {
    tplError.value = `This template has a ${tplSelected.value.header_type} header — a media URL is required.`
    return
  }
  tplSending.value = true
  tplError.value = null
  try {
    const params = {}
    tplVariables.value.forEach((v, i) => { params[i + 1] = v })
    const to = activeConversation.value.to_number || activeConversation.value.from_number
    await chat.sendTemplate(to, tplSelected.value.name, params, null, null, tplHeaderMediaUrl.value || undefined)
    showTplPicker.value = false
    scrollToBottom()
  } catch (e) {
    tplError.value = e.message
  } finally {
    tplSending.value = false
  }
}

onMounted(() => {
  chat.loadConversations()
  chat.loadStats()
})

let searchDebounceTimer
function onSearchInput(e) {
  clearTimeout(searchDebounceTimer)
  const value = e.target.value
  searchDebounceTimer = setTimeout(() => chat.setSearch(value), 300)
}

function setFilterTab(tab) {
  chat.setFilter(tab)
}

const activeConversation = computed(() =>
  chat.conversations.find((c) => (c.conversation_id || c.name) === chat.activeConversationId)
)

async function selectConversation(id) {
  await chat.openConversation(id)
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

watch(() => chat.activeMessages.length, scrollToBottom)

async function send() {
  const text = draft.value.trim()
  if (!text || !activeConversation.value) return
  draft.value = ''
  const to = activeConversation.value.to_number || activeConversation.value.from_number
  await chat.sendText(to, text, activeConversation.value.reference_doctype, activeConversation.value.reference_name)
}

// --- New Chat flow ---------------------------------------------------
const showNewChat = ref(false)
const ncStep = ref('contact') // 'contact' | 'template'
const ncSearch = ref('')
const ncContacts = ref([])
const ncLoadingContacts = ref(false)
const ncSelectedContact = ref(null)
const ncTemplates = ref([])
const ncSelectedTemplate = ref(null)
const ncVariables = ref([])
const ncHeaderMediaUrl = ref('')
const ncSending = ref(false)
const ncError = ref(null)

function openNewChat() {
  showNewChat.value = true
  ncStep.value = 'contact'
  ncSearch.value = ''
  ncSelectedContact.value = null
  ncSelectedTemplate.value = null
  ncError.value = null
  searchContacts()
}

async function searchContacts() {
  ncLoadingContacts.value = true
  try {
    ncContacts.value = await call('whatsnext.whatsnext.api.get_selectable_contacts', { search: ncSearch.value || undefined }, 'GET')
  } catch (e) {
    ncError.value = e.message
  } finally {
    ncLoadingContacts.value = false
  }
}

let searchDebounce
watch(ncSearch, () => {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(searchContacts, 300)
})

async function pickContact(contact) {
  ncSelectedContact.value = contact
  ncError.value = null
  try {
    ncTemplates.value = await call('whatsnext.whatsnext.api.get_templates', { approved_only: true }, 'GET')
  } catch (e) {
    ncError.value = e.message
  }
  ncStep.value = 'template'
}

const ncNeedsHeaderMedia = computed(() =>
  ncSelectedTemplate.value && !['None', 'Text'].includes(ncSelectedTemplate.value.header_type)
)

function pickTemplate(tpl) {
  ncSelectedTemplate.value = tpl
  const matches = [...(tpl.body || '').matchAll(/\{\{(\d+)\}\}/g)]
  const count = matches.length ? Math.max(...matches.map((m) => parseInt(m[1], 10))) : 0
  ncVariables.value = Array.from({ length: count }, () => '')
  ncHeaderMediaUrl.value = tpl.header_example_url || ''
}

async function sendNewChat() {
  if (!ncSelectedContact.value || !ncSelectedTemplate.value) return
  if (ncNeedsHeaderMedia.value && !ncHeaderMediaUrl.value.trim()) {
    ncError.value = `This template has a ${ncSelectedTemplate.value.header_type} header — a media URL is required.`
    return
  }
  ncSending.value = true
  ncError.value = null
  try {
    const params = {}
    ncVariables.value.forEach((v, i) => { params[i + 1] = v })
    const phone = ncSelectedContact.value.phone
    chat.activeConversationId = phone
    await chat.sendTemplate(phone, ncSelectedTemplate.value.name, params, null, null, ncHeaderMediaUrl.value || undefined)
    showNewChat.value = false
    await chat.loadConversations()
    await selectConversation(phone)
  } catch (e) {
    ncError.value = e.message
  } finally {
    ncSending.value = false
  }
}
</script>

<template>
  <div class="wn-chat-layout">
    <div class="wn-conv-pane">
      <div class="wn-conv-header">
        <button class="wn-new-chat-btn" @click="openNewChat">+ New Chat</button>
        <input class="wn-conv-search" type="text" placeholder="Search by name or number" @input="onSearchInput" />
        <div class="wn-stats-bar">
          <span class="wn-stat">Total <strong>{{ chat.stats.total }}</strong></span>
          <span class="wn-stat unread">Unread <strong>{{ chat.stats.unread }}</strong></span>
          <span class="wn-stat">Sent <strong>{{ chat.stats.sent }}</strong></span>
        </div>
        <div class="wn-filter-tabs">
          <button v-for="tab in ['all','unread','incoming','outgoing']" :key="tab"
                  :class="{ active: chat.filter === tab }" @click="setFilterTab(tab)">
            {{ tab.charAt(0).toUpperCase() + tab.slice(1) }}
          </button>
        </div>
      </div>
      <ConversationList
        :conversations="chat.conversations"
        :active-id="chat.activeConversationId"
        @select="selectConversation"
      />
    </div>

    <div class="wn-chat-pane">
      <template v-if="activeConversation">
        <div class="wn-chat-header">
          <div class="wn-avatar">{{ (activeConversation.profile_name || '?').charAt(0).toUpperCase() }}</div>
          <div class="wn-chat-header-name">
            <div class="wn-chat-name">{{ activeConversation.profile_name || activeConversation.to_number }}</div>
            <div class="wn-chat-phone">{{ activeConversation.to_number || activeConversation.from_number }}</div>
          </div>
          <button class="wn-info-btn" @click="showMediaPanel = false; showContactInfo = !showContactInfo" title="Contact info">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
          </button>
          <button class="wn-info-btn" @click="openMediaPanel" title="Media & Files">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
        </div>

        <div class="wn-messages" ref="messagesEl">
          <MessageBubble v-for="m in chat.activeMessages" :key="m.name" :message="m" />
          <div v-if="chat.loadingMessages" class="wn-loading">Loading…</div>
        </div>

        <p v-if="attachError" class="wn-error wn-composer-error">{{ attachError }}</p>
        <form class="wn-composer" @submit.prevent="send">
          <button type="button" class="wn-tpl-btn" @click="openTplPicker" title="Send a template">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z" />
              <rect x="5" y="4" width="14" height="18" rx="2" />
              <line x1="9" y1="11" x2="15" y2="11" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          </button>
          <div class="wn-emoji-wrap">
            <button type="button" class="wn-tpl-btn" @click="showEmojiPicker = !showEmojiPicker" title="Emoji">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 14s1.5 2 4 2 4-2 4-2" />
                <line x1="9" y1="9" x2="9.01" y2="9" />
                <line x1="15" y1="9" x2="15.01" y2="9" />
              </svg>
            </button>
            <div v-if="showEmojiPicker" class="wn-emoji-popup">
              <button v-for="e in commonEmojis" :key="e" type="button" @click="insertEmoji(e)">{{ e }}</button>
            </div>
          </div>
          <button type="button" class="wn-tpl-btn" @click="triggerFilePicker" :disabled="attachSending" title="Attach file">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <input ref="fileInputEl" type="file" class="wn-hidden-file-input" @change="onFileSelected" />
          <input v-model="draft" type="text" placeholder="Type a message" />
          <button type="submit">Send</button>
        </form>
      </template>

      <div v-else class="wn-chat-empty">
        <p>Select a conversation to start messaging</p>
      </div>
    </div>

    <div v-if="showContactInfo && activeConversation" class="wn-info-panel">
      <div class="wn-info-header">
        <span>Contact Info</span>
        <button @click="showContactInfo = false">✕</button>
      </div>
      <div class="wn-info-avatar">{{ (activeConversation.profile_name || '?').charAt(0).toUpperCase() }}</div>
      <div class="wn-info-name">{{ activeConversation.profile_name || activeConversation.to_number }}</div>
      <div class="wn-info-row">
        <span class="wn-info-label">Phone</span>
        <span>{{ activeConversation.to_number || activeConversation.from_number }}</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Customer</span>
        <span>{{ activeConversation.customer || '—' }}</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Last Message Type</span>
        <span>{{ activeConversation.type }}</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Last Message</span>
        <span>{{ new Date(activeConversation.modified).toLocaleString() }}</span>
      </div>
    </div>

    <div v-if="showMediaPanel && activeConversation" class="wn-info-panel">
      <div class="wn-info-header">
        <span>Media & Files</span>
        <button @click="showMediaPanel = false">✕</button>
      </div>
      <div class="wn-media-tabs">
        <button v-for="t in ['media','docs','audio']" :key="t" :class="{ active: mediaTab === t }" @click="mediaTab = t">
          {{ t.charAt(0).toUpperCase() + t.slice(1) }}
        </button>
      </div>
      <div v-if="mediaLoading" class="wn-muted">Loading…</div>
      <template v-else>
        <div v-if="mediaTab === 'media'" class="wn-media-grid">
          <img v-for="m in mediaData.media.filter(x => x.content_type === 'image')" :key="m.name" :src="m.attach" class="wn-media-thumb" />
          <a v-for="m in mediaData.media.filter(x => x.content_type === 'video')" :key="'v'+m.name" :href="m.attach" target="_blank" class="wn-media-thumb wn-media-video">🎬</a>
          <p v-if="!mediaData.media.length" class="wn-muted">No media shared yet</p>
        </div>
        <div v-if="mediaTab === 'docs'" class="wn-media-list">
          <a v-for="d in mediaData.docs" :key="d.name" :href="d.attach" target="_blank" class="wn-media-doc-item">📎 {{ (d.attach || '').split('/').pop() }}</a>
          <p v-if="!mediaData.docs.length" class="wn-muted">No documents shared yet</p>
        </div>
        <div v-if="mediaTab === 'audio'" class="wn-media-list">
          <audio v-for="a in mediaData.audio" :key="a.name" :src="a.attach" controls class="wn-media-audio" />
          <p v-if="!mediaData.audio.length" class="wn-muted">No audio shared yet</p>
        </div>
      </template>
    </div>

    <div v-if="showTplPicker" class="wn-modal-backdrop" @click.self="showTplPicker = false">
      <div class="wn-modal">
        <template v-if="!tplSelected">
          <h3>Send a Template</h3>
          <div class="wn-nc-list">
            <div v-for="t in tplList" :key="t.name" class="wn-nc-item wn-nc-template" @click="pickTplForSend(t)">
              <div class="wn-nc-item-name">{{ t.template_name }}</div>
              <div class="wn-nc-item-meta">{{ t.body }}</div>
            </div>
            <p v-if="!tplList.length" class="wn-muted">No approved templates available yet.</p>
          </div>
        </template>
        <template v-else>
          <h3>{{ tplSelected.template_name }}</h3>
          <p class="wn-nc-template-body">{{ tplSelected.body }}</p>
          <template v-if="tplNeedsHeaderMedia">
            <label>{{ tplSelected.header_type }} Header URL</label>
            <input v-model="tplHeaderMediaUrl" type="text" placeholder="https://example.com/image.jpg" />
          </template>
          <template v-if="tplVariables.length">
            <label v-for="(v, i) in tplVariables" :key="i">Variable {{ i + 1 }}</label>
            <input v-for="(v, i) in tplVariables" :key="'tv' + i" v-model="tplVariables[i]" type="text" />
          </template>
          <div class="wn-modal-actions">
            <button class="ghost" @click="tplSelected = null">Back</button>
            <button class="primary" :disabled="tplSending" @click="sendTplToActiveConversation">
              {{ tplSending ? 'Sending…' : 'Send' }}
            </button>
          </div>
        </template>
        <p v-if="tplError" class="wn-error">{{ tplError }}</p>
        <div class="wn-modal-actions" v-if="!tplSelected">
          <button class="ghost" @click="showTplPicker = false">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="showNewChat" class="wn-modal-backdrop" @click.self="showNewChat = false">
      <div class="wn-modal">
        <template v-if="ncStep === 'contact'">
          <h3>New Chat — choose a contact</h3>
          <input v-model="ncSearch" type="text" placeholder="Search by name, phone, or customer" class="wn-nc-search" />
          <div class="wn-nc-list">
            <div v-if="ncLoadingContacts" class="wn-muted">Loading…</div>
            <div
              v-for="c in ncContacts"
              :key="c.contact_name"
              class="wn-nc-item"
              @click="pickContact(c)"
            >
              <div class="wn-avatar">{{ (c.full_name || '?').charAt(0).toUpperCase() }}</div>
              <div class="wn-nc-item-body">
                <div class="wn-nc-item-name">{{ c.full_name || c.phone }}</div>
                <div class="wn-nc-item-meta">{{ c.customer }} · {{ c.phone }}</div>
              </div>
            </div>
            <p v-if="!ncLoadingContacts && !ncContacts.length" class="wn-muted">
              No contacts found — only contacts linked to a customer assigned to you are shown here.
            </p>
          </div>
        </template>

        <template v-else>
          <h3>New Chat — {{ ncSelectedContact.full_name || ncSelectedContact.phone }}</h3>
          <p class="wn-hint">
            WhatsApp requires an approved template to start a new conversation.
          </p>

          <div v-if="!ncSelectedTemplate" class="wn-nc-list">
            <div
              v-for="t in ncTemplates"
              :key="t.name"
              class="wn-nc-item wn-nc-template"
              @click="pickTemplate(t)"
            >
              <div class="wn-nc-item-name">{{ t.template_name }}</div>
              <div class="wn-nc-item-meta">{{ t.body }}</div>
            </div>
            <p v-if="!ncTemplates.length" class="wn-muted">No approved templates available yet.</p>
          </div>

          <template v-else>
            <p class="wn-nc-template-body">{{ ncSelectedTemplate.body }}</p>
            <template v-if="ncNeedsHeaderMedia">
              <label>{{ ncSelectedTemplate.header_type }} Header URL (public link required by WhatsApp)</label>
              <input v-model="ncHeaderMediaUrl" type="text" placeholder="https://example.com/image.jpg" />
              <p v-if="ncSelectedTemplate.header_example_url" class="wn-hint">
                Pre-filled from the template's approved example media — edit if you want a different image for this send.
              </p>
            </template>
            <template v-if="ncVariables.length">
              <label v-for="(v, i) in ncVariables" :key="i">Variable {{ i + 1 }}</label>
              <input v-for="(v, i) in ncVariables" :key="'in' + i" v-model="ncVariables[i]" type="text" />
            </template>
            <div class="wn-modal-actions">
              <button class="ghost" @click="ncSelectedTemplate = null">Back</button>
              <button class="primary" :disabled="ncSending" @click="sendNewChat">
                {{ ncSending ? 'Sending…' : 'Send' }}
              </button>
            </div>
          </template>
        </template>

        <p v-if="ncError" class="wn-error">{{ ncError }}</p>

        <div class="wn-modal-actions" v-if="ncStep === 'contact'">
          <button class="ghost" @click="showNewChat = false">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-chat-layout {
  display: flex;
  height: 100%;
  background: white;
  border-radius: var(--wn-radius);
  overflow: hidden;
  box-shadow: var(--wn-shadow);
  position: relative;
}
.wn-conv-pane { width: 320px; flex-shrink: 0; border-right: 1px solid var(--wn-border); display: flex; flex-direction: column; }
.wn-conv-header { padding: 10px 12px; border-bottom: 1px solid var(--wn-border); display: flex; flex-direction: column; gap: 8px; }
.wn-new-chat-btn { width: 100%; background: var(--wn-teal); color: white; border: none; padding: 9px; border-radius: 8px; font-weight: 600; font-size: 13px; }
.wn-conv-search { width: 100%; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 12.5px; }
.wn-stats-bar { display: flex; gap: 12px; font-size: 11px; color: var(--wn-text-muted); }
.wn-stat strong { color: var(--wn-text, #222); font-size: 12px; }
.wn-stat.unread strong { color: var(--wn-teal); }
.wn-filter-tabs { display: flex; gap: 4px; }
.wn-filter-tabs button { flex: 1; padding: 5px 0; border: none; background: var(--wn-bg); border-radius: 6px; font-size: 11px; color: var(--wn-text-muted); }
.wn-filter-tabs button.active { background: var(--wn-teal); color: white; font-weight: 600; }
.wn-chat-pane { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.wn-chat-header { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--wn-border); }
.wn-chat-header-name { flex: 1; min-width: 0; }
.wn-info-btn { background: none; border: none; color: var(--wn-text-muted); cursor: pointer; padding: 6px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; }
.wn-info-btn:hover { color: var(--wn-teal); }
.wn-info-panel { position: absolute; top: 0; right: 0; bottom: 0; width: 280px; background: white; box-shadow: -2px 0 8px rgba(0,0,0,0.08); padding: 16px; z-index: 40; overflow-y: auto; }
.wn-info-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
.wn-info-header button { background: none; border: none; font-size: 14px; color: var(--wn-text-muted); cursor: pointer; }
.wn-info-avatar { width: 64px; height: 64px; border-radius: 50%; background: var(--wn-navy); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 24px; margin: 0 auto 10px; }
.wn-info-name { text-align: center; font-weight: 600; font-size: 15px; margin-bottom: 16px; }
.wn-info-row { display: flex; flex-direction: column; gap: 2px; padding: 10px 0; border-top: 1px solid var(--wn-border); font-size: 13px; }
.wn-info-label { font-size: 11px; color: var(--wn-text-muted); font-weight: 600; text-transform: uppercase; }
.wn-media-tabs { display: flex; gap: 4px; margin-bottom: 14px; }
.wn-media-tabs button { flex: 1; padding: 6px 0; border: none; background: var(--wn-bg); border-radius: 6px; font-size: 11.5px; color: var(--wn-text-muted); }
.wn-media-tabs button.active { background: var(--wn-teal); color: white; font-weight: 600; }
.wn-media-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.wn-media-thumb { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: var(--wn-bg); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.wn-media-list { display: flex; flex-direction: column; gap: 8px; }
.wn-media-doc-item { font-size: 12.5px; color: var(--wn-blue); }
.wn-media-audio { width: 100%; }
.wn-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--wn-navy); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.wn-chat-name { font-weight: 600; font-size: 14px; }
.wn-chat-phone { font-size: 12px; color: var(--wn-text-muted); }
.wn-messages { flex: 1; overflow-y: auto; padding: 16px; background: var(--wn-bg); }
.wn-loading { text-align: center; font-size: 12px; color: var(--wn-text-muted); }
.wn-composer { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--wn-border); }
.wn-composer input { flex: 1; padding: 10px 14px; border-radius: 20px; border: 1px solid var(--wn-border); font-size: 14px; }
.wn-composer button { padding: 10px 18px; border-radius: 20px; border: none; background: var(--wn-teal); color: white; font-weight: 600; }
.wn-tpl-btn { background: var(--wn-bg) !important; color: var(--wn-text-muted) !important; padding: 8px 12px !important; border-radius: 20px !important; display: inline-flex; align-items: center; justify-content: center; }
.wn-tpl-btn:disabled { opacity: 0.5; }
.wn-hidden-file-input { display: none; }
.wn-composer-error { padding: 0 12px; margin: 0; }
.wn-emoji-wrap { position: relative; }
.wn-emoji-popup { position: absolute; bottom: 44px; left: 0; background: white; border-radius: 10px; box-shadow: var(--wn-shadow); padding: 8px; display: grid; grid-template-columns: repeat(6, 1fr); gap: 2px; z-index: 30; width: 220px; }
.wn-emoji-popup button { background: none; border: none; font-size: 18px; padding: 4px; border-radius: 6px; cursor: pointer; }
.wn-emoji-popup button:hover { background: var(--wn-bg); }
.wn-chat-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--wn-text-muted); }

.wn-modal-backdrop { position: fixed; inset: 0; background: rgba(15,61,62,0.4); display: flex; align-items: center; justify-content: center; z-index: 50; }
.wn-modal { background: white; border-radius: 14px; padding: 24px; width: 480px; max-width: 92vw; max-height: 88vh; overflow-y: auto; }
.wn-modal h3 { margin-top: 0; }
.wn-nc-search { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; margin-bottom: 10px; }
.wn-nc-list { display: flex; flex-direction: column; gap: 4px; max-height: 340px; overflow-y: auto; }
.wn-nc-item { display: flex; gap: 10px; align-items: center; padding: 8px; border-radius: 8px; cursor: pointer; }
.wn-nc-item:hover { background: var(--wn-bg); }
.wn-nc-item-body { min-width: 0; }
.wn-nc-item-name { font-weight: 600; font-size: 13.5px; }
.wn-nc-item-meta { font-size: 11.5px; color: var(--wn-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-nc-template { flex-direction: column; align-items: flex-start; }
.wn-nc-template-body { font-size: 13px; background: var(--wn-bg); padding: 10px; border-radius: 8px; white-space: pre-wrap; }
.wn-hint { font-size: 11.5px; color: var(--wn-text-muted); margin-top: -6px; margin-bottom: 12px; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 10px 0 4px; }
.wn-modal input[type="text"] { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
button.primary { background: var(--wn-teal); color: white; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 600; font-size: 13px; }
button.ghost { background: white; border: 1px solid var(--wn-border); padding: 10px 18px; border-radius: 8px; font-size: 13px; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; padding: 10px 0; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }

@media (max-width: 768px) {
  .wn-conv-pane { width: 100%; }
  .wn-chat-pane { display: none; }
}
</style>
