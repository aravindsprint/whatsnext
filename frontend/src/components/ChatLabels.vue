<script setup>
// Chips an add-on puts on a chat (e.g. AI labels: Order, Urgent, Angry).
defineProps({ labels: { type: Array, default: () => [] } })
</script>

<template>
  <span v-if="labels.length" class="wn-labels">
    <span v-for="(l, i) in labels" :key="i" class="wn-label" :class="l.tone || 'gray'" :title="l.title || ''">{{ l.text }}</span>
  </span>
</template>

<style scoped>
.wn-labels { display: inline-flex; flex-wrap: wrap; gap: 4px; vertical-align: middle; }
.wn-label { font-size: 10.5px; font-weight: 600; line-height: 1; padding: 3px 7px; border-radius: 9px; white-space: nowrap; }
.wn-label.teal { background: var(--wn-teal-light); color: #0b7a6e; }
.wn-label.gray { background: var(--wn-bg); color: var(--wn-text-muted); }
.wn-label.orange { background: #fff4e0; color: #9a5b00; }
.wn-label.red { background: #fde8e8; color: #b42318; }
.wn-label.green { background: #e7f8ee; color: #15803d; }
</style>
