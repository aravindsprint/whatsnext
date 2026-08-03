<script setup>
defineProps({ compact: { type: Boolean, default: false } })
</script>

<template>
  <div class="wn-logo">
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="8" fill="var(--wn-teal)" />
      <path d="M8 10a6 6 0 1 1 2.1 8.9L8 20l1.1-2.9A6 6 0 0 1 8 10Z" stroke="white" stroke-width="1.6" fill="none" />
    </svg>
    <span v-if="!compact" class="wn-logo-text">Whatsnext</span>
  </div>
</template>

<style scoped>
.wn-logo { display: flex; align-items: center; gap: 8px; }
.wn-logo-text { font-weight: 700; font-size: 18px; color: var(--wn-navy); }
</style>
