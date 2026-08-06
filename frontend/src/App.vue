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
  <div v-else class="wn-app-shell">
    <NavSidebar />
    <div class="wn-main">
      <AppHeader />
      <div class="wn-content">
        <router-view />
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
  padding: 24px;
}

@media (max-width: 768px) {
  .wn-content { padding: 12px; }
}
</style>
