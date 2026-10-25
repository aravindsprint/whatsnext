import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/frappe', () => ({ call: vi.fn() }))

import { call } from '@/api/frappe'
import {
  aiCredits, createSalesOrder, extractOrder, formatCredits, improveDraft, loadReplyOptions, orderProblems,
  requestSuggestions, retagChat, searchItems, summarizeChat, summaryNote, translateText,
} from '../aiReplies'

const ext = { options: 'addon.api.get_reply_options', suggest: 'addon.api.suggest_replies' }

describe('aiReplies', () => {
  beforeEach(() => call.mockReset())

  it('loads options from the extension method with GET', async () => {
    call.mockResolvedValue({ models: [{ tier: 'Fast' }], default_model: 'Fast', credits_available: 0, plan: 'Pro' })
    const opts = await loadReplyOptions(ext)
    expect(call).toHaveBeenCalledWith('addon.api.get_reply_options', {}, 'GET')
    expect(opts).toEqual({
      models: [{ tier: 'Fast' }], defaultModel: 'Fast', credits: 0, plan: 'Pro', features: {}, agentLanguage: 'English',
    })
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

  it('improves a draft and keeps the shared credit balance current', async () => {
    aiCredits.value = 50
    call.mockResolvedValue({ text: ' Could you share your order number, please? ', credits_remaining: 49.8 })
    const text = await improveDraft({ improve: 'addon.improve' }, { conversationId: '91', text: 'send order no', style: 'polite' })
    expect(call).toHaveBeenCalledWith('addon.improve', { conversation_id: '91', text: 'send order no', style: 'polite' })
    expect(text).toBe('Could you share your order number, please?')
    expect(aiCredits.value).toBe(49.8)
  })

  it('keeps the balance when a reply has none (own-key plans, cached translations)', async () => {
    aiCredits.value = 12
    call.mockResolvedValue({ text: 'When will it come?', language: 'English', credits_remaining: null })
    const res = await translateText({ translate: 'addon.translate' }, { conversationId: '91', text: 'Eppo varum?', to: 'agent' })
    expect(call).toHaveBeenCalledWith('addon.translate', { conversation_id: '91', text: 'Eppo varum?', to: 'agent' })
    expect(res).toEqual({ text: 'When will it come?', language: 'English' })
    expect(aiCredits.value).toBe(12)
  })

  it('summarises a chat and turns it into a note', async () => {
    call.mockResolvedValue({ summary: 'Ravi wants a date.', open_items: ['Dispatch date', ''], next_step: 'Reply today' })
    const s = await summarizeChat({ summarize: 'addon.sum' }, '91')
    expect(s).toEqual({ summary: 'Ravi wants a date.', openItems: ['Dispatch date'], nextStep: 'Reply today' })
    expect(summaryNote(s)).toBe('AI summary: Ravi wants a date.\nOpen: Dispatch date\nNext: Reply today')
    expect(summaryNote({ summary: 'Done.', openItems: [], nextStep: '' })).toBe('AI summary: Done.')
  })

  it('reads an order into editable lines', async () => {
    call.mockResolvedValue({
      customer: 'CUST-1', customer_name: 'Ravi Textiles', delivery_date: '2026-11-01', notes: 'Tirupur',
      items: [{ item_code: 'YARN-40S', item_name: 'Cotton Yarn 40s', description: '40s yarn', qty: 200, uom: 'Kg', rate: null, match: 'exact' },
              { item_code: null, description: 'silk', qty: null, match: 'none' }],
    })
    const order = await extractOrder({ extract: 'addon.extract' }, '91')
    expect(order.lines[0]).toEqual({ itemCode: 'YARN-40S', itemName: 'Cotton Yarn 40s', description: '40s yarn', qty: 200, uom: 'Kg', rate: '', match: 'exact' })
    expect(order.lines[1]).toMatchObject({ itemCode: '', qty: '', match: 'none' })
    expect(order.deliveryDate).toBe('2026-11-01')
  })

  it('lists what to fix before an order can be saved', () => {
    expect(orderProblems([])).toEqual(['Add at least one item.'])
    expect(orderProblems([
      { itemCode: '', qty: 1, rate: '' },
      { itemCode: 'A', qty: '', rate: '' },
      { itemCode: 'B', qty: 2, rate: -1 },
      { itemCode: 'C', qty: 2, rate: '' },
    ])).toEqual(['Line 1: choose an item.', 'Line 2: enter a quantity.', "Line 3: the rate can't be negative."])
  })

  it('sends the checked lines to create the draft order', async () => {
    call.mockResolvedValue({ name: 'SO-1' })
    await createSalesOrder({ create: 'addon.create' }, {
      conversationId: '91', deliveryDate: '2026-11-01', notes: '  ',
      lines: [{ itemCode: 'A', qty: '2', uom: 'Kg', rate: '' }, { itemCode: 'B', qty: 1, uom: '', rate: '9.5' }],
    })
    const [method, args] = call.mock.calls[0]
    expect(method).toBe('addon.create')
    expect(JSON.parse(args.items)).toEqual([{ item_code: 'A', qty: 2, uom: 'Kg' }, { item_code: 'B', qty: 1, rate: 9.5 }])
    expect(args).toMatchObject({ conversation_id: '91', delivery_date: '2026-11-01', notes: undefined })
  })

  it("doesn't search items for an empty box", async () => {
    expect(await searchItems({ search_items: 'addon.search' }, '  ')).toEqual([])
    expect(call).not.toHaveBeenCalled()
    call.mockResolvedValue([{ item_code: 'A' }])
    expect(await searchItems({ search_items: 'addon.search' }, ' yarn ')).toEqual([{ item_code: 'A' }])
    expect(call).toHaveBeenCalledWith('addon.search', { txt: 'yarn' }, 'GET')
  })

  it('re-labels a chat', async () => {
    call.mockResolvedValue({ labels: [{ text: 'Order' }], credits_remaining: 3 })
    expect(await retagChat({ retag: 'addon.retag' }, '91')).toEqual([{ text: 'Order' }])
  })
})
