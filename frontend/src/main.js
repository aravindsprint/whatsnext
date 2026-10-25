import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'

import { getSessionUser, isLoggedIn } from './api/frappe'
import { ensureCacheOwner } from './db'
import tableLabels from './lib/tableLabels'
import { registerServiceWorker, recoverFromMissingChunks } from './lib/appUpdate'

// Before anything reads the offline cache: drop it if it belongs to a
// different user than the one now logged in.
const ready = isLoggedIn() ? ensureCacheOwner(getSessionUser()) : Promise.resolve()
ready.finally(() => {
  createApp(App).use(createPinia()).use(router).directive('table-labels', tableLabels).mount('#app')
})

// Manual service worker registration — vite-plugin-pwa's normal
// auto-injected registration script never runs here, because
// www/whatsnext.html is a hand-written Jinja template rather than the
// index.html Vite itself builds. It targets /whatsnext/sw.js (a build-time
// copy, see scripts/copy-sw.js) so its scope covers the app's pages.
// lib/appUpdate.js also keeps open tabs on the latest deployed build.
registerServiceWorker()
recoverFromMissingChunks(router)
