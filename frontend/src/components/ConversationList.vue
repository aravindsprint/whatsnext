<script setup>
defineProps({ conversations: Array, activeId: String })
const emit = defineEmits(['select'])
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
      <div class="wn-avatar">{{ (c.profile_name || c.to_number || '?').charAt(0).toUpperCase() }}</div>
      <div class="wn-conv-body">
        <div class="wn-conv-top">
          <span class="wn-conv-name">{{ c.profile_name || c.to_number || c.from_number }}</span>
          <span class="wn-conv-time">{{ new Date(c.modified).toLocaleDateString() }}</span>
        </div>
        <div class="wn-conv-preview">
          <span>{{ c.message || '📎 Media' }}</span>
          <span v-if="c.is_unread" class="wn-unread-dot"></span>
        </div>
      </div>
    </div>
    <div v-if="!conversations.length" class="wn-empty">No conversations yet</div>
  </div>
</template>

<style scoped>
.wn-conv-list { display: flex; flex-direction: column; overflow-y: auto; height: 100%; }
.wn-conv-item { display: flex; gap: 10px; padding: 12px 14px; cursor: pointer; border-bottom: 1px solid var(--wn-border); }
.wn-conv-item:hover, .wn-conv-item.active { background: var(--wn-teal-light); }
.wn-avatar {
  width: 40px; height: 40px; border-radius: 50%; background: var(--wn-navy); color: white;
  display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0;
}
.wn-conv-body { min-width: 0; flex: 1; }
.wn-conv-top { display: flex; justify-content: space-between; gap: 8px; }
.wn-conv-name { font-weight: 600; font-size: 14px; }
.wn-conv-time { font-size: 11px; color: var(--wn-text-muted); flex-shrink: 0; }
.wn-conv-preview { display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: 12.5px; color: var(--wn-text-muted); }
.wn-conv-preview span:first-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-conv-item.unread .wn-conv-name { font-weight: 700; }
.wn-conv-item.unread .wn-conv-preview span:first-child { color: var(--wn-text, #222); font-weight: 600; }
.wn-unread-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--wn-teal); flex-shrink: 0; }
.wn-empty { padding: 24px; text-align: center; color: var(--wn-text-muted); font-size: 13px; }
</style>
