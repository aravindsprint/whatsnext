<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppLogo from './AppLogo.vue'
import { useAuthStore } from '@/stores/auth'
import { navOpen, PHONE_MAX, RAIL_MAX } from '@/lib/layout'

const auth = useAuthStore()
const route = useRoute()

// Three layouts:
//  - phone (≤768px): hidden; slides in over the page from the ☰ button
//  - tablet / small laptop (769–1199px): icon rail, unless the user expanded it
//  - laptop / desktop (≥1200px): full sidebar, unless the user collapsed it
// The user's own choice is remembered separately for the two wider modes.
function readPref(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function writePref(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

const width = ref(window.innerWidth)
const isPhone = ref(width.value <= PHONE_MAX)
const isRail = ref(width.value > PHONE_MAX && width.value <= RAIL_MAX)
const prefKey = () => (isRail.value ? 'wn-sidebar-collapsed-tablet' : 'wn-sidebar-collapsed')
const collapsed = ref(false)

function applyWidth() {
  width.value = window.innerWidth
  isPhone.value = width.value <= PHONE_MAX
  isRail.value = width.value > PHONE_MAX && width.value <= RAIL_MAX
  const pref = readPref(prefKey())
  collapsed.value = isPhone.value ? false : pref === null ? isRail.value : pref === '1'
  if (!isPhone.value) navOpen.value = false
}

function toggleSidebar() {
  if (isPhone.value) {
    navOpen.value = false
    return
  }
  collapsed.value = !collapsed.value
  writePref(prefKey(), collapsed.value ? '1' : '0')
}

let resizeTimer
function onResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(applyWidth, 100)
}
function onKey(e) {
  if (e.key === 'Escape') navOpen.value = false
}

onMounted(() => {
  applyWidth()
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onKey)
})
watch(() => route.fullPath, () => { navOpen.value = false })

const links = [
  { to: '/whatsnext/dashboard', label: 'Dashboard', icon: '📊' },
  { to: '/whatsnext', label: 'Chats', icon: '💬', exact: true },
  { to: '/whatsnext/templates', label: 'Templates', icon: '📋' },
  { to: '/whatsnext/campaigns', label: 'Campaigns', icon: '📢' },
  { to: '/whatsnext/recipients', label: 'Recipients', icon: '👥' },
  { to: '/whatsnext/messages', label: 'Message Logs', icon: '🗒️' },
  { to: '/whatsnext/reports', label: 'Reports', icon: '📈' },
]
const adminLinks = [
  { to: '/whatsnext/notifications', label: 'Notifications', icon: '⚡' },
]
</script>

<template>
  <div v-if="isPhone && navOpen" class="wn-nav-backdrop" @click="navOpen = false"></div>
  <aside class="wn-sidebar" :class="{ collapsed: collapsed && !isPhone, phone: isPhone, open: isPhone && navOpen }"
         :aria-hidden="isPhone && !navOpen ? 'true' : 'false'">
    <div class="wn-sidebar-top">
      <AppLogo v-if="!collapsed || isPhone" />
      <button class="wn-collapse-btn" @click="toggleSidebar"
              :title="isPhone ? 'Close menu' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
              :aria-label="isPhone ? 'Close menu' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'">
        <svg v-if="isPhone" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" /></svg>
        <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :style="{ transform: collapsed ? 'rotate(180deg)' : 'none' }">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
    </div>
    <nav class="wn-nav">
      <router-link v-for="l in links" :key="l.to" :to="l.to" class="wn-nav-link"
                   :active-class="l.exact ? '' : 'active'" :exact-active-class="'active'" :title="l.label">
        <span class="wn-nav-icon">{{ l.icon }}</span>
        <span class="wn-nav-label">{{ l.label }}</span>
      </router-link>
      <template v-if="auth.isSystemManager">
        <router-link v-for="l in adminLinks" :key="l.to" :to="l.to" class="wn-nav-link" active-class="active" :title="l.label">
          <span class="wn-nav-icon">{{ l.icon }}</span>
          <span class="wn-nav-label">{{ l.label }}</span>
        </router-link>
      </template>
      <router-link to="/whatsnext/settings" class="wn-nav-link" active-class="active" title="Settings">
        <span class="wn-nav-icon">⚙️</span>
        <span class="wn-nav-label">Settings</span>
      </router-link>
    </nav>
    <div class="wn-sidebar-bottom">
      <router-link to="/whatsnext/about" class="wn-nav-link small" active-class="active" title="About">
        <span class="wn-nav-icon">ℹ️</span>
        <span class="wn-nav-label">About</span>
      </router-link>
      <button class="wn-nav-link wn-logout" title="Log out" @click="auth.logout()">
        <span class="wn-nav-icon">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
        </span>
        <span class="wn-nav-label">Log out</span>
      </button>
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
  transition: width 0.18s ease, transform 0.2s ease;
  overflow-y: auto;
  overflow-x: hidden;
}
.wn-sidebar.collapsed { width: 64px; padding: 16px 8px; }
.wn-sidebar.collapsed .wn-nav-label { display: none; }
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
  white-space: nowrap;
  text-decoration: none;
}
.wn-sidebar.collapsed .wn-nav-link { justify-content: center; padding: 10px 0; }
.wn-nav-link:hover { background: var(--wn-teal-light); color: var(--wn-navy); }
.wn-nav-link.active { background: var(--wn-teal-light); color: var(--wn-teal); font-weight: 600; }
.wn-nav-icon { font-size: 16px; width: 20px; text-align: center; display: inline-flex; justify-content: center; flex-shrink: 0; }
.wn-sidebar-bottom { display: flex; flex-direction: column; gap: 2px; padding-top: 12px; border-top: 1px solid var(--wn-border); }
.wn-nav-link.small { font-size: 13px; }
.wn-logout { background: none; border: none; width: 100%; text-align: left; color: var(--wn-red); cursor: pointer; font-family: inherit; }
.wn-logout:hover { background: #fef2f2; color: var(--wn-red); }

/* Phones: off-canvas drawer over the page. */
.wn-sidebar.phone {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: min(280px, 82vw);
  z-index: 70;
  transform: translateX(-105%);
  box-shadow: 4px 0 24px rgba(15, 61, 62, 0.18);
  padding-top: max(16px, env(safe-area-inset-top));
  padding-bottom: max(16px, env(safe-area-inset-bottom));
}
.wn-sidebar.phone.open { transform: translateX(0); }
.wn-sidebar.phone .wn-nav-link { padding: 12px; font-size: 15px; }
.wn-nav-backdrop { position: fixed; inset: 0; background: rgba(15, 61, 62, 0.35); z-index: 65; }
@media (prefers-reduced-motion: reduce) {
  .wn-sidebar { transition: none; }
}
</style>
