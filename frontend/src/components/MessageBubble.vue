<script setup>
const props = defineProps({ message: Object })

const statusIcon = { Sent: '✓', Delivered: '✓✓', Read: '✓✓', Failed: '⚠️', Pending: '🕒', Queued: '🕒' }
</script>

<template>
  <div class="wn-bubble-row" :class="message.type === 'Outgoing' ? 'out' : 'in'">
    <div class="wn-bubble">
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
        <p v-if="message.message">{{ message.message }}</p>
        <div class="wn-bubble-meta">
          <span>{{ new Date(message.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</span>
          <span v-if="message.type === 'Outgoing'" :class="{ read: message.status === 'Read' }">{{ statusIcon[message.status] || '' }}</span>
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
.wn-bubble-template { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--wn-teal); font-weight: 600; margin-bottom: 2px; padding: 8px 12px 0; }
.wn-bubble-image { width: 100%; max-width: 280px; display: block; }
.wn-bubble-audio { width: 260px; display: block; margin: 8px 12px 0; }
.wn-bubble-video { width: 100%; max-width: 280px; display: block; }
.wn-bubble-doc { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--wn-blue); padding: 8px 12px; }
.wn-bubble-doc svg, .wn-bubble-template svg { flex-shrink: 0; }
.wn-bubble-meta { display: flex; gap: 4px; justify-content: flex-end; font-size: 10px; color: var(--wn-text-muted); margin-top: 2px; }
.wn-bubble-meta .read { color: var(--wn-blue); }
</style>
