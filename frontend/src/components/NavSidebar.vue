<script setup>
import { ref } from 'vue'
import AppLogo from './AppLogo.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const collapsed = ref(localStorage.getItem('wn-sidebar-collapsed') === '1')

function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem('wn-sidebar-collapsed', collapsed.value ? '1' : '0')
}

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
  <aside class="wn-sidebar" :class="{ collapsed }">
    <div class="wn-sidebar-top">
      <AppLogo v-if="!collapsed" />
      <button class="wn-collapse-btn" @click="toggleSidebar" :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: collapsed ? 'rotate(180deg)' : 'none' }">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>
    <nav class="wn-nav">
      <router-link v-for="l in links" :key="l.to" :to="l.to" class="wn-nav-link" active-class="active" :title="l.label">
        <span class="wn-nav-icon">{{ l.icon }}</span>
        <span v-if="!collapsed">{{ l.label }}</span>
      </router-link>
      <router-link to="/whatsnext/settings" class="wn-nav-link" active-class="active" title="Settings">
        <span class="wn-nav-icon">⚙️</span>
        <span v-if="!collapsed">Settings</span>
      </router-link>
    </nav>
    <div v-if="!collapsed" class="wn-sidebar-bottom">
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
  transition: width 0.18s ease;
}
.wn-sidebar.collapsed { width: 64px; padding: 16px 8px; }
.wn-sidebar-top { display: flex; align-items: center; justify-content: space-between; padding: 4px 8px 20px; }
.wn-sidebar.collapsed .wn-sidebar-top { justify-content: center; padding: 4px 0 20px; }
.wn-collapse-btn {
  background: none; border: none; cursor: pointer; padding: 6px;
  border-radius: 6px; color: var(--wn-text-muted); flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.wn-collapse-btn:hover { background: var(--wn-bg); color: var(--wn-teal); }
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
.wn-sidebar.collapsed .wn-nav-link { justify-content: center; padding: 10px 0; }
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
  .wn-sidebar:not(.collapsed) { width: 64px; }
  .wn-sidebar:not(.collapsed) .wn-nav-link span:not(.wn-nav-icon) { display: none; }
}
</style>
