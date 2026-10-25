// Runs before `yarn dev`. The dev server proxies /api, /assets, /files and
// /socket.io to a Frappe site (vite.config.js reads WHATSNEXT_DEV_SITE). The
// first time, ask which site and save the answer to frontend/.env.local,
// which git ignores, so it never reaches GitHub or a deployed build.
//
// Skipped when WHATSNEXT_DEV_SITE is already set (in the shell or in
// .env.local), or when there is no terminal to ask in (CI, editors); vite then
// falls back to http://localhost:8000.
import { existsSync, readFileSync, appendFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createInterface } from 'node:readline/promises'

const __dirname = dirname(fileURLToPath(import.meta.url))
const envFile = resolve(__dirname, '../.env.local')
const DEFAULT_SITE = 'http://localhost:8000'

function savedSite() {
  if (!existsSync(envFile)) return ''
  const line = readFileSync(envFile, 'utf8').split(/\r?\n/).find((l) => /^\s*WHATSNEXT_DEV_SITE\s*=/.test(l))
  return line ? line.split('=').slice(1).join('=').trim() : ''
}

function normalise(answer) {
  let site = answer.trim() || DEFAULT_SITE
  if (!/^https?:\/\//i.test(site)) site = `https://${site}`
  return site.replace(/\/+$/, '')
}

async function main() {
  if (process.env.WHATSNEXT_DEV_SITE || savedSite()) return
  if (!process.stdin.isTTY) return

  const rl = createInterface({ input: process.stdin, output: process.stdout })
  try {
    const answer = await rl.question(
      `Which Frappe site should the dev server connect to? (${DEFAULT_SITE}) `
    )
    const site = normalise(answer)
    try {
      new URL(site)
    } catch {
      console.error(`[dev-site] "${site}" isn't a valid address; using ${DEFAULT_SITE} this time.`)
      return
    }
    const prefix = existsSync(envFile) && !readFileSync(envFile, 'utf8').endsWith('\n') ? '\n' : ''
    appendFileSync(envFile, `${prefix}WHATSNEXT_DEV_SITE=${site}\n`)
    console.log(`[dev-site] Saved ${site} to frontend/.env.local. Edit or delete that file to change it.`)
  } finally {
    rl.close()
  }
}

main()
