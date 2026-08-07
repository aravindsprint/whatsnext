import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'

createApp(App).use(createPinia()).use(router).mount('#app')

// Manual service worker registration — vite-plugin-pwa's normal
// auto-injected registration script never runs here, because
// www/whatsnext.html is a hand-written Jinja template rather than the
// index.html Vite itself builds, so that injected snippet never ships to
// the browser. In production this deliberately targets /whatsnext/sw.js
// (a build-time copy of the same file — see scripts/copy-sw.js) rather
// than its real build path under /assets/whatsnext/whatsnext_frontend/:
// a service worker's default scope is the directory it's served from, and
// only /whatsnext/sw.js sits in the same directory as the pages
// (/whatsnext, /whatsnext/settings, ...) that need it to control them.
if ('serviceWorker' in navigator) {
  const swUrl = import.meta.env.PROD ? '/whatsnext/sw.js' : '/sw.js'
  const scope = import.meta.env.PROD ? '/whatsnext/' : '/'
  navigator.serviceWorker.register(swUrl, { scope }).catch((err) => {
    console.error('Service worker registration failed:', err)
  })
}
