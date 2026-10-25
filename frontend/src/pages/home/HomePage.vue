<script setup>
import { onMounted, ref, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { call } from '@/api/frappe'
import { parseFrappeDate } from '@/lib/date'
import { toFrappeDatetime } from '@/lib/templateVars'
import ConversationList from '@/components/ConversationList.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import TemplateSendForm from '@/components/TemplateSendForm.vue'

const chat = useChatStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const draft = ref('')
const messagesEl = ref(null)
const showContactInfo = ref(false)
const showMediaPanel = ref(false)
const mediaTab = ref('media')
const mediaData = ref({ media: [], docs: [], audio: [] })
const mediaLoading = ref(false)
const composerError = ref(null)

const FILTER_TABS = [
  ['all', 'All'], ['unread', 'Unread'], ['mine', 'Mine'],
  ['incoming', 'In'], ['outgoing', 'Out'], ['closed', 'Closed'],
]

// --- Active conversation ---------------------------------------------
const activeConversation = computed(() =>
  chat.conversations.find((c) => (c.conversation_id || c.name) === chat.activeConversationId)
)
// conversation_id is always the counterpart's number (see
// Whatsnext Message.before_insert and the webhook handlers).
const activeConversationNumber = computed(() => chat.activeConversationId)
const info = computed(() => chat.activeInfo)
const displayName = computed(() =>
  activeConversation.value?.profile_name || info.value?.profile_name || activeConversationNumber.value
)

// Free-form messages are only allowed for 24h after the customer's last
// message; outside it WhatsApp accepts approved templates only.
const windowOpen = computed(() => {
  if (info.value) return !!info.value.window_open
  return !!activeConversation.value?.window_open
})
const windowLabel = computed(() => {
  const exp = info.value?.window_expires_at
  if (!windowOpen.value || !exp) return null
  const hours = Math.max(0, Math.round((parseFrappeDate(exp) - new Date()) / 3600000))
  return hours >= 1 ? `${hours}h left to reply` : 'under 1h left to reply'
})

function dateSeparatorLabel(dateStr) {
  const d = parseFrappeDate(dateStr)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  if (sameDay(d, today)) return 'Today'
  if (sameDay(d, yesterday)) return 'Yesterday'
  return d.toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' })
}

// Messages and internal notes in one timeline, by time. While older
// messages are still unloaded, notes older than the oldest loaded message
// wait for them, so they never appear out of context at the top.
const timelineItems = computed(() => {
  const messages = chat.activeMessages
  const oldest = messages[0]?.creation
  const notes = chat.activeNotes.filter((n) => !chat.activeHasOlder || !oldest || n.creation >= oldest)
  const entries = [
    ...messages.map((m) => ({ kind: 'message', at: m.creation, data: m })),
    ...notes.map((n) => ({ kind: 'note', at: n.creation, data: n })),
  ].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0))

  const items = []
  let lastDateKey = null
  for (const e of entries) {
    const d = parseFrappeDate(e.at)
    const dateKey = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    if (dateKey !== lastDateKey) {
      items.push({ type: 'separator', key: `sep-${dateKey}`, label: dateSeparatorLabel(e.at) })
      lastDateKey = dateKey
    }
    if (e.kind === 'note') items.push({ type: 'note', key: `note-${e.data.name}`, note: e.data })
    else items.push({ type: 'message', key: e.data.name, message: e.data })
  }
  return items
})

// --- Internal notes ------------------------------------------------------
const noteMode = ref(false)
function canDeleteNote(n) {
  return n.owner === auth.user || auth.isSystemManager
}
function deleteNote(n) {
  if (!confirm('Delete this note?')) return
  runAction(() => chat.deleteNote(n.name))
}

// --- Save number as Contact / Lead ---------------------------------------
const showLinkForm = ref(null) // null | 'contact' | 'lead'
const linkForm = ref({ firstName: '', lastName: '', customer: '', companyName: '' })
const customerMatches = ref([])
const linkBusy = ref(false)
const linkError = ref(null)

function openLinkForm(kind) {
  const [first, ...rest] = (displayName.value && displayName.value !== activeConversationNumber.value ? displayName.value : '').split(' ')
  linkForm.value = { firstName: first || '', lastName: rest.join(' '), customer: '', companyName: '' }
  customerMatches.value = []
  linkError.value = null
  showLinkForm.value = kind
}

let customerTimer
function onCustomerInput(e) {
  linkForm.value.customer = e.target.value
  clearTimeout(customerTimer)
  customerTimer = setTimeout(async () => {
    try {
      customerMatches.value = linkForm.value.customer
        ? await call('whatsnext.whatsnext.api.search_customers', { search: linkForm.value.customer }, 'GET')
        : []
    } catch {
      customerMatches.value = []
    }
  }, 250)
}

async function submitLinkForm() {
  linkBusy.value = true
  linkError.value = null
  try {
    if (showLinkForm.value === 'lead') await chat.createLead(linkForm.value)
    else await chat.saveAsContact(linkForm.value)
    showLinkForm.value = null
  } catch (e) {
    linkError.value = e.message
  } finally {
    linkBusy.value = false
  }
}

async function openMediaPanel() {
  showMediaPanel.value = true
  showContactInfo.value = false
  mediaTab.value = 'media'
  if (!activeConversationNumber.value) return
  mediaLoading.value = true
  try {
    mediaData.value = await call('whatsnext.whatsnext.api.get_conversation_media', { conversation_id: activeConversationNumber.value }, 'GET')
  } finally {
    mediaLoading.value = false
  }
}

// --- Assignment / status / opt-out -------------------------------------
const actionBusy = ref(false)
async function runAction(fn) {
  actionBusy.value = true
  composerError.value = null
  try {
    await fn()
  } catch (e) {
    composerError.value = e.message
  } finally {
    actionBusy.value = false
  }
}
function onAssign(e) { runAction(() => chat.assign(e.target.value)) }
function assignToMe() { runAction(() => chat.assign(auth.user)) }
function toggleClosed() { runAction(() => chat.setStatus(info.value?.status === 'Closed' ? 'Open' : 'Closed')) }
function toggleOptOut() { runAction(() => chat.setOptOut(!info.value?.opted_out)) }
function cancelScheduled(name) { runAction(() => chat.cancelScheduled(name)) }

// --- Emoji picker -----------------------------------------------------
const showEmojiPicker = ref(false)
const commonEmojis = ['😀','😁','😂','🤣','😊','😍','😘','😉','😎','🤔','😢','😡','👍','👎','🙏','👏','💪','🔥','✅','❌','⭐','🎉','❤️','💡','📌','⏰','📅','✨','🙌','👋']
function insertEmoji(e) {
  draft.value += e
  showEmojiPicker.value = false
}

// --- Quick replies -------------------------------------------------------
const quickReplies = ref([])
const showQuickReplies = ref(false)
const qrSearch = ref('')

async function loadQuickReplies() {
  try {
    quickReplies.value = await call('whatsnext.whatsnext.api.list_quick_replies', {}, 'GET')
  } catch {
    quickReplies.value = []
  }
}

// Typing "/" at the start of the composer suggests replies by shortcut/title.
const slashQuery = computed(() => (draft.value.startsWith('/') && !draft.value.includes(' ') ? draft.value.slice(1).toLowerCase() : null))
function matchReplies(q) {
  if (!q) return quickReplies.value
  return quickReplies.value.filter((r) =>
    (r.shortcut || '').toLowerCase().includes(q) || (r.title || '').toLowerCase().includes(q) || (r.message || '').toLowerCase().includes(q)
  )
}
const slashMatches = computed(() => (slashQuery.value === null ? [] : matchReplies(slashQuery.value).slice(0, 6)))
const pickerMatches = computed(() => matchReplies(qrSearch.value.trim().toLowerCase()))

function useQuickReply(r) {
  const name = (activeConversation.value?.profile_name || info.value?.profile_name || '').split(' ')[0]
  draft.value = (r.message || '').replace(/\{name\}/g, name || 'there')
  showQuickReplies.value = false
  qrSearch.value = ''
}

function onDraftKeydown(e) {
  if (e.key === 'Tab' && slashMatches.value.length) {
    e.preventDefault()
    useQuickReply(slashMatches.value[0])
  }
}

// --- Schedule (free text) ----------------------------------------------
const showSchedule = ref(false)
const scheduleAt = ref('')

// --- File attach --------------------------------------------------------
const fileInputEl = ref(null)
const attachSending = ref(false)

function triggerFilePicker() {
  showAttachMenu.value = false
  fileInputEl.value?.click()
}

// --- Reply-to (quoting) ----------------------------------------------
const replyingTo = ref(null)
function startReply(message) {
  replyingTo.value = message
  nextTick(() => document.querySelector('.wn-composer input[type="text"]')?.focus())
}
function replyLabel(m) {
  if (!m) return ''
  return m.message || (m.template ? '📋 ' + m.template : `[${m.content_type}]`)
}
function jumpToMessage(name) {
  const el = document.getElementById(`wn-msg-${name}`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('wn-flash')
  setTimeout(() => el.classList.remove('wn-flash'), 1200)
}

// --- Attach menu: location & contact card ----------------------------
const showAttachMenu = ref(false)
const showLocation = ref(false)
const loc = ref({ latitude: '', longitude: '', name: '', address: '', link: '' })
const locBusy = ref(false)
const locError = ref(null)

function openLocation() {
  showAttachMenu.value = false
  loc.value = { latitude: '', longitude: '', name: '', address: '', link: '' }
  locError.value = null
  showLocation.value = true
}

function useMyLocation() {
  if (!navigator.geolocation) {
    locError.value = 'This browser can’t share its location.'
    return
  }
  locBusy.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      loc.value.latitude = pos.coords.latitude.toFixed(6)
      loc.value.longitude = pos.coords.longitude.toFixed(6)
      locBusy.value = false
    },
    (err) => {
      locError.value = err.message || 'Couldn’t get your location.'
      locBusy.value = false
    },
    { enableHighAccuracy: true, timeout: 10000 }
  )
}

// Accepts a pasted Google Maps link ("…/@11.1,77.3,15z" or "…?q=11.1,77.3").
function parseMapsLink() {
  const m = loc.value.link.match(/[@=](-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/)
  if (m) {
    loc.value.latitude = m[1]
    loc.value.longitude = m[2]
    locError.value = null
  } else if (loc.value.link) {
    locError.value = 'Couldn’t find coordinates in that link.'
  }
}

function onMapsPaste() {
  // v-model only updates on the input event that follows paste.
  setTimeout(parseMapsLink, 0)
}

async function sendLocation() {
  if (loc.value.latitude === '' || loc.value.longitude === '') {
    locError.value = 'Enter coordinates, paste a Maps link, or use your current location.'
    return
  }
  locBusy.value = true
  locError.value = null
  try {
    await chat.sendLocation(activeConversationNumber.value, {
      latitude: loc.value.latitude, longitude: loc.value.longitude,
      name: loc.value.name, address: loc.value.address, replyTo: replyingTo.value?.name,
    })
    replyingTo.value = null
    showLocation.value = false
    scrollToBottom()
  } catch (e) {
    locError.value = e.message
  } finally {
    locBusy.value = false
  }
}

const showContactCard = ref(false)
const ccSearch = ref('')
const ccResults = ref([])
const ccManual = ref({ name: '', phone: '' })
const ccBusy = ref(false)
const ccError = ref(null)

async function openContactCard() {
  showAttachMenu.value = false
  ccSearch.value = ''
  ccManual.value = { name: '', phone: '' }
  ccError.value = null
  showContactCard.value = true
  searchContactCards()
}

async function searchContactCards() {
  try {
    ccResults.value = await call('whatsnext.whatsnext.api.search_contact_cards', { search: ccSearch.value || undefined }, 'GET')
  } catch (e) {
    ccError.value = e.message
  }
}
let ccTimer
watch(ccSearch, () => {
  clearTimeout(ccTimer)
  ccTimer = setTimeout(searchContactCards, 300)
})

async function sendContactCard(contact) {
  ccBusy.value = true
  ccError.value = null
  try {
    await chat.sendContactCard(activeConversationNumber.value, {
      contact: contact?.name,
      name: contact ? undefined : ccManual.value.name,
      phone: contact ? undefined : ccManual.value.phone,
      replyTo: replyingTo.value?.name,
    })
    replyingTo.value = null
    showContactCard.value = false
    scrollToBottom()
  } catch (e) {
    ccError.value = e.message
  } finally {
    ccBusy.value = false
  }
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
  if (!file || !activeConversationNumber.value) return

  attachSending.value = true
  composerError.value = null
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
    await chat.sendMedia(activeConversationNumber.value, fileUrl, mediaTypeFromMime(file.type), '', { replyTo: replyingTo.value?.name })
    replyingTo.value = null
    scrollToBottom()
  } catch (err) {
    composerError.value = err.message
  } finally {
    attachSending.value = false
  }
}

// --- Template picker (send a template mid-conversation) --------------
const showTplPicker = ref(false)
const tplList = ref([])
const tplSelected = ref(null)
const tplSending = ref(false)
const tplError = ref(null)

async function openTplPicker() {
  showTplPicker.value = true
  tplSelected.value = null
  tplError.value = null
  try {
    tplList.value = await call('whatsnext.whatsnext.api.get_templates', { approved_only: 1 }, 'GET')
  } catch (e) {
    tplError.value = e.message
  }
}

async function sendTplToActiveConversation(payload) {
  if (!tplSelected.value || !activeConversationNumber.value) return
  tplSending.value = true
  tplError.value = null
  try {
    await chat.sendTemplate(activeConversationNumber.value, tplSelected.value.name, payload.parameters, {
      headerMediaUrl: payload.headerMediaUrl,
      scheduledTime: payload.scheduledTime,
      replyTo: replyingTo.value?.name,
    })
    replyingTo.value = null
    showTplPicker.value = false
    scrollToBottom()
  } catch (e) {
    tplError.value = e.message
  } finally {
    tplSending.value = false
  }
}

// --- Lifecycle --------------------------------------------------------
onMounted(async () => {
  loadQuickReplies()
  chat.subscribeRealtime()
  chat.loadStats()
  await chat.loadConversations()
  openConversationFromQuery()
})

// Push notifications link to /whatsnext?conversation=<number> (see
// push_engine.notify_new_message).
function openConversationFromQuery() {
  const id = route.query.conversation
  if (!id || typeof id !== 'string') return
  selectConversation(id)
  router.replace({ query: {} })
}
watch(() => route.query.conversation, (id) => { if (id) openConversationFromQuery() })

let searchDebounceTimer
function onSearchInput(e) {
  clearTimeout(searchDebounceTimer)
  const value = e.target.value
  searchDebounceTimer = setTimeout(() => chat.setSearch(value), 300)
}

async function selectConversation(id) {
  composerError.value = null
  showSchedule.value = false
  replyingTo.value = null
  await chat.openConversation(id)
  scrollToBottom()
}

function closeConversation() {
  chat.activeConversationId = null
  showContactInfo.value = false
  showMediaPanel.value = false
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

// Only jump to the bottom for new messages, not when older ones are prepended.
let lastLastName = null
watch(() => chat.activeMessages, (list) => {
  const last = list[list.length - 1]?.name || null
  if (last !== lastLastName) scrollToBottom()
  lastLastName = last
})

async function loadOlder() {
  const el = messagesEl.value
  const before = el ? el.scrollHeight : 0
  await chat.loadOlder()
  nextTick(() => {
    if (el) el.scrollTop = el.scrollHeight - before
  })
}

function onMessagesScroll(e) {
  if (e.target.scrollTop < 40 && chat.activeHasOlder && !chat.loadingOlder) loadOlder()
}

async function send() {
  const text = draft.value.trim()
  if (!text || !activeConversationNumber.value) return
  if (noteMode.value) {
    draft.value = ''
    composerError.value = null
    try {
      await chat.addNote(text)
      scrollToBottom()
    } catch (e) {
      if (!draft.value) draft.value = text
      composerError.value = e.message
    }
    return
  }
  const scheduledTime = showSchedule.value && scheduleAt.value ? toFrappeDatetime(scheduleAt.value) : undefined
  if (showSchedule.value && !scheduledTime) {
    composerError.value = 'Pick a date and time to schedule, or close the schedule option.'
    return
  }
  draft.value = ''
  composerError.value = null
  try {
    await chat.sendText(activeConversationNumber.value, text, {
      referenceDoctype: activeConversation.value?.reference_doctype,
      referenceName: activeConversation.value?.reference_name,
      scheduledTime,
      replyTo: replyingTo.value?.name,
    })
    replyingTo.value = null
    if (scheduledTime) {
      showSchedule.value = false
      scheduleAt.value = ''
    }
  } catch (e) {
    // Don't silently lose what the user typed when the request fails.
    if (!draft.value) draft.value = text
    composerError.value = e.message
  }
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
const ncSending = ref(false)
const ncError = ref(null)
const ncManualNumber = ref('')

function openNewChat() {
  showNewChat.value = true
  ncStep.value = 'contact'
  ncSearch.value = ''
  ncManualNumber.value = ''
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

let contactSearchDebounce
watch(ncSearch, () => {
  clearTimeout(contactSearchDebounce)
  contactSearchDebounce = setTimeout(searchContacts, 300)
})

async function pickContact(contact) {
  ncSelectedContact.value = contact
  ncError.value = null
  try {
    ncTemplates.value = await call('whatsnext.whatsnext.api.get_templates', { approved_only: 1 }, 'GET')
  } catch (e) {
    ncError.value = e.message
  }
  ncStep.value = 'template'
}

function pickManualNumber() {
  const digits = ncManualNumber.value.replace(/[^\d+]/g, '')
  if (digits.replace('+', '').length < 7) {
    ncError.value = 'Enter a valid WhatsApp number with country code.'
    return
  }
  pickContact({ full_name: '', phone: digits, customer: '' })
}

async function sendNewChat(payload) {
  if (!ncSelectedContact.value || !ncSelectedTemplate.value) return
  ncSending.value = true
  ncError.value = null
  try {
    const phone = ncSelectedContact.value.phone
    const msg = await chat.sendTemplate(phone, ncSelectedTemplate.value.name, payload.parameters, {
      headerMediaUrl: payload.headerMediaUrl,
      scheduledTime: payload.scheduledTime,
    })
    showNewChat.value = false
    // The backend normalizes the number ("+91 98940 88422" -> "919894088422")
    // and groups the thread under that, so open the id it actually used.
    const conversationId = msg?.conversation_id || msg?.to_number || phone
    await chat.loadConversations()
    await selectConversation(conversationId)
  } catch (e) {
    ncError.value = e.message
  } finally {
    ncSending.value = false
  }
}
</script>

<template>
  <div class="wn-chat-layout" :class="{ 'has-active': !!chat.activeConversationId }">
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
          <button v-for="[tab, label] in FILTER_TABS" :key="tab"
                  :class="{ active: chat.filter === tab }" @click="chat.setFilter(tab)">
            {{ label }}
          </button>
        </div>
      </div>
      <ConversationList
        :conversations="chat.conversations"
        :active-id="chat.activeConversationId"
        :has-more="chat.hasMoreConversations"
        :loading-more="chat.loadingMoreConversations"
        @select="selectConversation"
        @load-more="chat.loadMoreConversations()"
      />
    </div>

    <div class="wn-chat-pane">
      <template v-if="chat.activeConversationId">
        <div class="wn-chat-header">
          <button class="wn-info-btn wn-back-btn" @click="closeConversation" title="Back to chats">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
          <div class="wn-avatar">{{ (displayName || '?').charAt(0).toUpperCase() }}</div>
          <div class="wn-chat-header-name">
            <div class="wn-chat-name">{{ displayName }}</div>
            <div class="wn-chat-phone">
              {{ activeConversationNumber }}
              <span v-if="info?.status === 'Closed'" class="wn-badge">Closed</span>
              <span v-if="info?.assigned_to" class="wn-badge green">{{ info.assigned_to === auth.user ? 'You' : (info.assigned_to_name || info.assigned_to) }}</span>
              <span v-if="info?.opted_out" class="wn-badge red">Opted out</span>
            </div>
          </div>
          <button v-if="!info?.assigned_to" class="ghost small wn-hide-mobile" :disabled="actionBusy" @click="assignToMe">Assign to me</button>
          <button class="ghost small" :disabled="actionBusy" @click="toggleClosed">
            {{ info?.status === 'Closed' ? 'Reopen' : 'Close' }}
          </button>
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

        <div class="wn-messages" ref="messagesEl" @scroll="onMessagesScroll">
          <div v-if="chat.activeHasOlder" class="wn-older-row">
            <button class="ghost small" :disabled="chat.loadingOlder" @click="loadOlder">
              {{ chat.loadingOlder ? 'Loading…' : 'Load earlier messages' }}
            </button>
          </div>
          <template v-for="item in timelineItems" :key="item.key">
            <div v-if="item.type === 'separator'" class="wn-date-pill-row">
              <span class="wn-date-pill">{{ item.label }}</span>
            </div>
            <div v-else-if="item.type === 'note'" class="wn-note-row">
              <div class="wn-note">
                <div class="wn-note-head">
                  <span>📝 Note · {{ item.note.author || item.note.owner }}</span>
                  <span>{{ parseFrappeDate(item.note.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</span>
                  <button v-if="canDeleteNote(item.note)" type="button" class="wn-note-del" title="Delete note" @click="deleteNote(item.note)">✕</button>
                </div>
                <p>{{ item.note.note }}</p>
              </div>
            </div>
            <div v-else :id="`wn-msg-${item.message.name}`" class="wn-msg-wrap">
              <MessageBubble :message="item.message" @reply="startReply" @jump="jumpToMessage" />
            </div>
          </template>
          <div v-if="chat.loadingMessages" class="wn-loading">Loading…</div>
        </div>

        <div v-if="info?.scheduled?.length" class="wn-scheduled-strip">
          🕒 {{ info.scheduled.length }} scheduled —
          <button class="wn-link" @click="showMediaPanel = false; showContactInfo = true">view</button>
        </div>

        <div v-if="!windowOpen" class="wn-window-banner">
          The 24-hour reply window is closed — WhatsApp only allows an approved template until the customer writes back.
          <button class="primary small" @click="openTplPicker">Send a template</button>
        </div>
        <div v-else-if="windowLabel" class="wn-window-hint">{{ windowLabel }}</div>

        <p v-if="composerError" class="wn-error wn-composer-error">{{ composerError }}</p>
        <div v-if="replyingTo" class="wn-reply-bar">
          <div class="wn-reply-bar-text">
            <strong>Replying to {{ replyingTo.type === 'Incoming' ? (displayName || 'customer') : 'yourself' }}</strong>
            <span>{{ replyLabel(replyingTo) }}</span>
          </div>
          <button type="button" class="wn-reply-cancel" @click="replyingTo = null" title="Cancel reply">✕</button>
        </div>
        <div v-if="showSchedule && windowOpen" class="wn-schedule-row">
          <label>Send at</label>
          <input v-model="scheduleAt" type="datetime-local" />
          <button type="button" class="ghost small" @click="showSchedule = false; scheduleAt = ''">Cancel</button>
        </div>
        <form class="wn-composer" @submit.prevent="send">
          <button type="button" class="wn-tpl-btn" @click="openTplPicker" title="Send a template">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z" />
              <rect x="5" y="4" width="14" height="18" rx="2" />
              <line x1="9" y1="11" x2="15" y2="11" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          </button>
          <template v-if="windowOpen">
            <div class="wn-emoji-wrap wn-hide-mobile">
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
            <div class="wn-emoji-wrap">
              <button type="button" class="wn-tpl-btn" :class="{ active: showQuickReplies }" @click="showQuickReplies = !showQuickReplies; showEmojiPicker = false" title="Quick replies (or type /)">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>
              </button>
              <div v-if="showQuickReplies" class="wn-qr-popup">
                <input v-model="qrSearch" type="text" placeholder="Search quick replies" class="wn-qr-search" />
                <button v-for="r in pickerMatches" :key="r.name" type="button" class="wn-qr-item" @click="useQuickReply(r)">
                  <strong>{{ r.title }}</strong><span v-if="r.shortcut" class="wn-qr-shortcut">/{{ r.shortcut }}</span>
                  <span class="wn-qr-text">{{ r.message }}</span>
                </button>
                <p v-if="!pickerMatches.length" class="wn-muted-small wn-qr-empty">
                  No quick replies yet — add them in <router-link to="/whatsnext/settings">Settings</router-link>.
                </p>
              </div>
            </div>
            <div class="wn-emoji-wrap">
              <button type="button" class="wn-tpl-btn" :class="{ active: showAttachMenu }" @click="showAttachMenu = !showAttachMenu; showQuickReplies = false" :disabled="attachSending" title="Attach">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
              </button>
              <div v-if="showAttachMenu" class="wn-attach-menu">
                <button type="button" @click="triggerFilePicker">📎 File or photo</button>
                <button type="button" @click="openLocation">📍 Location</button>
                <button type="button" @click="openContactCard">👤 Contact card</button>
              </div>
            </div>
            <button type="button" class="wn-tpl-btn" :class="{ active: showSchedule }" @click="showSchedule = !showSchedule" title="Schedule">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
              </svg>
            </button>
          </template>
          <input ref="fileInputEl" type="file" class="wn-hidden-file-input" @change="onFileSelected" />
          <select v-if="auth.providers.length > 1" v-model="chat.provider" class="wn-provider-select" title="Send via">
            <option value="">Default ({{ auth.defaultProvider }})</option>
            <option v-for="p in auth.providers" :key="p" :value="p">{{ p }}</option>
          </select>
          <div v-if="slashMatches.length && windowOpen" class="wn-slash-popup">
            <button v-for="r in slashMatches" :key="r.name" type="button" class="wn-qr-item" @click="useQuickReply(r)">
              <strong>{{ r.title }}</strong><span v-if="r.shortcut" class="wn-qr-shortcut">/{{ r.shortcut }}</span>
              <span class="wn-qr-text">{{ r.message }}</span>
            </button>
          </div>
          <button type="button" class="wn-tpl-btn" :class="{ active: noteMode }" @click="noteMode = !noteMode"
                  :title="noteMode ? 'Back to messaging the customer' : 'Write an internal note (not sent to the customer)'">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
          </button>
          <input v-model="draft" type="text" :class="{ 'wn-note-input': noteMode }" :disabled="!windowOpen && !noteMode" @keydown="onDraftKeydown"
                 :placeholder="noteMode ? 'Internal note — only your team sees this' : (windowOpen ? 'Type a message' : 'Templates only — the customer hasn’t written in 24 hours')" />
          <button type="submit" :class="{ 'wn-note-send': noteMode }" :disabled="!windowOpen && !noteMode">{{ noteMode ? 'Add note' : (showSchedule ? 'Schedule' : 'Send') }}</button>
        </form>
      </template>

      <div v-else class="wn-chat-empty">
        <p>Select a conversation to start messaging</p>
      </div>
    </div>

    <div v-if="showContactInfo && chat.activeConversationId" class="wn-info-panel">
      <div class="wn-info-header">
        <span>Contact Info</span>
        <button @click="showContactInfo = false">✕</button>
      </div>
      <div class="wn-info-avatar">{{ (displayName || '?').charAt(0).toUpperCase() }}</div>
      <div class="wn-info-name">{{ displayName }}</div>
      <div class="wn-info-row">
        <span class="wn-info-label">Phone</span>
        <span>{{ activeConversationNumber }}</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Customer</span>
        <a v-if="info?.customer" :href="`/app/customer/${encodeURIComponent(info.customer)}`" target="_blank">{{ info.customer }}</a>
        <span v-else>—</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Contact</span>
        <a v-if="info?.contact" :href="`/app/contact/${encodeURIComponent(info.contact)}`" target="_blank">{{ info.contact }}</a>
        <template v-else>
          <span>Not saved in ERPNext</span>
          <div class="wn-link-actions">
            <button class="ghost small" @click="openLinkForm('contact')">Save as Contact</button>
            <button class="ghost small" @click="openLinkForm('lead')">Create Lead</button>
          </div>
        </template>
      </div>
      <div v-if="info?.lead" class="wn-info-row">
        <span class="wn-info-label">Lead</span>
        <a :href="`/app/lead/${encodeURIComponent(info.lead)}`" target="_blank">{{ info.lead }}</a>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Assigned to</span>
        <select :value="info?.assigned_to || ''" :disabled="actionBusy" @change="onAssign">
          <option value="">Unassigned</option>
          <option v-for="a in auth.agents" :key="a.name" :value="a.name">{{ a.full_name || a.name }}</option>
        </select>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Reply window</span>
        <span>{{ windowOpen ? (windowLabel || 'Open') : 'Closed — templates only' }}</span>
      </div>
      <div class="wn-info-row">
        <span class="wn-info-label">Promotional messages</span>
        <span>
          {{ info?.opted_out ? 'Opted out' : 'Subscribed' }}
          <button class="ghost small" :disabled="actionBusy" @click="toggleOptOut">
            {{ info?.opted_out ? 'Opt back in' : 'Mark opted out' }}
          </button>
        </span>
      </div>
      <div v-if="info?.scheduled?.length" class="wn-info-row">
        <span class="wn-info-label">Scheduled</span>
        <div v-for="s in info.scheduled" :key="s.name" class="wn-scheduled-item">
          <div>
            <strong>{{ parseFrappeDate(s.scheduled_time).toLocaleString() }}</strong>
            <div class="wn-muted-small">{{ s.template ? '📋 ' + s.template : (s.message || '').slice(0, 60) }}</div>
          </div>
          <button class="ghost small danger" :disabled="actionBusy" @click="cancelScheduled(s.name)">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="showMediaPanel && chat.activeConversationId" class="wn-info-panel">
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
            <div v-for="t in tplList" :key="t.name" class="wn-nc-item wn-nc-template" @click="tplSelected = t">
              <div class="wn-nc-item-name">{{ t.template_name }} <span class="wn-badge">{{ t.category }}</span></div>
              <div class="wn-nc-item-meta">{{ t.body }}</div>
            </div>
            <p v-if="!tplList.length" class="wn-muted">No approved templates available yet.</p>
          </div>
          <div class="wn-modal-actions">
            <button class="ghost" @click="showTplPicker = false">Cancel</button>
          </div>
        </template>
        <template v-else>
          <h3>{{ tplSelected.template_name }}</h3>
          <p v-if="info?.opted_out && tplSelected.category === 'Marketing'" class="wn-error">
            This customer opted out of promotional messages — Marketing templates will be refused.
          </p>
          <TemplateSendForm :template="tplSelected" :sending="tplSending" @back="tplSelected = null" @send="sendTplToActiveConversation" />
        </template>
        <p v-if="tplError" class="wn-error">{{ tplError }}</p>
      </div>
    </div>

    <div v-if="showLinkForm" class="wn-modal-backdrop" @click.self="showLinkForm = null">
      <div class="wn-modal">
        <h3>{{ showLinkForm === 'lead' ? 'Create a Lead' : 'Save as Contact' }}</h3>
        <p class="wn-hint">For {{ activeConversationNumber }} — this chat will be linked to it in ERPNext.</p>
        <div class="wn-loc-row">
          <div><label>First name</label><input v-model="linkForm.firstName" type="text" /></div>
          <div><label>Last name</label><input v-model="linkForm.lastName" type="text" /></div>
        </div>
        <template v-if="showLinkForm === 'lead'">
          <label>Company (optional)</label>
          <input v-model="linkForm.companyName" type="text" />
        </template>
        <template v-else>
          <label>Customer (optional)</label>
          <div class="wn-ac">
            <input :value="linkForm.customer" type="text" placeholder="Link to an existing customer" @input="onCustomerInput" />
            <div v-if="customerMatches.length" class="wn-ac-list">
              <button v-for="c in customerMatches" :key="c.name" type="button" @click="linkForm.customer = c.name; customerMatches = []">
                {{ c.customer_name }}<span v-if="c.customer_name !== c.name" class="wn-muted-small"> · {{ c.name }}</span>
              </button>
            </div>
          </div>
        </template>
        <p v-if="linkError" class="wn-error">{{ linkError }}</p>
        <div class="wn-modal-actions">
          <button class="ghost" @click="showLinkForm = null">Cancel</button>
          <button class="primary" :disabled="linkBusy || !linkForm.firstName.trim()" @click="submitLinkForm">
            {{ linkBusy ? 'Saving…' : (showLinkForm === 'lead' ? 'Create Lead' : 'Save Contact') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showLocation" class="wn-modal-backdrop" @click.self="showLocation = false">
      <div class="wn-modal">
        <h3>Share a location</h3>
        <button class="ghost" type="button" :disabled="locBusy" @click="useMyLocation">📍 Use my current location</button>
        <label>…or paste a Google Maps link</label>
        <input v-model="loc.link" type="text" placeholder="https://maps.google.com/…" @change="parseMapsLink" @paste="onMapsPaste" />
        <div class="wn-loc-row">
          <div><label>Latitude</label><input v-model="loc.latitude" type="text" inputmode="decimal" /></div>
          <div><label>Longitude</label><input v-model="loc.longitude" type="text" inputmode="decimal" /></div>
        </div>
        <label>Place name (optional)</label>
        <input v-model="loc.name" type="text" placeholder="Pranera Unit 2" />
        <label>Address (optional)</label>
        <input v-model="loc.address" type="text" />
        <p v-if="locError" class="wn-error">{{ locError }}</p>
        <div class="wn-modal-actions">
          <button class="ghost" @click="showLocation = false">Cancel</button>
          <button class="primary" :disabled="locBusy" @click="sendLocation">{{ locBusy ? 'Working…' : 'Send location' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showContactCard" class="wn-modal-backdrop" @click.self="showContactCard = false">
      <div class="wn-modal">
        <h3>Share a contact card</h3>
        <input v-model="ccSearch" type="text" placeholder="Search contacts by name, phone or company" class="wn-nc-search" />
        <div class="wn-nc-list">
          <div v-for="c in ccResults" :key="c.name" class="wn-nc-item" @click="!ccBusy && sendContactCard(c)">
            <div class="wn-avatar">{{ (c.full_name || c.name || '?').charAt(0).toUpperCase() }}</div>
            <div class="wn-nc-item-body">
              <div class="wn-nc-item-name">{{ c.full_name || c.name }}</div>
              <div class="wn-nc-item-meta">{{ [c.company_name, c.mobile_no || c.phone].filter(Boolean).join(' · ') }}</div>
            </div>
          </div>
          <p v-if="!ccResults.length" class="wn-muted">No contacts found.</p>
        </div>
        <label>…or enter one</label>
        <div class="wn-loc-row">
          <div><input v-model="ccManual.name" type="text" placeholder="Name" /></div>
          <div><input v-model="ccManual.phone" type="text" placeholder="+91 98765 43210" /></div>
        </div>
        <p v-if="ccError" class="wn-error">{{ ccError }}</p>
        <div class="wn-modal-actions">
          <button class="ghost" @click="showContactCard = false">Cancel</button>
          <button class="primary" :disabled="ccBusy || !ccManual.name || !ccManual.phone" @click="sendContactCard(null)">Send</button>
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
              :key="c.contact_name + c.customer"
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
          <label>Or message a number directly</label>
          <div class="wn-manual-row">
            <input v-model="ncManualNumber" type="text" placeholder="+91 98765 43210" @keyup.enter="pickManualNumber" />
            <button class="ghost" @click="pickManualNumber">Next</button>
          </div>
          <div class="wn-modal-actions">
            <button class="ghost" @click="showNewChat = false">Cancel</button>
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
              @click="ncSelectedTemplate = t"
            >
              <div class="wn-nc-item-name">{{ t.template_name }} <span class="wn-badge">{{ t.category }}</span></div>
              <div class="wn-nc-item-meta">{{ t.body }}</div>
            </div>
            <p v-if="!ncTemplates.length" class="wn-muted">No approved templates available yet.</p>
            <div class="wn-modal-actions">
              <button class="ghost" @click="ncStep = 'contact'">Back</button>
            </div>
          </div>

          <TemplateSendForm v-else :template="ncSelectedTemplate" :sending="ncSending"
                            @back="ncSelectedTemplate = null" @send="sendNewChat" />
        </template>

        <p v-if="ncError" class="wn-error">{{ ncError }}</p>
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
.wn-back-btn { display: none; }
.wn-info-btn { background: none; border: none; color: var(--wn-text-muted); cursor: pointer; padding: 6px; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; }
.wn-info-btn:hover { color: var(--wn-teal); }
.wn-info-panel { position: absolute; top: 0; right: 0; bottom: 0; width: 300px; max-width: 100%; background: white; box-shadow: -2px 0 8px rgba(0,0,0,0.08); padding: 16px; z-index: 40; overflow-y: auto; }
.wn-info-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
.wn-info-header button { background: none; border: none; font-size: 14px; color: var(--wn-text-muted); cursor: pointer; }
.wn-info-avatar { width: 64px; height: 64px; border-radius: 50%; background: var(--wn-navy); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 24px; margin: 0 auto 10px; }
.wn-info-name { text-align: center; font-weight: 600; font-size: 15px; margin-bottom: 16px; }
.wn-info-row { display: flex; flex-direction: column; gap: 4px; padding: 10px 0; border-top: 1px solid var(--wn-border); font-size: 13px; }
.wn-info-row select { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-info-row a { color: var(--wn-blue); }
.wn-info-label { font-size: 11px; color: var(--wn-text-muted); font-weight: 600; text-transform: uppercase; }
.wn-scheduled-item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 0; }
.wn-muted-small { font-size: 11.5px; color: var(--wn-text-muted); }
.wn-media-tabs { display: flex; gap: 4px; margin-bottom: 14px; }
.wn-media-tabs button { flex: 1; padding: 6px 0; border: none; background: var(--wn-bg); border-radius: 6px; font-size: 11.5px; color: var(--wn-text-muted); }
.wn-media-tabs button.active { background: var(--wn-teal); color: white; font-weight: 600; }
.wn-media-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.wn-media-thumb { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: var(--wn-bg); display: flex; align-items: center; justify-content: center; font-size: 20px; }
.wn-media-list { display: flex; flex-direction: column; gap: 8px; }
.wn-media-doc-item { font-size: 12.5px; color: var(--wn-blue); }
.wn-media-audio { width: 100%; }
.wn-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--wn-navy); color: white; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.wn-chat-name { font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-chat-phone { font-size: 12px; color: var(--wn-text-muted); display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.wn-messages { flex: 1; overflow-y: auto; padding: 16px; background: var(--wn-bg); }
.wn-older-row { display: flex; justify-content: center; margin-bottom: 8px; }
.wn-date-pill-row { display: flex; justify-content: center; margin: 12px 0; position: sticky; top: 0; z-index: 1; }
.wn-date-pill {
  background: #e9edef;
  color: #54656f;
  font-size: 12.5px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 8px;
  box-shadow: 0 1px 0.5px rgba(0,0,0,0.08);
}
.wn-loading { text-align: center; font-size: 12px; color: var(--wn-text-muted); }
.wn-window-banner { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 12px; background: #fef3c7; color: #92400e; font-size: 12.5px; border-top: 1px solid #fde68a; }
.wn-window-hint { padding: 4px 12px; font-size: 11px; color: var(--wn-text-muted); text-align: right; }
.wn-scheduled-strip { padding: 6px 12px; font-size: 12px; color: var(--wn-text-muted); background: var(--wn-teal-light); }
.wn-link { background: none; border: none; color: var(--wn-blue); padding: 0; font-size: inherit; text-decoration: underline; }
.wn-schedule-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px 0; font-size: 12.5px; }
.wn-schedule-row input { padding: 6px 8px; border-radius: 8px; border: 1px solid var(--wn-border); }
.wn-composer { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--wn-border); align-items: center; position: relative; }
.wn-qr-popup, .wn-slash-popup { position: absolute; bottom: 44px; left: 0; background: white; border-radius: 10px; box-shadow: 0 4px 16px rgba(15,61,62,0.16); padding: 6px; z-index: 30; width: 320px; max-width: 86vw; max-height: 320px; overflow-y: auto; }
.wn-slash-popup { bottom: 60px; left: 12px; }
.wn-qr-search { width: 100%; padding: 7px 9px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 12.5px; margin-bottom: 4px; box-sizing: border-box; }
.wn-qr-item { display: block; width: 100%; text-align: left; background: none !important; color: var(--wn-text) !important; border: none; padding: 8px !important; border-radius: 8px !important; font-weight: 400 !important; font-size: 12.5px; }
.wn-qr-item:hover { background: var(--wn-bg) !important; }
.wn-qr-shortcut { margin-left: 6px; color: var(--wn-teal); font-size: 11.5px; }
.wn-qr-text { display: block; color: var(--wn-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.wn-qr-empty { padding: 8px; }
.wn-attach-menu { position: absolute; bottom: 44px; left: 0; background: white; border-radius: 10px; box-shadow: 0 4px 16px rgba(15,61,62,0.16); padding: 6px; z-index: 30; min-width: 180px; }
.wn-attach-menu button { display: block; width: 100%; text-align: left; background: none !important; color: var(--wn-text) !important; border: none; padding: 9px 10px !important; border-radius: 8px !important; font-weight: 400 !important; font-size: 13px; }
.wn-attach-menu button:hover { background: var(--wn-bg) !important; }
.wn-reply-bar { display: flex; align-items: center; gap: 8px; margin: 8px 12px 0; padding: 6px 10px; border-left: 3px solid var(--wn-teal); background: var(--wn-bg); border-radius: 6px; }
.wn-reply-bar-text { flex: 1; min-width: 0; font-size: 12px; color: var(--wn-text-muted); }
.wn-reply-bar-text strong { display: block; color: var(--wn-teal); font-size: 11.5px; }
.wn-reply-bar-text span { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-reply-cancel { background: none; border: none; color: var(--wn-text-muted); font-size: 14px; cursor: pointer; }
.wn-msg-wrap { border-radius: 14px; transition: background 0.4s; }
.wn-msg-wrap.wn-flash { background: rgba(22, 163, 148, 0.18); }
.wn-loc-row { display: flex; gap: 10px; }
.wn-note-row { display: flex; justify-content: center; margin: 8px 0; }
.wn-note { max-width: 80%; background: #fff8db; border: 1px dashed #e6c766; border-radius: 10px; padding: 6px 10px; font-size: 13px; }
.wn-note p { margin: 2px 0 0; white-space: pre-wrap; word-break: break-word; }
.wn-note-head { display: flex; gap: 8px; align-items: center; font-size: 11px; color: #8a6d00; font-weight: 600; }
.wn-note-del { background: none; border: none; color: #8a6d00; font-size: 11px; cursor: pointer; padding: 0 2px; margin-left: auto; }
.wn-note-input { background: #fffbea !important; border-color: #e6c766 !important; }
.wn-composer button.wn-note-send { background: #b38600; }
.wn-link-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.wn-ac { position: relative; }
.wn-ac-list { position: absolute; left: 0; right: 0; top: 100%; background: white; border: 1px solid var(--wn-border); border-radius: 8px; z-index: 5; max-height: 200px; overflow-y: auto; }
.wn-ac-list button { display: block; width: 100%; text-align: left; background: none; border: none; padding: 8px 10px; font-size: 13px; }
.wn-ac-list button:hover { background: var(--wn-bg); }
.wn-loc-row > div { flex: 1; min-width: 0; }
.wn-composer input { flex: 1; min-width: 0; padding: 10px 14px; border-radius: 20px; border: 1px solid var(--wn-border); font-size: 14px; }
.wn-composer input:disabled { background: var(--wn-bg); }
.wn-composer button { padding: 10px 18px; border-radius: 20px; border: none; background: var(--wn-teal); color: white; font-weight: 600; }
.wn-composer button:disabled { opacity: 0.5; }
.wn-provider-select { padding: 8px; border-radius: 20px; border: 1px solid var(--wn-border); font-size: 12px; background: white; max-width: 120px; }
.wn-tpl-btn { background: var(--wn-bg) !important; color: var(--wn-text-muted) !important; padding: 8px 12px !important; border-radius: 20px !important; display: inline-flex; align-items: center; justify-content: center; }
.wn-tpl-btn.active { color: var(--wn-teal) !important; background: var(--wn-teal-light) !important; }
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
.wn-nc-item-meta { font-size: 11.5px; color: var(--wn-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.wn-nc-template { flex-direction: column; align-items: flex-start; }
.wn-hint { font-size: 11.5px; color: var(--wn-text-muted); margin-top: -6px; margin-bottom: 12px; }
.wn-manual-row { display: flex; gap: 8px; }
.wn-manual-row input { flex: 1; }
.wn-modal label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 10px 0 4px; }
.wn-modal input[type="text"] { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; padding: 10px 0; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }

/* Phones: one pane at a time — the list, or the open chat with a back
   button. (Previously the chat pane was simply hidden below 768px, so a
   conversation could never be opened on a phone.) */
@media (max-width: 768px) {
  .wn-conv-pane { width: 100%; border-right: none; }
  .wn-chat-pane { display: none; }
  .wn-chat-layout.has-active .wn-conv-pane { display: none; }
  .wn-chat-layout.has-active .wn-chat-pane { display: flex; }
  .wn-back-btn { display: inline-flex; }
  .wn-hide-mobile { display: none !important; }
  .wn-chat-header { padding: 8px 10px; gap: 6px; }
  .wn-composer { padding: 8px; gap: 6px; }
  .wn-composer button[type="submit"] { padding: 10px 14px; }
  .wn-filter-tabs { overflow-x: auto; }
  .wn-filter-tabs button { flex: 0 0 auto; padding: 5px 10px; }
  .wn-window-banner { flex-direction: column; align-items: stretch; }
}
</style>
