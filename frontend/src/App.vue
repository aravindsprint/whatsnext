<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import NavSidebar from '@/components/NavSidebar.vue'
import { useAuthStore } from '@/stores/auth'
import { isLoggedIn } from '@/api/frappe'
import { pushPermission, enablePush } from '@/push'

const route = useRoute()
const auth = useAuthStore()
const isLoginRoute = computed(() => route.name === 'login')

onMounted(() => {
  if (isLoggedIn()) {
    auth.loadWhoAmI()
    // Re-register the push subscription with the backend if the user
    // already granted notification permission on a previous visit —
    // browsers can rotate/expire a push endpoint, and this keeps the
    // server's copy current without asking again. Never prompts for
    // permission here; that only happens from the explicit Settings toggle.
    if (pushPermission() === 'granted') {
      enablePush().catch(() => {
        /* non-fatal — Settings page surfaces any real problem */
      })
    }
  }
})
</script>

<template>
  <div v-if="isLoginRoute" class="wn-login-shell">
    <router-view />
  </div>
  <div v-else-if="auth.loaded && !auth.hasAccess" class="wn-no-access">
    <div class="wn-no-access-card">
      <h2>No access to Whatsnext</h2>
      <p>Your account ({{ auth.user }}) doesn't have the <strong>Whatsnext User</strong> role. Ask your administrator to add it.</p>
      <button class="ghost" @click="auth.logout()">Log out</button>
    </div>
  </div>
  <div v-else class="wn-app-shell">
    <NavSidebar />
    <div class="wn-main">
      <AppHeader />
      <div class="wn-content" :class="{ 'wn-content-chat': route.name === 'home', 'wn-content-narrow': ['settings', 'about'].includes(route.name) }">
        <div class="wn-content-inner">
          <router-view />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wn-login-shell {
  min-height: 100vh;
  width: 100%;
}

.wn-app-shell {
  display: flex;
  height: 100vh;
  height: 100dvh; /* mobile browsers: exclude the URL bar, so the composer isn't hidden */
  overflow: hidden;
}

.wn-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.wn-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px;
  min-height: 0;
}
/* Pages stay readable on wide screens instead of stretching edge to edge. */
.wn-content-inner { max-width: 1440px; margin: 0 auto; min-height: 100%; }
.wn-content-narrow .wn-content-inner { max-width: 960px; }
/* The chat fills the available height and may use more width. */
.wn-content-chat { overflow: hidden; display: flex; }
.wn-content-chat .wn-content-inner { max-width: 1760px; width: 100%; height: 100%; display: flex; flex-direction: column; }

@media (max-width: 1199px) {
  .wn-content { padding: 16px; }
}
@media (max-width: 768px) {
  .wn-content { padding: 12px; padding-bottom: max(12px, env(safe-area-inset-bottom)); }
  /* Chat is edge-to-edge on phones, like a messaging app. */
  .wn-content-chat { padding: 0; }
}
@media (max-height: 500px) {
  .wn-content-chat { padding: 0; }
}
.wn-no-access { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }
.wn-no-access-card { background: white; border-radius: var(--wn-radius); box-shadow: var(--wn-shadow); padding: 28px; max-width: 420px; text-align: center; }
</style>
