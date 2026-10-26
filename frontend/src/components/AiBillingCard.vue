<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  choiceFor, CREDIT_PACKS, FEATURE_NAMES, finishCheckout, formatDate, loadBilling, loadRazorpay, money, paymentLabel,
  quoteBilling, startCheckout, upgradeNow,
} from '@/lib/aiBilling'

// Plan & Billing for the AI add-on, in Settings (System Managers): renew,
// change plan or buy credits, paid in Razorpay's own window.
const props = defineProps({ ext: { type: Object, required: true } })
const auth = useAuthStore()

const ov = ref(null)
const loadError = ref('')
const action = ref('renew')
const plan = ref('')
const months = ref(1)
const credits = ref(5000)
const quote = ref(null)
const quoteError = ref('')
const quoting = ref(false)
const paying = ref(false)
const result = ref(null) // { status, message }
let timer = null

const active = computed(() => ov.value?.status === 'Active')
const managed = computed(() => ov.value?.current_plan?.key_source === 'managed')
const otherPlans = computed(() => (ov.value?.plans || []).filter((p) => p.name !== ov.value.plan))
const canBuyCredits = computed(() => active.value && managed.value && ov.value?.current_plan?.topup_price_per_1000_credits > 0)
const statusPill = computed(() => ({
  Active: ['green', 'Active'], 'Awaiting Payment': ['orange', 'Waiting for first payment'],
  Expired: ['red', 'Expired'], Suspended: ['red', 'Suspended'],
}[ov.value?.status] || ['gray', ov.value?.status || '']))
const monthsHint = computed(() => (action.value === 'change' && upgradeNow(ov.value, plan.value)
  ? '0 = switch now and pay only the difference for the days left in this period.' : ''))

async function load() {
  loadError.value = ''
  try {
    ov.value = await loadBilling(props.ext)
    if (!plan.value) plan.value = otherPlans.value[0]?.name || ''
    refreshQuote()
  } catch (e) {
    loadError.value = e.message
  }
}

function setDefaults() {
  if (action.value === 'change') months.value = upgradeNow(ov.value, plan.value) ? 0 : Math.max(1, months.value || 1)
  else if (action.value === 'renew') months.value = Math.max(1, months.value || 1)
}

function refreshQuote() {
  clearTimeout(timer)
  quote.value = null
  quoteError.value = ''
  if (!ov.value) return
  if (action.value === 'change' && !plan.value) return
  quoting.value = true
  timer = setTimeout(async () => {
    try {
      const res = await quoteBilling(props.ext, choiceFor({ action: action.value, plan: plan.value, months: months.value, credits: credits.value }))
      if (res?.error) quoteError.value = res.error
      else quote.value = res
    } catch (e) {
      quoteError.value = e.message
    } finally {
      quoting.value = false
    }
  }, 300)
}

watch([action, plan], () => { setDefaults(); refreshQuote() })
watch([months, credits], refreshQuote)

async function pay() {
  if (!quote.value || paying.value) return
  paying.value = true
  result.value = null
  try {
    const c = await startCheckout(props.ext, choiceFor({ action: action.value, plan: plan.value, months: months.value, credits: credits.value }))
    await loadRazorpay()
    const rzp = new window.Razorpay({
      key: c.key_id, order_id: c.order_id, amount: c.amount, currency: c.currency,
      name: c.name, description: c.description, prefill: c.prefill || {},
      theme: { color: '#16a394' },
      handler: (resp) => finish(resp),
      modal: { ondismiss: () => { paying.value = false } },
    })
    rzp.on('payment.failed', (resp) => {
      result.value = { status: 'Failed', message: resp?.error?.description || "The payment didn't go through. Please try again or use another method." }
    })
    rzp.open()
  } catch (e) {
    result.value = { status: 'Failed', message: e.message }
    paying.value = false
  }
}

async function finish(resp) {
  try {
    result.value = { status: 'Confirming', message: 'Confirming your payment…' }
    result.value = await finishCheckout(props.ext, resp)
    await load()
    auth.loadWhoAmI() // the plan's AI features may have changed
  } catch (e) {
    result.value = { status: 'Failed', message: e.message }
  } finally {
    paying.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="wn-card wn-billing">
    <div class="wn-card-top">
      <h3>AI plan &amp; billing</h3>
      <span v-if="ov" class="wn-pill" :class="statusPill[0]">{{ statusPill[1] }}</span>
    </div>
    <p v-if="loadError" class="wn-error">{{ loadError }}</p>
    <p v-else-if="!ov" class="wn-muted">Loading your plan…</p>

    <template v-else>
      <div class="wn-billing-now">
        <div>
          <div class="wn-billing-label">Plan</div>
          <div class="wn-billing-big">{{ ov.plan }}</div>
          <div v-if="ov.valid_until" class="wn-billing-small">Paid until <strong>{{ formatDate(ov.valid_until) }}</strong></div>
        </div>
        <div>
          <div class="wn-billing-label">{{ managed ? 'Credits available' : 'AI usage' }}</div>
          <div class="wn-billing-big">{{ managed ? Math.floor(ov.credits.available).toLocaleString() : 'Your own AI account' }}</div>
          <div v-if="managed && active && ov.next_refill" class="wn-billing-small">Next monthly allowance {{ formatDate(ov.next_refill) }}</div>
        </div>
      </div>
      <p v-if="ov.scheduled_plan" class="wn-billing-note">You'll move to <strong>{{ ov.scheduled_plan }}</strong> on {{ formatDate(ov.scheduled_plan_from) }}.</p>
      <p v-if="!ov.online_payments" class="wn-billing-note warn">Online payment isn't set up yet. Contact your Whatsnext AI provider to pay.</p>

      <div class="wn-billing-tabs" role="tablist">
        <button type="button" :class="{ on: action === 'renew' }" @click="action = 'renew'">{{ active ? `Renew ${ov.plan}` : `Pay for ${ov.plan}` }}</button>
        <button v-if="otherPlans.length" type="button" :class="{ on: action === 'change' }" @click="action = 'change'">Change plan</button>
        <button v-if="canBuyCredits" type="button" :class="{ on: action === 'credits' }" @click="action = 'credits'">Buy credits</button>
      </div>

      <div class="wn-row">
        <div v-if="action === 'change'">
          <label>New plan</label>
          <select v-model="plan">
            <option v-for="p in otherPlans" :key="p.name" :value="p.name">{{ p.name }} — {{ money(p.price_per_month, p.currency) }}/month</option>
          </select>
        </div>
        <div v-if="action !== 'credits'">
          <label>Months</label>
          <input v-model.number="months" type="number" min="0" :max="ov.max_months" />
        </div>
        <div v-else>
          <label>Credits</label>
          <select v-model.number="credits">
            <option v-for="c in CREDIT_PACKS" :key="c" :value="c">{{ c.toLocaleString() }}</option>
          </select>
        </div>
      </div>
      <p v-if="monthsHint" class="wn-hint">{{ monthsHint }}</p>

      <div class="wn-billing-quote">
        <p v-if="quoting" class="wn-muted">Working out the price…</p>
        <p v-else-if="quoteError" class="wn-error">{{ quoteError }}</p>
        <template v-else-if="quote">
          <ul><li v-for="(line, i) in quote.summary" :key="i">{{ line }}</li></ul>
          <div class="wn-billing-pay">
            <div class="wn-billing-big">To pay: {{ money(quote.amount, quote.currency) }}</div>
            <button type="button" class="primary" :disabled="paying || !ov.online_payments || !(quote.amount > 0)" @click="pay">
              {{ paying ? 'Waiting for payment…' : `Pay ${money(quote.amount, quote.currency)}` }}
            </button>
          </div>
          <p class="wn-hint">You pay in Razorpay's window (UPI, card or netbanking). Card and bank details never reach this site.</p>
        </template>
      </div>
      <p v-if="result" :class="result.status === 'Paid' ? 'wn-success' : (result.status === 'Failed' ? 'wn-error' : 'wn-billing-note')">{{ result.message }}</p>

      <details class="wn-billing-more">
        <summary>Compare plans</summary>
        <div v-for="p in ov.plans" :key="p.name" class="wn-billing-plan" :class="{ mine: p.name === ov.plan }">
          <div class="wn-billing-plan-top">
            <strong>{{ p.name }}<span v-if="p.name === ov.plan" class="wn-muted"> (yours)</span></strong>
            <span>{{ money(p.price_per_month, p.currency) }}/month</span>
          </div>
          <div class="wn-billing-small">
            {{ p.key_source === 'own' ? 'Uses your own AI account' : `${Math.floor(p.monthly_credits).toLocaleString()} credits a month` }}
            · {{ p.models.join(', ') }}
          </div>
          <div class="wn-billing-small">{{ p.features.map((f) => FEATURE_NAMES[f] || f).join(' · ') }}</div>
        </div>
      </details>
      <details class="wn-billing-more">
        <summary>Payment history</summary>
        <p v-if="!ov.payments.length" class="wn-muted">No payments yet.</p>
        <div v-for="p in ov.payments" :key="p.name" class="wn-billing-history">
          <span>{{ formatDate(p.payment_date) }}</span><span>{{ paymentLabel(p) }}</span>
          <span>{{ money(p.amount, p.currency) }}</span><span class="wn-muted">{{ p.payment_method }}</span>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 20px; }
.wn-card-top { display: flex; justify-content: space-between; align-items: center; }
.wn-card h3 { margin: 0 0 12px; font-size: 15px; }
label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 10px 0 4px; }
input, select { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; box-sizing: border-box; }
.wn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.wn-hint { font-size: 11.5px; color: var(--wn-text-muted); margin: 6px 0 0; }
.wn-muted { color: var(--wn-text-muted); font-size: 13px; }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-success { color: var(--wn-teal); font-size: 13px; font-weight: 600; }
.wn-pill { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 10px; }
.wn-pill.green { background: #e7f8ee; color: #15803d; }
.wn-pill.orange { background: #fff4e0; color: #9a5b00; }
.wn-pill.red { background: #fde8e8; color: #b42318; }
.wn-pill.gray { background: var(--wn-bg); color: var(--wn-text-muted); }
.wn-billing-now { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; background: var(--wn-bg); border-radius: 10px; }
.wn-billing-label { font-size: 11px; color: var(--wn-text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.wn-billing-big { font-size: 17px; font-weight: 700; margin: 2px 0; }
.wn-billing-small { font-size: 12px; color: var(--wn-text-muted); }
.wn-billing-note { font-size: 12.5px; background: var(--wn-teal-light); padding: 8px 10px; border-radius: 8px; margin: 10px 0 0; }
.wn-billing-note.warn { background: #fff4e0; color: #9a5b00; }
.wn-billing-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
.wn-billing-tabs button { background: white; border: 1px solid var(--wn-border); color: var(--wn-text); padding: 7px 12px; border-radius: 18px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.wn-billing-tabs button.on { background: var(--wn-teal-light); border-color: var(--wn-teal); color: #0b7a6e; }
.wn-billing-quote { margin-top: 14px; border-top: 1px solid var(--wn-border); padding-top: 12px; }
.wn-billing-quote ul { margin: 0 0 10px; padding-left: 18px; font-size: 13px; }
.wn-billing-pay { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
button.primary { background: var(--wn-teal); color: white; border: none; padding: 10px 18px; border-radius: 10px; font-weight: 600; }
button.primary:disabled { opacity: 0.5; }
.wn-billing-more { margin-top: 12px; font-size: 13px; }
.wn-billing-more summary { cursor: pointer; font-weight: 600; color: var(--wn-text-muted); font-size: 12.5px; }
.wn-billing-plan { border: 1px solid var(--wn-border); border-radius: 8px; padding: 8px 10px; margin-top: 8px; }
.wn-billing-plan.mine { border-color: var(--wn-teal); }
.wn-billing-plan-top { display: flex; justify-content: space-between; gap: 8px; }
.wn-billing-history { display: grid; grid-template-columns: 90px 1fr auto 80px; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--wn-border); font-size: 12.5px; }
@media (max-width: 600px) {
  .wn-row, .wn-billing-now { grid-template-columns: 1fr; }
  .wn-billing-history { grid-template-columns: 80px 1fr auto; }
  .wn-billing-history span:last-child { display: none; }
}
</style>
