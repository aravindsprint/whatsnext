<script setup>
import { computed, ref, watch } from 'vue'
import { templateInputs, needsHeaderMedia, toFrappeDatetime } from '@/lib/templateVars'

const props = defineProps({
  template: { type: Object, required: true },
  sending: Boolean,
  allowSchedule: { type: Boolean, default: true },
  submitLabel: { type: String, default: 'Send' },
})
const emit = defineEmits(['back', 'send'])

const inputs = computed(() => templateInputs(props.template))
const values = ref({})
const headerMediaUrl = ref('')
const scheduleOn = ref(false)
const scheduleAt = ref('')
const localError = ref(null)

watch(
  () => props.template,
  (t) => {
    values.value = Object.fromEntries(templateInputs(t).map((i) => [i.key, '']))
    headerMediaUrl.value = t?.header_example_url || ''
    scheduleOn.value = false
    scheduleAt.value = ''
    localError.value = null
  },
  { immediate: true }
)

function submit() {
  localError.value = null
  if (needsHeaderMedia(props.template) && !headerMediaUrl.value.trim()) {
    localError.value = `This template has a ${props.template.header_type} header — a media URL is required.`
    return
  }
  const missing = inputs.value.find((i) => !String(values.value[i.key] || '').trim())
  if (missing) {
    localError.value = `Fill in “${missing.label}” — WhatsApp rejects templates with empty variables.`
    return
  }
  if (scheduleOn.value && !scheduleAt.value) {
    localError.value = 'Pick a date and time, or turn off scheduling.'
    return
  }
  emit('send', {
    parameters: { ...values.value },
    headerMediaUrl: needsHeaderMedia(props.template) ? headerMediaUrl.value.trim() : undefined,
    scheduledTime: scheduleOn.value ? toFrappeDatetime(scheduleAt.value) : undefined,
  })
}
</script>

<template>
  <div class="wn-tsf">
    <p class="wn-tsf-body">{{ template.body }}</p>
    <div v-if="needsHeaderMedia(template)" class="wn-tsf-field">
      <label>{{ template.header_type }} header URL (public link)</label>
      <input v-model="headerMediaUrl" type="text" placeholder="https://example.com/file" />
    </div>
    <div v-for="i in inputs" :key="i.key" class="wn-tsf-field">
      <label>{{ i.label }}</label>
      <input v-model="values[i.key]" type="text" :placeholder="i.placeholder" />
    </div>
    <div v-if="allowSchedule" class="wn-tsf-field">
      <label class="wn-tsf-check"><input v-model="scheduleOn" type="checkbox" /> Schedule for later</label>
      <input v-if="scheduleOn" v-model="scheduleAt" type="datetime-local" />
    </div>
    <p v-if="localError" class="wn-error">{{ localError }}</p>
    <div class="wn-modal-actions">
      <button class="ghost" type="button" @click="emit('back')">Back</button>
      <button class="primary" type="button" :disabled="sending" @click="submit">
        {{ sending ? 'Sending…' : (scheduleOn ? 'Schedule' : submitLabel) }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.wn-tsf-body { white-space: pre-wrap; background: var(--wn-bg); padding: 10px 12px; border-radius: 8px; font-size: 13px; }
.wn-tsf-field label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 10px 0 4px; }
.wn-tsf-field input[type="text"], .wn-tsf-field input[type="datetime-local"] { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; box-sizing: border-box; }
.wn-tsf-check { display: flex !important; align-items: center; gap: 6px; font-weight: 500 !important; }
.wn-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.wn-error { color: var(--wn-red); font-size: 13px; }
</style>
