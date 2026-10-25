import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/frappe', () => ({ call: vi.fn() }))

import { call } from '@/api/frappe'
import { formatCredits, loadReplyOptions, requestSuggestions } from '../aiReplies'

const ext = { options: 'addon.api.get_reply_options', suggest: 'addon.api.suggest_replies' }

describe('aiReplies', () => {
  beforeEach(() => call.mockReset())

  it('loads options from the extension method with GET', async () => {
    call.mockResolvedValue({ models: [{ tier: 'Fast' }], default_model: 'Fast', credits_available: 0, plan: 'Pro' })
    const opts = await loadReplyOptions(ext)
    expect(call).toHaveBeenCalledWith('addon.api.get_reply_options', {}, 'GET')
    expect(opts).toEqual({ models: [{ tier: 'Fast' }], defaultModel: 'Fast', credits: 0, plan: 'Pro' })
  })

  it('requests suggestions and drops empty ones', async () => {
    call.mockResolvedValue({ suggestions: ['Hi', '  ', 'Thanks'], model: 'Fast', credits_remaining: 41.5 })
    const res = await requestSuggestions(ext, { conversationId: '919876543210', model: 'Smart', instruction: '  say sorry ' })
    expect(call).toHaveBeenCalledWith('addon.api.suggest_replies', {
      conversation_id: '919876543210', model: 'Smart', instruction: 'say sorry',
    })
    expect(res).toEqual({ suggestions: ['Hi', 'Thanks'], model: 'Fast', credits: 41.5 })
  })

  it('leaves out an empty instruction and model', async () => {
    call.mockResolvedValue({})
    const res = await requestSuggestions(ext, { conversationId: '91', model: '', instruction: '   ' })
    expect(call.mock.calls[0][1]).toEqual({ conversation_id: '91', model: undefined, instruction: undefined })
    expect(res).toEqual({ suggestions: [], model: '', credits: null })
  })

  it('formats credits', () => {
    expect(formatCredits(null)).toBe('')
    expect(formatCredits(12.34)).toBe('12.3')
    expect(formatCredits(25000.9)).toBe((25000).toLocaleString())
  })
})
