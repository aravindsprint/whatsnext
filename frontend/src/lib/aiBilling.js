import { call } from '@/api/frappe'

// Plan & Billing for an installed AI add-on (the "ai_billing" extension:
// { overview, quote, start, finish } method names). Prices come from the
// add-on's service; payment happens in Razorpay's own window.

export const FEATURE_NAMES = {
  smart_replies: 'Suggested replies',
  improve_reply: 'Improve my reply',
  translate: 'Translate',
  chat_summary: 'Chat summary',
  order_draft: 'Chat to Sales Order',
  auto_tag: 'Auto-tag',
}
export const CREDIT_PACKS = [1000, 5000, 10000, 25000, 50000]

export function money(amount, currency = 'INR') {
  const n = Number(amount)
  if (!Number.isFinite(n)) return ''
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency', currency, minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2,
    }).format(n)
  } catch {
    return `${currency} ${n.toFixed(2)}`
  }
}

export function formatDate(value) {
  if (!value) return ''
  const d = new Date(`${String(value).slice(0, 10)}T00:00:00`)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

// What the form's state means as a purchase.
export function choiceFor({ action, plan, months, credits }) {
  return {
    plan: action === 'change' ? plan || null : null,
    months: action === 'credits' ? 0 : Math.max(0, parseInt(months, 10) || 0),
    credits: action === 'credits' ? parseInt(credits, 10) || 0 : 0,
  }
}

// A dearer plan mid-period can start without extra months (pay only the
// difference); everything else needs at least one month.
export function upgradeNow(overview, planName) {
  const target = overview?.plans?.find((p) => p.name === planName)
  return !!(target && overview.status === 'Active' && target.price_per_month >= (overview.current_plan?.price_per_month || 0))
}

export function paymentLabel(p) {
  if (p.purpose === 'Credit Top-up') return `${Number(p.credits || 0).toLocaleString()} credits`
  if (p.purpose === 'Plan Change') return `Change to ${p.new_plan}${p.months ? ` + ${p.months} month${p.months === 1 ? '' : 's'}` : ''}`
  return `${p.months} month${p.months === 1 ? '' : 's'}`
}

export const loadBilling = (ext) => call(ext.overview, {}, 'GET')
export const quoteBilling = (ext, choice) => call(ext.quote, choice)
export const startCheckout = (ext, choice) => call(ext.start, choice)
export const finishCheckout = (ext, resp) => call(ext.finish, {
  razorpay_order_id: resp.razorpay_order_id,
  razorpay_payment_id: resp.razorpay_payment_id,
  razorpay_signature: resp.razorpay_signature,
})

export function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = resolve
    s.onerror = () => reject(new Error("Couldn't load Razorpay. Check your internet connection and try again."))
    document.head.appendChild(s)
  })
}
