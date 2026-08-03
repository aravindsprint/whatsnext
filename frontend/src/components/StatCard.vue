<script setup>
defineProps({
  label: String,
  value: [String, Number],
  icon: { type: String, default: '📨' },
  tone: { type: String, default: 'teal' }, // teal | red | amber | blue
})
</script>

<template>
  <div class="wn-stat-card" :class="tone">
    <div class="wn-stat-icon">{{ icon }}</div>
    <div>
      <div class="wn-stat-value">{{ value }}</div>
      <div class="wn-stat-label">{{ label }}</div>
    </div>
  </div>
</template>

<style scoped>
.wn-stat-card {
  background: white;
  border-radius: var(--wn-radius);
  box-shadow: var(--wn-shadow);
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
}
.wn-stat-icon {
  width: 40px; height: 40px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
  background: var(--wn-teal-light);
}
.wn-stat-card.red .wn-stat-icon { background: #fee2e2; }
.wn-stat-card.amber .wn-stat-icon { background: #fef3c7; }
.wn-stat-card.blue .wn-stat-icon { background: #dbeafe; }
.wn-stat-value { font-size: 22px; font-weight: 700; color: var(--wn-navy); line-height: 1.1; }
.wn-stat-label { font-size: 12px; color: var(--wn-text-muted); margin-top: 2px; }
</style>
