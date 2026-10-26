import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/frappe', () => ({ call: vi.fn() }))

import { call } from '@/api/frappe'
import { choiceFor, finishCheckout, formatDate, loadBilling, money, paymentLabel, quoteBilling, upgradeNow } from '../aiBilling'

const ext = { overview: 'addon.overview', quote: 'addon.quote', start: 'addon.start', finish: 'addon.finish' }

describe('aiBilling', () => {
  beforeEach(() => call.mockReset())

  it('turns the form into a purchase', () => {
    expect(choiceFor({ action: 'renew', plan: 'Pro', months: '3', credits: 5000 })).toEqual({ plan: null, months: 3, credits: 0 })
    expect(choiceFor({ action: 'change', plan: 'Pro', months: 0, credits: 5000 })).toEqual({ plan: 'Pro', months: 0, credits: 0 })
    expect(choiceFor({ action: 'credits', plan: 'Pro', months: 3, credits: '10000' })).toEqual({ plan: null, months: 0, credits: 10000 })
    expect(choiceFor({ action: 'renew', months: -2 }).months).toBe(0)
  })

  it('knows when a plan change can start now without extra months', () => {
    const ov = { status: 'Active', current_plan: { price_per_month: 499 }, plans: [{ name: 'Pro', price_per_month: 1499 }, { name: 'Lite', price_per_month: 199 }] }
    expect(upgradeNow(ov, 'Pro')).toBe(true)
    expect(upgradeNow(ov, 'Lite')).toBe(false)
    expect(upgradeNow({ ...ov, status: 'Expired' }, 'Pro')).toBe(false)
  })

  it('formats money and dates', () => {
    expect(money(1034, 'INR')).toBe('₹1,034')
    expect(money(1499.5, 'INR')).toBe('₹1,499.50')
    expect(money('x')).toBe('')
    expect(formatDate('2026-11-25')).toBe('25 Nov 2026')
    expect(formatDate(null)).toBe('')
  })

  it('labels payments', () => {
    expect(paymentLabel({ purpose: 'Subscription', months: 1 })).toBe('1 month')
    expect(paymentLabel({ purpose: 'Credit Top-up', credits: 5000 })).toBe(`${(5000).toLocaleString()} credits`)
    expect(paymentLabel({ purpose: 'Plan Change', new_plan: 'Pro', months: 0 })).toBe('Change to Pro')
  })

  it('calls the add-on methods', async () => {
    call.mockResolvedValue({})
    await loadBilling(ext)
    await quoteBilling(ext, { plan: null, months: 1, credits: 0 })
    await finishCheckout(ext, { razorpay_order_id: 'o', razorpay_payment_id: 'p', razorpay_signature: 's', extra: 1 })
    expect(call.mock.calls).toEqual([
      ['addon.overview', {}, 'GET'],
      ['addon.quote', { plan: null, months: 1, credits: 0 }],
      ['addon.finish', { razorpay_order_id: 'o', razorpay_payment_id: 'p', razorpay_signature: 's' }],
    ])
  })
})
