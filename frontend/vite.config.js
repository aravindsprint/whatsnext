import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ command }) => ({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      // Switched from the default generateSW strategy to injectManifest:
      // generateSW builds the service worker entirely from config and has
      // no way to add our own event listeners, but real-time chat alerts
      // need a custom 'push' handler (to call showNotification with the
      // server's payload) and 'notificationclick' handler (to focus/open
      // the right conversation) — injectManifest lets us own src/sw.js
      // directly while workbox still injects the precache manifest into it.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      // whatsnext.html is a hand-written Jinja template (see www/whatsnext.py),
      // not vite's own generated index.html — so vite-plugin-pwa's normal
      // auto-injected <script> registration would never actually run; that
      // markup only gets added to the index.html vite itself builds, which
      // Frappe never serves. Registration is done manually in main.js
      // instead, so turn off the injection to avoid a dead, unused snippet.
      injectRegister: false,
      injectManifest: {
        // Keep the precached app-shell small; large generated JS chunks
        // are still fetched normally and cached at runtime as they load.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        // The built sw.js is copied to /whatsnext/sw.js at build time (see
        // scripts/copy-sw.js) so its registration scope covers the app's
        // pages. But workbox resolves each precache entry's url relative
        // to wherever the SW script itself is served from — without this
        // prefix, every asset URL would resolve relative to /whatsnext/
        // instead of the assets' real location, breaking precaching (and
        // potentially the SW install step) entirely.
        modifyURLPrefix: {
          '': '/assets/whatsnext/whatsnext_frontend/',
        },
      },
      devOptions: {
        enabled: true,
        type: 'module',
      },
      manifest: {
        name: 'Whatsnext — WhatsApp Hub',
        short_name: 'Whatsnext',
        theme_color: '#0F3D3E',
        background_color: '#0F3D3E',
        display: 'standalone',
        start_url: '/whatsnext',
        // Explicit, matching the real page directory (and the service
        // worker's own registration scope in main.js) — without this,
        // vite-plugin-pwa defaults scope to `base` (the assets directory),
        // which doesn't contain start_url and trips a browser warning.
        scope: '/whatsnext/',
        icons: [
          // Relative (no leading slash): vite-plugin-pwa prefixes these
          // with `base` when it writes manifest.webmanifest, so they
          // resolve to the actual served location
          // (/assets/whatsnext/whatsnext_frontend/icons/...). An absolute
          // path here is taken literally and skips that prefixing, which
          // is what produced the 404s on /icons/icon-192.png.
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-192-maskable.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  base: command === 'serve' ? '/' : '/assets/whatsnext/whatsnext_frontend/',
  build: {
    // Vite hashes output filenames per build (cache-busting). www/whatsnext.py
    // reads this manifest at request time to find the current entry/css
    // filenames instead of a hardcoded name that would silently 404 after
    // every rebuild.
    manifest: true,
    // Build straight into the app's public folder — this is what Frappe
    // actually serves (symlinked to sites/assets/whatsnext/whatsnext_frontend).
    // Without this, output lands in the default ./dist and never reaches
    // the served path, so both local `bench build` and Frappe Cloud's
    // deploy pipeline silently keep serving whatever was last built here.
    outDir: '../whatsnext/public/whatsnext_frontend',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    host: 'whatsnext.local',
    proxy: {
      '/api': {
        target: 'https://erp.pranera.in',
        changeOrigin: true,
        secure: false,
        cookieDomainRewrite: 'whatsnext.local',
        headers: {
          'Origin': 'https://erp.pranera.in',
          'Referer': 'https://erp.pranera.in'
        },
        configure(proxy) {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.removeHeader('expect')
          })
          proxy.on('proxyRes', (proxyRes) => {
            const setCookie = proxyRes.headers['set-cookie']
            if (setCookie) {
              proxyRes.headers['set-cookie'] = setCookie.map(c =>
                c.replace(/;\s*Secure/gi, '').replace(/;\s*SameSite=None/gi, '; SameSite=Lax')
              )
            }
          })
        }
      },
      '/assets': {
        target: 'https://erp.pranera.in',
        changeOrigin: true,
        secure: false
      },
      '/files': {
        target: 'https://erp.pranera.in',
        changeOrigin: true,
        secure: false
      },
      '/socket.io': {
        target: 'https://erp.pranera.in',
        changeOrigin: true,
        secure: false,
        ws: true
      }
    },
  },
  resolve: {
    alias: { '@': '/src' },
  },
}))
