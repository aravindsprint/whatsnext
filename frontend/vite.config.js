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
      injectManifest: {
        // Keep the precached app-shell small; large generated JS chunks
        // are still fetched normally and cached at runtime as they load.
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
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
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-192-maskable.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
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
    proxy: {
      '/api': { target: process.env.VITE_DEV_BACKEND || 'http://localhost:8000', changeOrigin: true },
      '/files': { target: process.env.VITE_DEV_BACKEND || 'http://localhost:8000', changeOrigin: true },
    },
  },
  resolve: {
    alias: { '@': '/src' },
  },
}))
