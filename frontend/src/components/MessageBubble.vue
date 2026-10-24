<script setup>
import { computed } from 'vue'
import { parseFrappeDate } from '@/lib/date'

const props = defineProps({ message: Object })
const emit = defineEmits(['reply', 'jump'])

const statusIcon = { Sent: '✓', Delivered: '✓✓', Read: '✓✓', Failed: '⚠️', Pending: '🕒', Queued: '🕒' }

// Message text split into plain text and links (rendered as <a>, never as
// HTML), so shared map pins and URLs are tappable without v-html.
const URL_RE = /(https?:\/\/[^\s<>"']+)/g
const segments = computed(() => {
  const text = props.message.message || ''
  const parts = []
  let last = 0
  for (const m of text.matchAll(URL_RE)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) })
    parts.push({ text: m[0], href: m[0] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  return parts
})
</script>

<template>
  <div class="wn-bubble-row" :class="message.type === 'Outgoing' ? 'out' : 'in'">
    <div class="wn-bubble">
      <button v-if="message.reply_preview" type="button" class="wn-bubble-quote" @click="emit('jump', message.reply_preview.name)">
        <strong>{{ message.reply_preview.author || 'Customer' }}</strong>
        <span>{{ message.reply_preview.text }}</span>
      </button>
      <div v-if="message.template" class="wn-bubble-template">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z" />
          <rect x="5" y="4" width="14" height="18" rx="2" />
          <line x1="9" y1="11" x2="15" y2="11" />
          <line x1="9" y1="15" x2="15" y2="15" />
        </svg>
        {{ message.template }}
      </div>
      <img v-if="message.content_type === 'image' && message.attach" :src="message.attach" class="wn-bubble-image" />
      <audio v-else-if="message.content_type === 'audio' && message.attach" :src="message.attach" controls class="wn-bubble-audio" />
      <video v-else-if="message.content_type === 'video' && message.attach" :src="message.attach" controls class="wn-bubble-video" />
      <a v-else-if="message.attach" :href="message.attach" target="_blank" class="wn-bubble-doc">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
        {{ message.attach.split('/').pop() }}
      </a>
      <div class="wn-bubble-content">
        <p v-if="message.message">
          <template v-for="(seg, i) in segments" :key="i">
            <a v-if="seg.href" :href="seg.href" target="_blank" rel="noopener" class="wn-bubble-link">{{ seg.href.includes('maps.google.com') ? 'Open in Maps' : seg.text }}</a>
            <template v-else>{{ seg.text }}</template>
          </template>
        </p>
        <p v-if="message.type === 'Outgoing' && message.status === 'Failed' && message.error_message" class="wn-bubble-error">
          Not delivered: {{ message.error_message }}
        </p>
        <div class="wn-bubble-meta">
          <button type="button" class="wn-bubble-reply" title="Reply" @click="emit('reply', message)">↩</button>
          <span v-if="message.is_automated" title="Sent automatically">⚙</span>
          <span>{{ parseFrappeDate(message.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</span>
          <span v-if="message.type === 'Outgoing'" :class="{ read: message.status === 'Read' }" :title="message.status">{{ statusIcon[message.status] || '' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-bubble-row { display: flex; margin: 4px 0; }
.wn-bubble-row.out { justify-content: flex-end; }
.wn-bubble-row.in { justify-content: flex-start; }
.wn-bubble {
  max-width: 65%;
  padding: 0;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.4;
  box-shadow: var(--wn-shadow);
  overflow: hidden;
}
.wn-bubble-row.out .wn-bubble { background: var(--wn-teal-light); border-bottom-right-radius: 4px; }
.wn-bubble-row.in .wn-bubble { background: white; border-bottom-left-radius: 4px; }
.wn-bubble-content { padding: 8px 12px; }
.wn-bubble p { margin: 2px 0; white-space: pre-wrap; word-break: break-word; }
.wn-bubble-quote { display: block; width: calc(100% - 12px); margin: 6px 6px 0; text-align: left; background: rgba(15, 61, 62, 0.06); border: none; border-left: 3px solid var(--wn-teal); border-radius: 6px; padding: 5px 8px; font-size: 12px; color: var(--wn-text-muted); cursor: pointer; }
.wn-bubble-quote strong { display: block; color: var(--wn-teal); font-size: 11.5px; }
.wn-bubble-quote span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.wn-bubble-template { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--wn-teal); font-weight: 600; margin-bottom: 2px; padding: 8px 12px 0; }
.wn-bubble-image { width: 100%; max-width: 280px; display: block; }
.wn-bubble-audio { width: 260px; max-width: 100%; display: block; margin: 8px 12px 0; }
.wn-bubble-video { width: 100%; max-width: 280px; display: block; }
.wn-bubble-doc { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--wn-blue); padding: 8px 12px; }
.wn-bubble-doc svg, .wn-bubble-template svg { flex-shrink: 0; }
.wn-bubble-link { color: var(--wn-blue); word-break: break-all; }
.wn-bubble-error { font-size: 11.5px; color: var(--wn-red) !important; }
.wn-bubble-meta { display: flex; gap: 4px; justify-content: flex-end; align-items: center; font-size: 10px; color: var(--wn-text-muted); margin-top: 2px; }
.wn-bubble-meta .read { color: var(--wn-blue); }
.wn-bubble-reply { background: none; border: none; padding: 0 4px; color: var(--wn-text-muted); font-size: 12px; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
.wn-bubble:hover .wn-bubble-reply, .wn-bubble-reply:focus { opacity: 1; }
@media (hover: none) { .wn-bubble-reply { opacity: 0.7; } }
@media (max-width: 768px) { .wn-bubble { max-width: 85%; } }
</style>
