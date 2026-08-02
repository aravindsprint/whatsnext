<script setup>
import { computed } from 'vue'

const props = defineProps({
  points: { type: Array, required: true }, // [{ label, value }]
  color: { type: String, default: 'var(--wn-teal)' },
})

const W = 320
const H = 120
const PAD = 16

const path = computed(() => {
  if (!props.points.length) return ''
  const max = Math.max(...props.points.map((p) => p.value), 1)
  const step = (W - PAD * 2) / Math.max(props.points.length - 1, 1)
  return props.points
    .map((p, i) => {
      const x = PAD + i * step
      const y = H - PAD - (p.value / max) * (H - PAD * 2)
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
})

const dots = computed(() => {
  if (!props.points.length) return []
  const max = Math.max(...props.points.map((p) => p.value), 1)
  const step = (W - PAD * 2) / Math.max(props.points.length - 1, 1)
  return props.points.map((p, i) => ({
    x: PAD + i * step,
    y: H - PAD - (p.value / max) * (H - PAD * 2),
    label: p.label,
    value: p.value,
  }))
})
</script>

<template>
  <svg :viewBox="`0 0 ${W} ${H + 16}`" width="100%" style="max-width: 360px">
    <path :d="path" fill="none" :stroke="color" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
    <circle v-for="(d, i) in dots" :key="i" :cx="d.x" :cy="d.y" r="3" :fill="color" />
    <text v-for="(d, i) in dots" :key="'l' + i" :x="d.x" :y="H + 14" text-anchor="middle" font-size="9" fill="var(--wn-text-muted)">
      {{ d.label }}
    </text>
  </svg>
</template>
