import { call } from '@/api/frappe'

// Talks to whichever installed app provides the "smart_replies" extension
// (see whatsnext_extensions in hooks.py). `ext` is that entry from whoami:
// { options: '<method>', suggest: '<method>' }.

export async function loadReplyOptions(ext) {
  const res = await call(ext.options, {}, 'GET')
  return {
    models: res?.models || [],
    defaultModel: res?.default_model || '',
    credits: res?.credits_available ?? null,
    plan: res?.plan || '',
  }
}

export async function requestSuggestions(ext, { conversationId, model, instruction }) {
  const res = await call(ext.suggest, {
    conversation_id: conversationId,
    model: model || undefined,
    instruction: (instruction || '').trim() || undefined,
  })
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
