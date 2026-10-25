<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  aiCredits, createSalesOrder, extractOrder, formatCredits, orderProblems, retagChat, searchItems, summarizeChat, summaryNote,
} from '@/lib/aiReplies'

// The AI menu in the chat header: Chat summary, Chat to Sales Order and
// re-labelling the chat. Shown by HomePage when an installed app provides
// any of the chat_summary / order_draft / auto_tag extensions.
const props = defineProps({
  exts: { type: Object, required: true }, // { chat_summary?, order_draft?, auto_tag? }
  conversationId: { type: String, required: true },
  customerLinked: { type: Boolean, default: false },
})
const emit = defineEmits(['note', 'link-customer', 'labelled'])

const menuOpen = ref(false)
const panel = ref(null) // 'summary' | 'order' | null
const loading = ref(false)
const error = ref(null)
const toast = ref('')

const summaryExt = computed(() => props.exts.chat_summary || null)
const orderExt = computed(() => props.exts.order_draft || null)
const tagExt = computed(() => props.exts.auto_tag || null)

// --- Menu ------------------------------------------------------------------
function toggleMenu() {
  menuOpen.value = !menuOpen.value
}
function onDocClick(e) {
  if (menuOpen.value && !e.target.closest?.('.wn-aitools')) menuOpen.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

function flash(text) {
  toast.value = text
  setTimeout(() => { if (toast.value === text) toast.value = '' }, 3500)
}

async function guarded(fn) {
  loading.value = true
  error.value = null
  try {
    await fn()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function closePanel() {
  panel.value = null
  error.value = null
}

// --- Summary -----------------------------------------------------------------
const summary = ref(null)
const noteSaved = ref(false)

function openSummary() {
  menuOpen.value = false
  panel.value = 'summary'
  summary.value = null
  noteSaved.value = false
  guarded(async () => { summary.value = await summarizeChat(summaryExt.value, props.conversationId) })
}

function saveSummaryAsNote() {
  emit('note', summaryNote(summary.value))
  noteSaved.value = true
}

// --- Order -------------------------------------------------------------------
const order = ref(null)
const created = ref(null)
const problems = ref([])
const search = ref({ line: null, text: '', results: [] })
let searchTimer = null

function openOrder() {
  menuOpen.value = false
  panel.value = 'order'
  order.value = null
  created.value = null
  problems.value = []
  if (!props.customerLinked) {
    error.value = 'Link this chat to a customer first, then draft the order.'
    return
  }
  guarded(async () => { order.value = await extractOrder(orderExt.value, props.conversationId) })
}

function addLine() {
  order.value.lines.push({ itemCode: '', itemName: '', description: '', qty: '', uom: '', rate: '', match: 'none' })
}
function removeLine(i) {
  order.value.lines.splice(i, 1)
}

function startSearch(i) {
  const line = order.value.lines[i]
  search.value = { line: i, text: line.itemName || line.description || '', results: [] }
  runSearch()
}
function runSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    try {
      search.value.results = await searchItems(orderExt.value, search.value.text)
    } catch (e) {
      search.value.results = []
    }
  }, 250)
}
function pickItem(item) {
  const line = order.value.lines[search.value.line]
  Object.assign(line, { itemCode: item.item_code, itemName: item.item_name, match: 'exact' })
  if (!line.uom) line.uom = item.stock_uom
  search.value = { line: null, text: '', results: [] }
}

function saveOrder() {
  problems.value = orderProblems(order.value.lines)
  if (problems.value.length) return
  guarded(async () => {
    created.value = await createSalesOrder(orderExt.value, {
      conversationId: props.conversationId,
      lines: order.value.lines,
      deliveryDate: order.value.deliveryDate,
      notes: order.value.notes,
    })
  })
}

function money(value, currency) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  return `${currency || ''} ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim()
}

// --- Labels ------------------------------------------------------------------
function relabel() {
  menuOpen.value = false
  guarded(async () => {
    const labels = await retagChat(tagExt.value, props.conversationId)
    emit('labelled', labels)
    flash(labels.length ? `Labelled: ${labels.map((l) => l.text).join(', ')}` : 'Labelled')
  }).then(() => { if (error.value) flash(error.value) })
}

watch(() => props.conversationId, () => {
  closePanel()
  menuOpen.value = false
})
</script>

<template>
  <div class="wn-aitools">
    <button type="button" class="wn-aitools-btn" :class="{ active: menuOpen }" @click.stop="toggleMenu" title="AI tools for this chat" aria-label="AI tools for this chat">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      </svg>
      <span>AI</span>
    </button>
    <div v-if="menuOpen" class="wn-aitools-menu" role="menu">
      <button v-if="summaryExt" type="button" role="menuitem" @click="openSummary">📝 Summarize chat</button>
      <button v-if="orderExt" type="button" role="menuitem" @click="openOrder">🧾 Draft sales order</button>
      <button v-if="tagExt" type="button" role="menuitem" @click="relabel">🏷️ Label this chat</button>
    </div>
    <div v-if="toast" class="wn-aitools-toast">{{ toast }}</div>

    <div v-if="panel" class="wn-aitools-backdrop" @click.self="closePanel">
      <div class="wn-aitools-modal" role="dialog" :aria-label="panel === 'summary' ? 'Chat summary' : 'Draft sales order'">
        <div class="wn-aitools-head">
          <h3>{{ panel === 'summary' ? 'Chat summary' : 'Draft sales order' }}</h3>
          <span v-if="aiCredits !== null" class="wn-aitools-muted">{{ formatCredits(aiCredits) }} credits</span>
          <button type="button" class="wn-aitools-x" @click="closePanel" aria-label="Close">✕</button>
        </div>

        <p v-if="loading" class="wn-aitools-muted">{{ panel === 'summary' ? 'Reading the chat…' : (order ? 'Saving the draft order…' : 'Reading the order from the chat…') }}</p>
        <p v-if="error" class="wn-aitools-error">
          {{ error }}
          <button v-if="panel === 'order' && !customerLinked" type="button" class="wn-aitools-link" @click="closePanel(); emit('link-customer')">Link a customer</button>
        </p>

        <!-- Summary -->
        <template v-if="panel === 'summary' && summary">
          <p class="wn-aitools-summary">{{ summary.summary }}</p>
          <template v-if="summary.openItems.length">
            <h4>Still open</h4>
            <ul><li v-for="(item, i) in summary.openItems" :key="i">{{ item }}</li></ul>
          </template>
          <template v-if="summary.nextStep">
            <h4>Next step</h4>
            <p>{{ summary.nextStep }}</p>
          </template>
          <div class="wn-aitools-actions">
            <span class="wn-aitools-muted">AI can get details wrong.</span>
            <button type="button" class="ghost small" :disabled="noteSaved" @click="saveSummaryAsNote">{{ noteSaved ? 'Added as note ✓' : 'Add as team note' }}</button>
          </div>
        </template>

        <!-- Order -->
        <template v-if="panel === 'order' && order && !created">
          <p class="wn-aitools-muted">
            For <strong>{{ order.customerName || order.customer }}</strong>. Check every line: items marked
            <span class="wn-aitools-tag suggested">check</span> were matched by name.
          </p>
          <p v-if="!order.lines.length" class="wn-aitools-muted">No order found in this chat. Add the items yourself, or close this.</p>
          <div v-for="(line, i) in order.lines" :key="i" class="wn-aitools-line">
            <div class="wn-aitools-line-top">
              <button type="button" class="wn-aitools-item" @click="startSearch(i)" :title="'Customer wrote: ' + (line.description || '')">
                <template v-if="line.itemCode">
                  <strong>{{ line.itemName || line.itemCode }}</strong>
                  <span class="wn-aitools-muted">{{ line.itemCode }}</span>
                </template>
                <span v-else class="wn-aitools-error">Choose an item</span>
              </button>
              <span v-if="line.match === 'suggested'" class="wn-aitools-tag suggested" title="Matched by name. Check it's the right item.">check</span>
              <button type="button" class="wn-aitools-x" @click="removeLine(i)" title="Remove line" aria-label="Remove line">✕</button>
            </div>
            <div v-if="line.description" class="wn-aitools-muted wn-aitools-said">Customer: “{{ line.description }}”</div>
            <div v-if="search.line === i" class="wn-aitools-search">
              <input v-model="search.text" type="text" placeholder="Search items by name or code" @input="runSearch" />
              <button v-for="item in search.results" :key="item.item_code" type="button" class="wn-aitools-result" @click="pickItem(item)">
                <strong>{{ item.item_name || item.item_code }}</strong> <span class="wn-aitools-muted">{{ item.item_code }} · {{ item.stock_uom }}</span>
              </button>
              <p v-if="search.text && !search.results.length" class="wn-aitools-muted">No matching items.</p>
            </div>
            <div class="wn-aitools-fields">
              <label>Qty <input v-model="line.qty" type="number" min="0" step="any" /></label>
              <label>Unit <input v-model="line.uom" type="text" /></label>
              <label>Rate <input v-model="line.rate" type="number" min="0" step="any" placeholder="Price list" /></label>
            </div>
          </div>
          <button type="button" class="ghost small" @click="addLine">+ Add item</button>
          <div class="wn-aitools-fields wn-aitools-order-fields">
            <label>Deliver by <input v-model="order.deliveryDate" type="date" /></label>
          </div>
          <label class="wn-aitools-notes">Notes for the order <textarea v-model="order.notes" rows="2" /></label>
          <ul v-if="problems.length" class="wn-aitools-error"><li v-for="p in problems" :key="p">{{ p }}</li></ul>
          <div class="wn-aitools-actions">
            <span class="wn-aitools-muted">Saved as a draft. Nothing is submitted.</span>
            <button type="button" class="primary small" :disabled="loading" @click="saveOrder">Create draft order</button>
          </div>
        </template>
        <template v-if="panel === 'order' && created">
          <p>Draft Sales Order <strong>{{ created.name }}</strong> created<template v-if="created.grand_total"> for {{ money(created.grand_total, created.currency) }}</template>. A note was added to this chat.</p>
          <div class="wn-aitools-actions">
            <button type="button" class="ghost small" @click="closePanel">Close</button>
            <a :href="created.url" target="_blank" rel="noopener" class="wn-aitools-open">Open in ERPNext</a>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-aitools { position: relative; }
.wn-aitools-btn {
  display: inline-flex; align-items: center; gap: 4px; padding: 6px 10px; border-radius: 8px;
  border: 1px solid var(--wn-border); background: white; color: var(--wn-text); font-size: 12px; font-weight: 600; cursor: pointer;
}
.wn-aitools-btn.active, .wn-aitools-btn:hover { border-color: var(--wn-teal); color: var(--wn-teal); background: var(--wn-teal-light); }
.wn-aitools-menu {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 40; min-width: 200px;
  background: white; border-radius: 10px; box-shadow: 0 4px 16px rgba(15, 61, 62, 0.16); padding: 6px;
}
.wn-aitools-menu button {
  display: block; width: 100%; text-align: left; background: none; border: none; padding: 9px 10px;
  border-radius: 6px; font-size: 13px; color: var(--wn-text); cursor: pointer;
}
.wn-aitools-menu button:hover { background: var(--wn-teal-light); }
.wn-aitools-toast {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 39; white-space: nowrap;
  background: var(--wn-navy); color: white; font-size: 12px; padding: 6px 10px; border-radius: 8px;
}
.wn-aitools-backdrop { position: fixed; inset: 0; background: rgba(15, 61, 62, 0.4); display: flex; align-items: center; justify-content: center; z-index: 60; }
.wn-aitools-modal {
  background: white; border-radius: 14px; padding: 20px; width: 560px; max-width: 94vw; max-height: 88vh; overflow-y: auto;
  color: var(--wn-text); font-size: 13px;
}
.wn-aitools-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.wn-aitools-head h3 { margin: 0; flex: 1; font-size: 16px; }
.wn-aitools-modal h4 { margin: 14px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--wn-text-muted); }
.wn-aitools-modal ul { margin: 0; padding-left: 18px; }
.wn-aitools-summary { font-size: 14px; line-height: 1.5; margin: 0; }
.wn-aitools-x { background: none; border: none; color: var(--wn-text-muted); cursor: pointer; font-size: 14px; padding: 4px; }
.wn-aitools-muted { color: var(--wn-text-muted); font-size: 12px; }
.wn-aitools-error { color: var(--wn-red); font-size: 12px; }
.wn-aitools-link { background: none; border: none; color: var(--wn-teal); font-weight: 600; cursor: pointer; text-decoration: underline; padding: 0 4px; font-size: 12px; }
.wn-aitools-actions { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 16px; }
.wn-aitools-open { background: var(--wn-teal); color: white; padding: 6px 12px; border-radius: 8px; font-weight: 600; font-size: 12px; text-decoration: none; }
.wn-aitools-line { border: 1px solid var(--wn-border); border-radius: 10px; padding: 10px; margin: 8px 0; }
.wn-aitools-line-top { display: flex; align-items: center; gap: 8px; }
.wn-aitools-item {
  flex: 1; min-width: 0; text-align: left; background: var(--wn-bg); border: 1px solid transparent; border-radius: 8px;
  padding: 6px 8px; cursor: pointer; display: flex; gap: 8px; align-items: baseline; font-size: 13px; color: var(--wn-text);
}
.wn-aitools-item:hover { border-color: var(--wn-teal); }
.wn-aitools-said { margin: 4px 2px 0; }
.wn-aitools-tag { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }
.wn-aitools-tag.suggested { background: #fff4e0; color: #9a5b00; }
.wn-aitools-search { margin-top: 6px; }
.wn-aitools-search input { width: 100%; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-aitools-result { display: block; width: 100%; text-align: left; background: none; border: none; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--wn-text); }
.wn-aitools-result:hover { background: var(--wn-teal-light); }
.wn-aitools-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }
.wn-aitools-order-fields { grid-template-columns: minmax(0, 200px); margin-top: 12px; }
.wn-aitools-fields label, .wn-aitools-notes { display: block; font-size: 11px; font-weight: 600; color: var(--wn-text-muted); }
.wn-aitools-notes { margin-top: 10px; }
.wn-aitools-fields input, .wn-aitools-notes textarea {
  display: block; width: 100%; margin-top: 3px; padding: 7px 8px; border-radius: 8px; border: 1px solid var(--wn-border);
  font-size: 13px; font-family: inherit; color: var(--wn-text); box-sizing: border-box;
}
@media (max-width: 600px) {
  .wn-aitools-modal { padding: 14px; }
  .wn-aitools-actions { flex-wrap: wrap; }
}
</style>
