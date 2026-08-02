import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/api/frappe'

const routes = [
  { path: '/whatsnext/login', name: 'login', component: () => import('@/pages/login/LoginPage.vue') },
  { path: '/whatsnext', name: 'home', component: () => import('@/pages/home/HomePage.vue') },
  { path: '/whatsnext/dashboard', name: 'dashboard', component: () => import('@/pages/dashboard/DashboardPage.vue') },
  { path: '/whatsnext/templates', name: 'templates', component: () => import('@/pages/templates/TemplatesPage.vue') },
  { path: '/whatsnext/campaigns', name: 'campaigns', component: () => import('@/pages/campaigns/CampaignsPage.vue') },
  { path: '/whatsnext/recipients', name: 'recipients', component: () => import('@/pages/recipients/RecipientsPage.vue') },
  { path: '/whatsnext/messages', name: 'messages', component: () => import('@/pages/message-log/MessageLogPage.vue') },
  { path: '/whatsnext/settings', name: 'settings', component: () => import('@/pages/settings/SettingsPage.vue'), meta: { systemManagerOnly: true } },
  { path: '/whatsnext/about', name: 'about', component: () => import('@/pages/about/AboutPage.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.name !== 'login' && !isLoggedIn()) {
    return { name: 'login' }
  }
  if (to.name === 'login' && isLoggedIn()) {
    return { name: 'home' }
  }
  return true
})

export default router
