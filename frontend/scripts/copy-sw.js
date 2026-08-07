// Copies the built service worker from the Vite output directory into
// www/whatsnext/sw.js so it's served at /whatsnext/sw.js — same directory
// as the app pages (/whatsnext, /whatsnext/settings, etc).
//
// This matters because a service worker's default scope is the directory
// it's served from. The Vite build itself lands under
// /assets/whatsnext/whatsnext_frontend/ (see vite.config.js `base`), and a
// script served from there can only ever control pages under that same
// path — never /whatsnext/* — without a Service-Worker-Allowed response
// header the app has no control over. Copying the identical file to a URL
// that already sits alongside the pages sidesteps that entirely: no header
// needed, scope just works.
import { existsSync, copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))

const src = resolve(__dirname, '../../whatsnext/public/whatsnext_frontend/sw.js')
const destDir = resolve(__dirname, '../../whatsnext/www/whatsnext')
const dest = resolve(destDir, 'sw.js')

if (!existsSync(src)) {
  console.error(`[copy-sw] Built service worker not found at ${src} — did vite build run first?`)
  process.exit(1)
}

mkdirSync(destDir, { recursive: true })
copyFileSync(src, dest)
console.log(`[copy-sw] Copied service worker to ${dest} (served at /whatsnext/sw.js)`)
