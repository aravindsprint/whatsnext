<script setup>
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { navOpen } from '@/lib/layout'

const route = useRoute()
const auth = useAuthStore()

const titles = {
  home: 'Chats',
  dashboard: 'Dashboard',
  templates: 'Message Templates',
  campaigns: 'Campaigns',
  recipients: 'Recipient Lists',
  messages: 'Message Logs',
  notifications: 'Notifications',
  reports: 'Agent Reports',
  settings: 'Settings',
  about: 'About',
}
const title = computed(() => titles[route.name] || 'Whatsnext')
const initial = computed(() => (auth.fullName || auth.user || '?').charAt(0).toUpperCase())
</script>

<template>
  <header class="wn-header">
    <button class="wn-menu-btn" type="button" aria-label="Open menu" @click="navOpen = true">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="7" x2="20" y2="7" /><line x1="4" y1="12" x2="20" y2="12" /><line x1="4" y1="17" x2="20" y2="17" /></svg>
    </button>
    <h1>{{ title }}</h1>
    <div class="wn-header-right" :title="auth.user">
      <span class="wn-user">{{ auth.fullName || auth.user }}</span>
      <span class="wn-user-avatar">{{ initial }}</span>
    </div>
  </header>
</template>

<style scoped>
.wn-header {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 24px;
  padding-top: env(safe-area-inset-top);
  background: white;
  border-bottom: 1px solid var(--wn-border);
}
.wn-header h1 { flex: 1; min-width: 0; font-size: 16px; font-weight: 600; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wn-header-right { display: flex; align-items: center; gap: 8px; min-width: 0; }
.wn-user { font-size: 13px; color: var(--wn-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }
.wn-user-avatar { width: 30px; height: 30px; border-radius: 50%; background: var(--wn-teal-light); color: var(--wn-teal); font-weight: 700; font-size: 13px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.wn-menu-btn { display: none; background: none; border: none; padding: 6px; margin-left: -6px; color: var(--wn-text); border-radius: 8px; }
.wn-menu-btn:hover { background: var(--wn-bg); }

@media (max-width: 1199px) {
  .wn-header { padding: 0 16px; }
}
@media (max-height: 500px) {
  .wn-header { height: 44px; }
}
@media (max-width: 768px) {
  .wn-header { height: 52px; padding: 0 12px; gap: 8px; }
  .wn-menu-btn { display: inline-flex; }
  .wn-user { display: none; }
}
</style>
