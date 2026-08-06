<script setup>
import { onMounted, ref } from 'vue'
import { call } from '@/api/frappe'
import { useAuthStore } from '@/stores/auth'
import { pushSupported, pushPermission, enablePush, disablePush, getExistingSubscription } from '@/push'

const auth = useAuthStore()
const settings = ref(null)
const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref(null)

const testing = ref({ Meta: false, Twilio: false })
const testResult = ref({ Meta: null, Twilio: null })

// Per-device push notification opt-in — available to every logged-in user
// (not just System Managers), since any agent working a chat wants alerts
// on their own device regardless of whether they can touch provider config.
const notifSupported = pushSupported()
const notifPermission = ref(pushPermission())
const notifSubscribed = ref(false)
const notifBusy = ref(false)
const notifError = ref(null)

async function refreshNotifState() {
  if (!notifSupported) return
  notifPermission.value = pushPermission()
  notifSubscribed.value = !!(await getExistingSubscription())
}

async function toggleNotifications() {
  notifBusy.value = true
  notifError.value = null
  try {
    if (notifSubscribed.value) {
      await disablePush()
    } else {
      await enablePush()
    }
    await refreshNotifState()
  } catch (e) {
    notifError.value = e.message
  } finally {
    notifBusy.value = false
  }
}

onMounted(refreshNotifState)

async function load() {
  loading.value = true
  try {
    const res = await call('frappe.client.get', { doctype: 'Whatsnext Settings' }, 'GET')
    // Frappe returns Check fields as "0"/"1" strings (or 0/1 numbers)
    // depending on version — coerce to real booleans so the checkbox
    // v-models actually reflect the stored value after every load.
    for (const f of ['notify_on_failure', 'meta_enabled', 'twilio_enabled', 'push_notifications_enabled']) {
      res[f] = res[f] === true || res[f] === 1 || res[f] === '1'
    }
    settings.value = res
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
    // Credential/config fields first, enabled-flags last — each set_value
    // call runs validate() independently, so flipping a provider "on"
    // before its credentials are persisted would fail validation even
    // when the user supplied everything in the same save.
    const fields = [
      'default_provider', 'notify_on_failure', 'failure_notification_email', 'default_country_code',
      'meta_phone_number_id', 'meta_waba_id', 'meta_app_id', 'meta_api_version',
      'meta_access_token', 'meta_webhook_verify_token',
      'twilio_account_sid', 'twilio_whatsapp_number', 'twilio_auth_token',
      'vapid_subject', 'push_notifications_enabled',
      'meta_enabled', 'twilio_enabled',
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

async function testConnection(provider) {
  testing.value[provider] = true
  testResult.value[provider] = null
  try {
    const res = await call('whatsnext.whatsnext.api.test_provider_connection', { provider })
    testResult.value[provider] = res
  } catch (e) {
    testResult.value[provider] = { success: false, error: e.message }
  } finally {
    testing.value[provider] = false
  }
}
</script>

<template>
  <div class="wn-settings">
    <div class="wn-card">
      <div class="wn-card-top">
        <h3>Notifications</h3>
        <label v-if="notifSupported" class="wn-checkbox">
          <input type="checkbox" :checked="notifSubscribed" :disabled="notifBusy" @change="toggleNotifications" />
          {{ notifSubscribed ? 'On' : 'Off' }}
        </label>
      </div>
      <p v-if="!notifSupported" class="wn-hint">This browser doesn't support push notifications.</p>
      <template v-else>
        <p class="wn-hint">
          Get a real notification on this device the moment a new WhatsApp message comes in — even when
          Whatsnext isn't open.
        </p>
        <p v-if="notifPermission === 'denied'" class="wn-error">
          Notifications are blocked for this site in your browser settings. Allow them there to turn this on.
        </p>
        <p v-else-if="notifBusy" class="wn-hint">{{ notifSubscribed ? 'Turning off…' : 'Turning on…' }}</p>
        <p v-else-if="notifSubscribed" class="wn-success">✓ Notifications are on for this device.</p>
        <p v-if="notifError" class="wn-error">{{ notifError }}</p>
      </template>
    </div>

    <div v-if="!auth.isSystemManager" class="wn-card wn-forbidden">
      The rest of Settings is restricted to System Managers.
    </div>

    <div v-else-if="loading" class="wn-muted">Loading settings…</div>

    <template v-else-if="settings">
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
      <label>Default Country Code</label>
      <input v-model="settings.default_country_code" type="text" placeholder="91" />
      <p class="wn-hint">Prepended to outbound numbers with no country code (e.g. a bare 10-digit number).</p>

      <label class="wn-checkbox">
        <input type="checkbox" v-model="settings.push_notifications_enabled" /> Enable push notifications site-wide
      </label>
      <p class="wn-hint">Master switch for the browser/mobile push alerts users turn on in the Notifications card above.</p>
      <template v-if="settings.push_notifications_enabled">
        <label>VAPID Subject (contact for push services)</label>
        <input v-model="settings.vapid_subject" type="text" placeholder="mailto:admin@example.com" />
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

      <div class="wn-test-row">
        <button class="secondary" :disabled="testing.Meta" @click="testConnection('Meta')">
          {{ testing.Meta ? 'Testing…' : 'Test Connection' }}
        </button>
        <span v-if="testResult.Meta?.success" class="wn-success">
          ✓ Connected — {{ testResult.Meta.details.verified_name || testResult.Meta.details.display_phone_number }}
        </span>
        <span v-else-if="testResult.Meta && !testResult.Meta.success" class="wn-error">
          ✗ {{ testResult.Meta.error }}
        </span>
      </div>
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

      <div class="wn-test-row">
        <button class="secondary" :disabled="testing.Twilio" @click="testConnection('Twilio')">
          {{ testing.Twilio ? 'Testing…' : 'Test Connection' }}
        </button>
        <span v-if="testResult.Twilio?.success" class="wn-success">
          ✓ Connected — {{ testResult.Twilio.details.friendly_name }} ({{ testResult.Twilio.details.status }})
        </span>
        <span v-else-if="testResult.Twilio && !testResult.Twilio.success" class="wn-error">
          ✗ {{ testResult.Twilio.error }}
        </span>
      </div>
    </div>

    <p v-if="error" class="wn-error">{{ error }}</p>
    <p v-if="saved" class="wn-success">Settings saved.</p>

    <button class="primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save Settings' }}</button>
    </template>
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
.wn-test-row { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
button.primary { align-self: flex-start; background: var(--wn-teal); color: white; border: none; padding: 11px 22px; border-radius: 10px; font-weight: 600; }
button.secondary { background: var(--wn-bg); color: var(--wn-text, #333); border: 1px solid var(--wn-border); padding: 8px 16px; border-radius: 8px; font-weight: 600; font-size: 12.5px; }
.wn-error { color: var(--wn-red); font-size: 13px; }
.wn-success { color: var(--wn-teal); font-size: 13px; }
.wn-forbidden { color: var(--wn-text-muted); }
.wn-muted { color: var(--wn-text-muted); }
</style>
