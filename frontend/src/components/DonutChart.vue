<script setup>
import { computed } from 'vue'

const props = defineProps({
  segments: {
    // [{ label, value, color }]
    type: Array,
    required: true,
  },
  centerLabel: { type: String, default: '' },
  centerValue: { type: String, default: '' },
})

const total = computed(() => props.segments.reduce((s, seg) => s + seg.value, 0) || 1)

const arcs = computed(() => {
  const r = 42
  const circumference = 2 * Math.PI * r
  let offset = 0
  return props.segments.map((seg) => {
    const fraction = seg.value / total.value
    const dash = fraction * circumference
    const arc = {
      ...seg,
      dashArray: `${dash} ${circumference - dash}`,
      dashOffset: -offset,
    }
    offset += dash
    return arc
  })
})
</script>

<template>
  <div class="wn-donut">
    <svg viewBox="0 0 100 100" width="120" height="120">
      <circle cx="50" cy="50" r="42" fill="none" stroke="#eef2f2" stroke-width="12" />
      <circle
        v-for="(arc, i) in arcs"
        :key="i"
        cx="50" cy="50" r="42" fill="none"
        :stroke="arc.color" stroke-width="12"
        :stroke-dasharray="arc.dashArray"
        :stroke-dashoffset="arc.dashOffset"
        transform="rotate(-90 50 50)"
        stroke-linecap="round"
      />
      <text x="50" y="47" text-anchor="middle" font-size="16" font-weight="700" fill="var(--wn-navy)">{{ centerValue }}</text>
      <text x="50" y="60" text-anchor="middle" font-size="7" fill="var(--wn-text-muted)">{{ centerLabel }}</text>
    </svg>
    <ul class="wn-donut-legend">
      <li v-for="(seg, i) in segments" :key="i">
        <span class="dot" :style="{ background: seg.color }"></span>
        {{ seg.label }} <strong>{{ seg.value }}</strong>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.wn-donut { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.wn-donut-legend { list-style: none; margin: 0; padding: 0; font-size: 13px; display: flex; flex-direction: column; gap: 6px; }
.wn-donut-legend .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
</style>
