<script setup>
import { parseFrappeDate } from '@/lib/date'
import ChatLabels from '@/components/ChatLabels.vue'

defineProps({ conversations: Array, activeId: String, hasMore: Boolean, loadingMore: Boolean })
const emit = defineEmits(['select', 'load-more'])

function initials(user) {
  return (user || '').split('@')[0].split(/[._-]/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('')
}

function formatTime(value) {
  const d = parseFrappeDate(value)
  if (isNaN(d)) return ''
  const today = new Date()
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString()
}
</script>

<template>
  <div class="wn-conv-list">
    <div
      v-for="c in conversations"
      :key="c.conversation_id || c.name"
      class="wn-conv-item"
      :class="{ active: (c.conversation_id || c.name) === activeId, unread: c.is_unread }"
      @click="emit('select', c.conversation_id || c.name)"
    >
      <div class="wn-avatar">{{ (c.profile_name || c.conversation_id || '?').charAt(0).toUpperCase() }}</div>
      <div class="wn-conv-body">
        <div class="wn-conv-top">
          <span class="wn-conv-name">{{ c.profile_name || c.conversation_id || c.to_number || c.from_number }}</span>
          <span class="wn-conv-time">{{ formatTime(c.modified) }}</span>
        </div>
        <div class="wn-conv-preview">
          <span>{{ c.message || '📎 Media' }}</span>
          <span v-if="c.assigned_to" class="wn-assignee" :title="'Assigned to ' + c.assigned_to">{{ initials(c.assigned_to) }}</span>
          <span v-if="c.is_unread" class="wn-unread-dot"></span>
        </div>
        <ChatLabels v-if="c.labels?.length" :labels="c.labels" class="wn-conv-labels" />
      </div>
    </div>
    <div v-if="hasMore" class="wn-load-more">
      <button type="button" :disabled="loadingMore" @click="emit('load-more')">{{ loadingMore ? 'Loading…' : 'Load more chats' }}</button>
    </div>
    <div v-if="!conversations.length" class="wn-empty">No conversations yet</div>
  </div>
</template>

<style scoped>
.wn-conv-list { display: flex; flex-direction: column; overflow-y: auto; flex: 1; min-height: 0; }
.wn-conv-item { display: flex; gap: 10px; padding: 12px 14px; cursor: pointer; border-bottom: 1px solid var(--wn-border); }
.wn-conv-item:hover, .wn-conv-item.active { background: var(--wn-teal-light); }
.wn-avatar {
  width: 40px; height: 40px; border-radius: 50%; background: var(--wn-navy); color: white;
  display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0;
}
.wn-conv-body { min-width: 0; flex: 1; }
.wn-conv-labels { margin-top: 4px; }
.wn-conv-top { display: flex; justify-content: space-between; gap: 8px; }
.wn-conv-name { font-weight: 600; font-size: 14px; }
.wn-conv-time { font-size: 11px; color: var(--wn-text-muted); flex-shrink: 0; }
.wn-conv-preview { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 12.5px; color: var(--wn-text-muted); }
.wn-conv-preview span:first-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-conv-item.unread .wn-conv-name { font-weight: 700; }
.wn-conv-item.unread .wn-conv-preview span:first-child { color: var(--wn-text, #222); font-weight: 600; }
.wn-unread-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--wn-teal); flex-shrink: 0; }
.wn-empty { padding: 24px; text-align: center; color: var(--wn-text-muted); font-size: 13px; }
.wn-assignee { font-size: 9.5px; font-weight: 700; background: var(--wn-teal-light); color: #0f8c72; border-radius: 999px; padding: 1px 5px; flex-shrink: 0; }
.wn-load-more { display: flex; justify-content: center; padding: 10px; }
.wn-load-more button { background: var(--wn-bg); border: 1px solid var(--wn-border); border-radius: 8px; padding: 7px 14px; font-size: 12.5px; color: var(--wn-text-muted); }
</style>
