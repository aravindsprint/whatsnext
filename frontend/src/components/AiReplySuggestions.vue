<script setup>
import { ref, watch } from 'vue'
import { loadReplyOptions, requestSuggestions, formatCredits } from '@/lib/aiReplies'

// "Suggest reply" button and panel. Shown by HomePage only when an installed
// app provides the smart_replies extension. Suggestions are drafts: picking
// one fills the composer for the agent to edit and send.
const props = defineProps({
  ext: { type: Object, required: true },
  conversationId: { type: String, default: null },
})
const emit = defineEmits(['use', 'open'])

const open = ref(false)
const loading = ref(false)
const error = ref(null)
const instruction = ref('')
const suggestions = ref([])
const models = ref([])
const model = ref('')
const credits = ref(null)
const optionsLoaded = ref(false)

async function ensureOptions() {
  if (optionsLoaded.value) return
  const opts = await loadReplyOptions(props.ext)
  models.value = opts.models
  model.value = opts.defaultModel || opts.models[0]?.tier || ''
  credits.value = opts.credits
  optionsLoaded.value = true
}

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  emit('open')
  error.value = null
  try {
    await ensureOptions()
    if (!suggestions.value.length) await suggest()
  } catch (e) {
    error.value = e.message
  }
}

async function suggest() {
  if (!props.conversationId || loading.value) return
  loading.value = true
  error.value = null
  try {
    const res = await requestSuggestions(props.ext, {
      conversationId: props.conversationId,
      model: model.value,
      instruction: instruction.value,
    })
    suggestions.value = res.suggestions
    if (res.credits !== null) credits.value = res.credits
    if (!res.suggestions.length) error.value = 'No suggestions this time. Try again or add a note on what to say.'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function use(text) {
  emit('use', text)
  open.value = false
}

function close() {
  open.value = false
}

// A different chat: its suggestions don't apply.
watch(() => props.conversationId, () => {
  suggestions.value = []
  instruction.value = ''
  error.value = null
  open.value = false
})

defineExpose({ close })
</script>

<template>
  <div class="wn-emoji-wrap">
    <button type="button" class="wn-ai-toggle" :class="{ active: open }" @click="toggle" title="Suggest a reply (AI)" aria-label="Suggest a reply">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
        <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
      </svg>
    </button>
    <div v-if="open" class="wn-ai-popup" role="dialog" aria-label="Suggested replies">
      <div class="wn-ai-head">
        <strong>Suggested replies</strong>
        <span v-if="credits !== null" class="wn-ai-muted" title="AI credits left">{{ formatCredits(credits) }} credits</span>
      </div>
      <!-- Not a <form>: this sits inside the composer's form, and Enter here must not send the chat message. -->
      <div class="wn-ai-controls">
        <input v-model="instruction" type="text" maxlength="500" placeholder="What should it say? (optional)"
               @keydown.enter.prevent="suggest" />
        <select v-if="models.length > 1" v-model="model" aria-label="AI model">
          <option v-for="m in models" :key="m.tier" :value="m.tier" :title="m.description">{{ m.tier }}</option>
        </select>
        <button type="button" class="wn-ai-go" :disabled="loading || !conversationId" @click="suggest">{{ suggestions.length ? 'Try again' : 'Suggest' }}</button>
      </div>
      <p v-if="loading" class="wn-ai-muted wn-ai-status">Thinking about a reply…</p>
      <p v-else-if="error" class="wn-ai-error wn-ai-status">{{ error }}</p>
      <template v-if="!loading">
        <button v-for="(s, i) in suggestions" :key="i" type="button" class="wn-ai-item" @click="use(s)">{{ s }}</button>
      </template>
      <p class="wn-ai-muted wn-ai-foot">Check before sending: AI can get details wrong.</p>
    </div>
  </div>
</template>

<style scoped>
/* Matches the composer's own icon buttons (HomePage .wn-tpl-btn). */
.wn-ai-toggle {
  background: var(--wn-bg) !important; color: var(--wn-text-muted) !important;
  padding: 8px 12px !important; border-radius: 20px !important; border: none;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
}
.wn-ai-toggle.active { color: var(--wn-teal) !important; background: var(--wn-teal-light) !important; }
.wn-ai-popup {
  position: absolute; bottom: 44px; left: 0; z-index: 30;
  width: 420px; max-width: 86vw; max-height: 60vh; overflow-y: auto;
  background: white; border-radius: 10px; box-shadow: 0 4px 16px rgba(15, 61, 62, 0.16); padding: 10px;
  color: var(--wn-text); font-size: 13px;
}
.wn-ai-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.wn-ai-controls { display: flex; gap: 6px; margin-bottom: 6px; }
.wn-ai-controls input { flex: 1; min-width: 0; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-ai-controls select { padding: 6px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; background: white; }
.wn-ai-go {
  flex-shrink: 0; padding: 6px 12px; border-radius: 8px; border: none;
  background: var(--wn-teal); color: white; font-weight: 600; font-size: 12px; cursor: pointer;
}
.wn-ai-go:disabled { opacity: 0.5; cursor: default; }
.wn-ai-item {
  display: block; width: 100%; text-align: left; white-space: pre-wrap; cursor: pointer;
  background: none; color: var(--wn-text); border: 1px solid var(--wn-border);
  padding: 8px 10px; border-radius: 8px; font-size: 13px; line-height: 1.4; margin-top: 6px;
}
.wn-ai-item:hover { background: var(--wn-teal-light); border-color: var(--wn-teal); }
.wn-ai-muted { color: var(--wn-text-muted); font-size: 12px; }
.wn-ai-error { color: var(--wn-red); font-size: 12px; }
.wn-ai-status { margin: 6px 2px; }
.wn-ai-foot { margin: 8px 2px 0; }
/* On phones the button sits mid-row, so pin the panel to the screen edges
   instead of the button, or it would run off the right side. */
@media (max-width: 600px) {
  .wn-ai-popup { position: fixed; left: 12px; right: 12px; bottom: 76px; width: auto; max-width: none; }
}
</style>
