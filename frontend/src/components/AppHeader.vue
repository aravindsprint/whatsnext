<script setup>
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()

const titles = {
  home: 'Chats',
  dashboard: 'Dashboard',
  templates: 'Message Templates',
  campaigns: 'Campaigns',
  recipients: 'Recipient Lists',
  messages: 'Message Logs',
  settings: 'Automate',
  about: 'About',
}
const title = computed(() => titles[route.name] || 'Whatsnext')
</script>

<template>
  <header class="wn-header">
    <h1>{{ title }}</h1>
    <div class="wn-header-right">
      <span class="wn-user">{{ auth.user }}</span>
    </div>
  </header>
</template>

<style scoped>
.wn-header {
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: white;
  border-bottom: 1px solid var(--wn-border);
}
.wn-header h1 { font-size: 16px; font-weight: 600; margin: 0; }
.wn-user { font-size: 13px; color: var(--wn-text-muted); }
</style>
