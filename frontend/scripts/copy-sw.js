// Copies the built service worker (and web app manifest) from the Vite
// output directory into www/whatsnext/ so they're served at
// /whatsnext/sw.js and /whatsnext/manifest.webmanifest — same directory
// as the app pages (/whatsnext, /whatsnext/settings, etc).
//
// This matters because a service worker's default scope is the directory
// it's served from. The Vite build itself lands under
// /assets/whatsnext/whatsnext_frontend/ (see vite.config.js `base`), and a
// script served from there can only ever control pages under that same
// path — never /whatsnext/* — without a Service-Worker-Allowed response
// header the app has no control over. Copying the identical files to a URL
// that already sits alongside the pages sidesteps that entirely: no header
// needed, scope just works.
//
// manifest.webmanifest has to be copied for a second, sharper reason: the
// generated sw.js precache list (see vite.config.js's `injectManifest`)
// includes an entry for "manifest.webmanifest" resolved against
// hooks.py's route (/whatsnext/manifest.webmanifest), NOT its real build
// path. If only sw.js is copied here, that precache entry 404s the moment
// the browser installs the worker — and because Workbox treats a failed
// precache fetch as a fatal install error, the service worker gets stuck
// in "installing" forever, never reaching "activated". Nothing throws a
// visible error in the app itself; anything gated on
// navigator.serviceWorker.ready (e.g. push notification subscribe) just
// hangs indefinitely with no explanation. Copying this file alongside
// sw.js is what makes that precache entry resolve.
import { existsSync, copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

const destDir = resolve(__dirname, '../../whatsnext/www/whatsnext')
mkdirSync(destDir, { recursive: true })

const files = ['sw.js', 'manifest.webmanifest']

for (const file of files) {
  const src = resolve(__dirname, `../../whatsnext/public/whatsnext_frontend/${file}`)
  const dest = resolve(destDir, file)

  if (!existsSync(src)) {
    console.error(`[copy-sw] Built file not found at ${src} — did vite build run first?`)
    process.exit(1)
  }

  copyFileSync(src, dest)
  console.log(`[copy-sw] Copied ${file} to ${dest} (served at /whatsnext/${file})`)
}
