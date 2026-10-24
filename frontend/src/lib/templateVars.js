// Inputs a template needs at send time, as [{ key, label, placeholder }].
// Keys match what the backend expects (see provider_engine.split_template_params):
//   "1", "2"…     body {{n}}
//   "header_1"    {{1}} in a text header
//   "button_<i>"  {{1}} suffix of the URL button at index i
export function templateInputs(t) {
  if (!t) return []
  let samples = {}
  try {
    samples = typeof t.variables_sample === 'string' ? JSON.parse(t.variables_sample || '{}') : (t.variables_sample || {})
  } catch {
    samples = {}
  }
  const inputs = []
  if (t.header_type === 'Text' && (t.header_text || '').includes('{{1}}')) {
    inputs.push({ key: 'header_1', label: 'Header variable', placeholder: t.header_text })
  }
  const nums = [...(t.body || '').matchAll(/\{\{(\d+)\}\}/g)].map((m) => parseInt(m[1], 10))
  const count = nums.length ? Math.max(...nums) : 0
  for (let i = 1; i <= count; i++) {
    inputs.push({ key: String(i), label: `Variable {{${i}}}`, placeholder: samples[String(i)] || '' })
  }
  for (const b of t.buttons || []) {
    if (b.type === 'URL' && (b.value || '').includes('{{1}}')) {
      inputs.push({ key: `button_${b.index}`, label: `Link for “${b.text}”`, placeholder: b.value })
    }
  }
  return inputs
}

export function needsHeaderMedia(t) {
  return !!t && ['Image', 'Video', 'Document'].includes(t.header_type)
}

// <input type="datetime-local"> value -> "YYYY-MM-DD HH:MM:SS" (site-local,
// which is how Frappe stores datetimes).
export function toFrappeDatetime(localValue) {
  if (!localValue) return null
  return localValue.replace('T', ' ') + (localValue.length === 16 ? ':00' : '')
}
