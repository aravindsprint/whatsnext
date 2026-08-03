<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AppLogo from '@/components/AppLogo.vue'

const auth = useAuthStore()
const usr = ref('')
const pwd = ref('')
const showPwd = ref(false)

function submit() {
  if (usr.value && pwd.value) auth.login(usr.value, pwd.value)
}
</script>

<template>
  <div class="wn-login-page">
    <div class="wn-login-card">
      <AppLogo />
      <h2>Sign in to Whatsnext</h2>
      <p class="wn-subtitle">Your WhatsApp Hub for ERPNext</p>

      <form @submit.prevent="submit">
        <label>Email / Username</label>
        <input v-model="usr" type="text" autocomplete="username" required />

        <label>Password</label>
        <div class="wn-pwd-field">
          <input
            v-model="pwd"
            :type="showPwd ? 'text' : 'password'"
            autocomplete="current-password"
            required
          />
          <button
            type="button"
            class="wn-pwd-toggle"
            :aria-label="showPwd ? 'Hide password' : 'Show password'"
            @click="showPwd = !showPwd"
          >
            <svg v-if="showPwd" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a21.86 21.86 0 0 1 5.06-6.06M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a21.86 21.86 0 0 1-3.22 4.56M1 1l22 22" />
              <path d="M14.12 14.12A3 3 0 0 1 9.88 9.88" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </button>
        </div>

        <p v-if="auth.error" class="wn-error">{{ auth.error }}</p>

        <button type="submit" :disabled="auth.loggingIn">
          {{ auth.loggingIn ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.wn-login-page {
  min-height: 100vh;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, var(--wn-navy), #0a2c2d);
}
.wn-login-card {
  background: white;
  border-radius: 16px;
  padding: 36px 32px;
  width: 100%;
  max-width: 360px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
}
h2 { font-size: 20px; margin: 16px 0 2px; }
.wn-subtitle { color: var(--wn-text-muted); font-size: 13px; margin-bottom: 20px; }
label { display: block; font-size: 12px; font-weight: 600; margin: 12px 0 4px; color: var(--wn-text-muted); }
input {
  width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--wn-border); font-size: 14px;
}
.wn-pwd-field {
  position: relative;
  display: flex;
  align-items: center;
}
.wn-pwd-field input {
  padding-right: 40px;
}
.wn-pwd-toggle {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: auto;
  margin-top: 0;
  padding: 4px;
  border: none;
  background: none;
  color: var(--wn-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.wn-pwd-toggle:hover {
  color: var(--wn-text, #333);
}
button[type="submit"] {
  width: 100%; margin-top: 20px; padding: 11px; border: none; border-radius: 8px;
  background: var(--wn-teal); color: white; font-weight: 600; font-size: 14px;
}
button:disabled { opacity: 0.6; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }
</style>
