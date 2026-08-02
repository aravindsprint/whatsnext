<script setup>
const props = defineProps({ message: Object })

const statusIcon = { Sent: '✓', Delivered: '✓✓', Read: '✓✓', Failed: '⚠️', Pending: '🕒', Queued: '🕒' }
</script>

<template>
  <div class="wn-bubble-row" :class="message.type === 'Outgoing' ? 'out' : 'in'">
    <div class="wn-bubble">
      <div v-if="message.template" class="wn-bubble-template">📋 {{ message.template }}</div>
      <img v-if="message.content_type === 'image' && message.attach" :src="message.attach" class="wn-bubble-image" />
      <a v-else-if="message.attach" :href="message.attach" target="_blank" class="wn-bubble-doc">📎 {{ message.attach.split('/').pop() }}</a>
      <p v-if="message.message">{{ message.message }}</p>
      <div class="wn-bubble-meta">
        <span>{{ new Date(message.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</span>
        <span v-if="message.type === 'Outgoing'" :class="{ read: message.status === 'Read' }">{{ statusIcon[message.status] || '' }}</span>
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
  padding: 8px 12px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.4;
  box-shadow: var(--wn-shadow);
}
.wn-bubble-row.out .wn-bubble { background: var(--wn-teal-light); border-bottom-right-radius: 4px; }
.wn-bubble-row.in .wn-bubble { background: white; border-bottom-left-radius: 4px; }
.wn-bubble p { margin: 2px 0; white-space: pre-wrap; word-break: break-word; }
.wn-bubble-template { font-size: 11px; color: var(--wn-teal); font-weight: 600; margin-bottom: 2px; }
.wn-bubble-image { max-width: 220px; border-radius: 8px; display: block; margin-bottom: 4px; }
.wn-bubble-doc { display: block; font-size: 13px; color: var(--wn-blue); margin-bottom: 4px; }
.wn-bubble-meta { display: flex; gap: 4px; justify-content: flex-end; font-size: 10px; color: var(--wn-text-muted); margin-top: 2px; }
.wn-bubble-meta .read { color: var(--wn-blue); }
</style>
