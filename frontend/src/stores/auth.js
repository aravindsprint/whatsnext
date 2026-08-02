import { defineStore } from 'pinia'
import { isLoggedIn, getSessionUser, login as apiLogin, logout as apiLogout, call } from '@/api/frappe'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: getSessionUser(),
    roles: [],
    isSystemManager: false,
    loggingIn: false,
    error: null,
  }),
  getters: {
    loggedIn: () => isLoggedIn(),
  },
  actions: {
    async login(usr, pwd) {
      this.loggingIn = true
      this.error = null
      try {
        await apiLogin(usr, pwd)
      } catch (e) {
        this.error = e.message
      } finally {
        this.loggingIn = false
      }
    },
    async logout() {
      await apiLogout()
    },
    async loadWhoAmI() {
      if (!isLoggedIn()) return
      try {
        const res = await call('whatsnext.whatsnext.api.whoami', {}, 'GET')
        this.user = res.user
        this.roles = res.roles
        this.isSystemManager = res.is_system_manager
      } catch {
        // non-fatal — settings page will just stay hidden
      }
    },
  },
})
