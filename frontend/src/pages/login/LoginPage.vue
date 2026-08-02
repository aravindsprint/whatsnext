<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AppLogo from '@/components/AppLogo.vue'

const auth = useAuthStore()
const usr = ref('')
const pwd = ref('')

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
        <input v-model="pwd" type="password" autocomplete="current-password" required />

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
button {
  width: 100%; margin-top: 20px; padding: 11px; border: none; border-radius: 8px;
  background: var(--wn-teal); color: white; font-weight: 600; font-size: 14px;
}
button:disabled { opacity: 0.6; }
.wn-error { color: var(--wn-red); font-size: 12.5px; margin-top: 10px; }
</style>
