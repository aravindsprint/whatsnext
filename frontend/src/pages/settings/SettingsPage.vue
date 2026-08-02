<script setup>
import { onMounted, ref } from 'vue'
import { call } from '@/api/frappe'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const settings = ref(null)
const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref(null)

async function load() {
  loading.value = true
  try {
    settings.value = await call('frappe.client.get', { doctype: 'Whatsnext Settings' }, 'GET')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function save() {
  saving.value = true
  saved.value = false
  error.value = null
  try {
    const fields = [
      'default_provider', 'notify_on_failure', 'failure_notification_email',
      'meta_enabled', 'meta_phone_number_id', 'meta_waba_id', 'meta_app_id', 'meta_api_version',
      'meta_access_token', 'meta_webhook_verify_token',
      'twilio_enabled', 'twilio_account_sid', 'twilio_whatsapp_number', 'twilio_auth_token',
    ]
    for (const f of fields) {
      // skip masked password placeholders so we never overwrite a saved
      // token with the '***' placeholder the API returns
      if ((f === 'meta_access_token' || f === 'twilio_auth_token') && /^\*+$/.test(settings.value[f] || '')) continue
      await call('frappe.client.set_value', {
        doctype: 'Whatsnext Settings',
        name: 'Whatsnext Settings',
        fieldname: f,
        value: settings.value[f],
      })
    }
    saved.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="!auth.isSystemManager" class="wn-card wn-forbidden">
    Settings are restricted to System Managers.
  </div>

  <div v-else-if="loading" class="wn-muted">Loading settings…</div>

  <div v-else-if="settings" class="wn-settings">
    <div class="wn-card">
      <h3>General</h3>
      <label>Default Provider</label>
      <select v-model="settings.default_provider">
        <option>Meta</option>
        <option>Twilio</option>
      </select>
      <label class="wn-checkbox"><input type="checkbox" v-model="settings.notify_on_failure" /> Notify admin on send failure</label>
      <template v-if="settings.notify_on_failure">
        <label>Failure Notification Email</label>
        <input v-model="settings.failure_notification_email" type="email" />
      </template>
    </div>

    <div class="wn-card">
      <div class="wn-card-top">
        <h3>Meta WhatsApp Cloud API</h3>
        <label class="wn-checkbox"><input type="checkbox" v-model="settings.meta_enabled" /> Enabled</label>
      </div>
      <div class="wn-row">
        <div>
          <label>Phone Number ID</label>
          <input v-model="settings.meta_phone_number_id" />
        </div>
        <div>
          <label>WABA ID</label>
          <input v-model="settings.meta_waba_id" />
        </div>
      </div>
      <div class="wn-row">
        <div>
          <label>App ID</label>
          <input v-model="settings.meta_app_id" />
        </div>
        <div>
          <label>Graph API Version</label>
          <input v-model="settings.meta_api_version" />
        </div>
      </div>
      <label>Permanent Access Token</label>
      <input v-model="settings.meta_access_token" type="password" placeholder="Leave unchanged to keep existing token" />
      <label>Webhook Verify Token</label>
      <input v-model="settings.meta_webhook_verify_token" />
      <p class="wn-hint">Webhook URL: <code>/api/method/whatsnext.whatsnext.api.webhook.meta_webhook</code></p>
    </div>

    <div class="wn-card">
      <div class="wn-card-top">
        <h3>Twilio WhatsApp API</h3>
        <label class="wn-checkbox"><input type="checkbox" v-model="settings.twilio_enabled" /> Enabled</label>
      </div>
      <div class="wn-row">
        <div>
          <label>Account SID</label>
          <input v-model="settings.twilio_account_sid" />
        </div>
        <div>
          <label>WhatsApp Number</label>
          <input v-model="settings.twilio_whatsapp_number" placeholder="whatsapp:+14155238886" />
        </div>
      </div>
      <label>Auth Token</label>
      <input v-model="settings.twilio_auth_token" type="password" placeholder="Leave unchanged to keep existing token" />
      <p class="wn-hint">
        Inbound webhook: <code>/api/method/whatsnext.whatsnext.api.webhook.twilio_webhook</code><br />
        Status callback: <code>/api/method/whatsnext.whatsnext.api.webhook.twilio_status_callback</code>
      </p>
    </div>

    <p v-if="error" class="wn-error">{{ error }}</p>
    <p v-if="saved" class="wn-success">Settings saved.</p>

    <button class="primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save Settings' }}</button>
  </div>
</template>

<style scoped>
.wn-settings { display: flex; flex-direction: column; gap: 16px; max-width: 640px; }
.wn-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 20px; }
.wn-card-top { display: flex; justify-content: space-between; align-items: center; }
.wn-card h3 { margin: 0 0 12px; font-size: 15px; }
label { display: block; font-size: 12px; font-weight: 600; color: var(--wn-text-muted); margin: 10px 0 4px; }
.wn-checkbox { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.wn-checkbox input { width: auto; }
input, select { width: 100%; padding: 9px 10px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 13px; }
.wn-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.wn-hint { font-size: 11.5px; color: var(--wn-text-muted); margin-top: 10px; }
.wn-hint code { background: var(--wn-bg); padding: 1px 5px; border-radius: 4px; }
button.primary { align-self: flex-start; background: var(--wn-teal); color: white; border: none; padding: 11px 22px; border-radius: 10px; font-weight: 600; }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-success { color: var(--wn-teal); font-size: 13px; }
.wn-forbidden { color: var(--wn-text-muted); }
.wn-muted { color: var(--wn-text-muted); }
</style>
