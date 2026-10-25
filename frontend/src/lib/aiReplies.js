import { ref } from 'vue'
import { call } from '@/api/frappe'

// Talks to whichever installed app provides the AI extensions (see
// whatsnext_extensions in hooks.py). Each `ext` is that feature's entry from
// whoami, e.g. smart_replies: { options: '<method>', suggest: '<method>' }.

// Credits left, shared by every AI panel and updated after each request.
// null: unknown, or the plan is paid to the customer's own AI account.
export const aiCredits = ref(null)

function noteCredits(res) {
  const value = res?.credits_remaining
  if (value !== null && value !== undefined) aiCredits.value = value
}

export async function loadReplyOptions(ext) {
  const res = await call(ext.options, {}, 'GET')
  return {
    models: res?.models || [],
    defaultModel: res?.default_model || '',
    credits: res?.credits_available ?? null,
    plan: res?.plan || '',
    features: res?.features || {},
    agentLanguage: res?.agent_language || 'English',
  }
}

export async function requestSuggestions(ext, { conversationId, model, instruction }) {
  const res = await call(ext.suggest, {
    conversation_id: conversationId,
    model: model || undefined,
    instruction: (instruction || '').trim() || undefined,
  })
  noteCredits(res)
  return {
    suggestions: (res?.suggestions || []).filter((s) => typeof s === 'string' && s.trim()),
    model: res?.model || '',
    credits: res?.credits_remaining ?? null,
  }
}

export function formatCredits(value) {
  if (value === null || value === undefined) return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  return n >= 100 ? Math.floor(n).toLocaleString() : n.toFixed(1)
}

// Improve my reply: style is one of IMPROVE_STYLES' keys.
export const IMPROVE_STYLES = [
  ['fix', 'Fix grammar'],
  ['polite', 'More polite'],
  ['shorter', 'Shorter'],
  ['friendly', 'Friendlier'],
  ['formal', 'More formal'],
]

export async function improveDraft(ext, { conversationId, text, style }) {
  const res = await call(ext.improve, { conversation_id: conversationId, text, style })
  noteCredits(res)
  return (res?.text || '').trim()
}

// to: 'agent' (a customer's message into the team's language) or
// 'customer' (the agent's draft into the language the customer writes in).
export async function translateText(ext, { conversationId, text, to }) {
  const res = await call(ext.translate, { conversation_id: conversationId, text, to })
  noteCredits(res)
  return { text: (res?.text || '').trim(), language: res?.language || '' }
}

export async function summarizeChat(ext, conversationId) {
  const res = await call(ext.summarize, { conversation_id: conversationId })
  noteCredits(res)
  return {
    summary: res?.summary || '',
    openItems: (res?.open_items || []).filter((i) => typeof i === 'string' && i.trim()),
    nextStep: res?.next_step || '',
  }
}

// Summary as a team note for the chat.
export function summaryNote({ summary, openItems, nextStep }) {
  const lines = ['AI summary: ' + summary]
  if (openItems?.length) lines.push('Open: ' + openItems.join('; '))
  if (nextStep) lines.push('Next: ' + nextStep)
  return lines.join('\n')
}

export async function extractOrder(ext, conversationId) {
  const res = await call(ext.extract, { conversation_id: conversationId })
  noteCredits(res)
  return {
    customer: res?.customer || '',
    customerName: res?.customer_name || '',
    lines: (res?.items || []).map((l) => ({
      itemCode: l.item_code || '',
      itemName: l.item_name || '',
      description: l.description || '',
      qty: l.qty ?? '',
      uom: l.uom || '',
      rate: l.rate ?? '',
      match: l.match || 'none',
    })),
    deliveryDate: res?.delivery_date || '',
    notes: res?.notes || '',
  }
}

export async function searchItems(ext, txt) {
  if (!(txt || '').trim()) return []
  const res = await call(ext.search_items, { txt: txt.trim() }, 'GET')
  return Array.isArray(res) ? res : []
}

// Problems to fix before saving, by line (1-based), or [] when ready.
export function orderProblems(lines) {
  if (!lines.length) return ['Add at least one item.']
  const problems = []
  lines.forEach((l, i) => {
    if (!l.itemCode) problems.push(`Line ${i + 1}: choose an item.`)
    else if (!(Number(l.qty) > 0)) problems.push(`Line ${i + 1}: enter a quantity.`)
    else if (l.rate !== '' && l.rate !== null && Number(l.rate) < 0) problems.push(`Line ${i + 1}: the rate can't be negative.`)
  })
  return problems
}

export async function createSalesOrder(ext, { conversationId, lines, deliveryDate, notes }) {
  return call(ext.create, {
    conversation_id: conversationId,
    items: JSON.stringify(lines.map((l) => ({
      item_code: l.itemCode,
      qty: Number(l.qty),
      uom: l.uom || undefined,
      rate: l.rate === '' || l.rate === null ? undefined : Number(l.rate),
    }))),
    delivery_date: deliveryDate || undefined,
    notes: (notes || '').trim() || undefined,
  })
}

export async function retagChat(ext, conversationId) {
  const res = await call(ext.retag, { conversation_id: conversationId })
  noteCredits(res)
  return res?.labels || []
}
