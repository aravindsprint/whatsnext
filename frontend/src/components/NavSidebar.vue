<script setup>
import AppLogo from './AppLogo.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const links = [
  { to: '/whatsnext/dashboard', label: 'Dashboard', icon: '📊' },
  { to: '/whatsnext', label: 'Chats', icon: '💬' },
  { to: '/whatsnext/templates', label: 'Templates', icon: '📋' },
  { to: '/whatsnext/campaigns', label: 'Campaigns', icon: '📢' },
  { to: '/whatsnext/recipients', label: 'Recipients', icon: '👥' },
  { to: '/whatsnext/messages', label: 'Message Logs', icon: '🗒️' },
]
</script>

<template>
  <aside class="wn-sidebar">
    <div class="wn-sidebar-top">
      <AppLogo />
    </div>
    <nav class="wn-nav">
      <router-link v-for="l in links" :key="l.to" :to="l.to" class="wn-nav-link" active-class="active">
        <span class="wn-nav-icon">{{ l.icon }}</span>
        <span>{{ l.label }}</span>
      </router-link>
      <router-link to="/whatsnext/settings" class="wn-nav-link" active-class="active">
        <span class="wn-nav-icon">⚙️</span>
        <span>Settings</span>
      </router-link>
    </nav>
    <div class="wn-sidebar-bottom">
      <router-link to="/whatsnext/about" class="wn-nav-link small">About</router-link>
      <button class="wn-logout" @click="auth.logout()">Log out</button>
    </div>
  </aside>
</template>

<style scoped>
.wn-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: white;
  border-right: 1px solid var(--wn-border);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
}
.wn-sidebar-top { padding: 4px 8px 20px; }
.wn-nav { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.wn-nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--wn-radius);
  color: var(--wn-text-muted);
  font-size: 14px;
  font-weight: 500;
}
.wn-nav-link:hover { background: var(--wn-teal-light); color: var(--wn-navy); }
.wn-nav-link.active { background: var(--wn-teal-light); color: var(--wn-teal); font-weight: 600; }
.wn-nav-icon { font-size: 16px; }
.wn-sidebar-bottom { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--wn-border); }
.small { font-size: 12px; color: var(--wn-text-muted); padding: 6px 12px; }
.wn-logout {
  background: none; border: none; text-align: left; padding: 8px 12px;
  color: var(--wn-red); font-size: 13px; font-weight: 500; border-radius: var(--wn-radius);
}
.wn-logout:hover { background: #fef2f2; }

@media (max-width: 768px) {
  .wn-sidebar { width: 64px; }
  .wn-logo-text, .wn-nav-link span:not(.wn-nav-icon), .small { display: none; }
}
</style>
