// seed-auth.mjs — copy a signed-in session from one RUNNING dev instance into
// another, so a fresh worktree instance boots signed-in without the web login.
//
// Why this shape: the renderer keeps its ENTIRE signed-in state — the Firebase
// session (firebase.ts uses browserLocalPersistence) plus onboarding/prefs
// (omi-windows-prefs-v1) — in localStorage scoped to its ORIGIN. Two dev
// instances run on different ports, so different origins, so a raw copy of the
// Local Storage leveldb would land under the wrong origin key. Reading and
// writing localStorage over the Chrome DevTools Protocol translates origins
// naturally (it is JS `localStorage` on each side) and works while both apps are
// running — the normal dev state. CDP is exposed by OMI_DEV_REMOTE_DEBUG, which
// the packaged app never opens (dev/bench.ts gates it on !app.isPackaged), so
// this is structurally dev-only.
//
// Usage (run from the worktree's desktop/windows):
//   node scripts/seed-auth.mjs                 # from primary (9222) → this worktree
//   node scripts/seed-auth.mjs --to fix-orb    # → the named instance's derived CDP port
//   node scripts/seed-auth.mjs --from-port 9222 --to-port 9231
//   node scripts/seed-auth.mjs --auth-only     # copy only firebase:* + prefs
//   node scripts/seed-auth.mjs --dry-run       # show what WOULD be copied
//
// Both apps must already be running (`pnpm dev` in each checkout).
import { chromium } from 'playwright'
import {
  PRIMARY_CDP_PORT,
  deriveCdpPort,
  sanitizeInstanceName,
  resolveInstance
} from './lib/dev-ports.mjs'

function parseArgs(argv) {
  const opts = {
    fromPort: null,
    toPort: null,
    from: null,
    to: null,
    authOnly: false,
    dryRun: false
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--from-port') opts.fromPort = Number.parseInt(argv[++i], 10)
    else if (a === '--to-port') opts.toPort = Number.parseInt(argv[++i], 10)
    else if (a === '--from') opts.from = argv[++i]
    else if (a === '--to') opts.to = argv[++i]
    else if (a === '--auth-only') opts.authOnly = true
    else if (a === '--dry-run') opts.dryRun = true
    else if (a === '--help' || a === '-h') opts.help = true
    else throw new Error(`unknown argument: ${a}`)
  }
  return opts
}

/** Resolve source/target CDP ports from the flags, defaulting sensibly. */
function resolvePorts(opts) {
  // Source: explicit port > named instance > primary (the canonical signed-in profile).
  const fromPort =
    opts.fromPort ?? (opts.from ? deriveCdpPort(sanitizeInstanceName(opts.from)) : PRIMARY_CDP_PORT)
  // Target: explicit port > named instance > THIS worktree (resolved from cwd).
  const toPort =
    opts.toPort ??
    (opts.to
      ? deriveCdpPort(sanitizeInstanceName(opts.to))
      : resolveInstance(process.cwd()).cdpPort)
  return { fromPort, toPort }
}

/** Attach to a CDP endpoint and return the MAIN-window page (no #/bar, #/capture, #/insight-toast hash). */
async function connectMainPage(port, role) {
  let browser
  try {
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { timeout: 8000 })
  } catch {
    throw new Error(
      `could not reach a dev CDP endpoint on port ${port} (${role}). ` +
        `Is the ${role} app running? Start it with \`pnpm dev\` in that checkout ` +
        `(dev remote-debug is on by default; OMI_DEV_NO_REMOTE_DEBUG=1 disables it).`
    )
  }
  const pages = browser.contexts().flatMap((c) => c.pages())
  const isSubWindow = (u) => /#\/(bar|capture|insight-toast)/.test(u)
  const main = pages.find((p) => !isSubWindow(p.url())) ?? pages[0]
  if (!main) {
    await browser.close()
    throw new Error(`no renderer window found on port ${port} (${role}).`)
  }
  return { browser, page: main }
}

const AUTH_ONLY_MATCH = (k) => k.startsWith('firebase:') || k === 'omi-windows-prefs-v1'

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  if (opts.help) {
    console.log(
      [
        'Seed a signed-in session from one running dev instance into another.',
        '',
        '  node scripts/seed-auth.mjs [--from <name>|--from-port <n>] [--to <name>|--to-port <n>]',
        '                             [--auth-only] [--dry-run]',
        '',
        'Defaults: source = primary (CDP 9222), target = this worktree (derived from cwd).'
      ].join('\n')
    )
    return
  }

  const { fromPort, toPort } = resolvePorts(opts)
  if (fromPort === toPort) {
    throw new Error(
      `source and target CDP ports are the same (${fromPort}). Run this FROM the target ` +
        `worktree, or pass distinct --from-port/--to-port.`
    )
  }
  console.log(`[seed-auth] source CDP ${fromPort} → target CDP ${toPort}`)

  const src = await connectMainPage(fromPort, 'source')
  let data
  try {
    data = await src.page.evaluate(() => {
      const out = {}
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i)
        out[k] = localStorage.getItem(k)
      }
      return out
    })
  } finally {
    await src.browser.close()
  }

  let keys = Object.keys(data)
  if (opts.authOnly) keys = keys.filter(AUTH_ONLY_MATCH)
  const hasFirebaseUser = keys.some((k) => k.startsWith('firebase:authUser:'))
  if (keys.length === 0) {
    throw new Error('source localStorage is empty — is the source app signed in / onboarded?')
  }
  if (!hasFirebaseUser) {
    console.warn(
      '[seed-auth] WARNING: no firebase:authUser:* key in the source — it is not signed in. ' +
        'Seeding onboarding/prefs only; the target will still need a web login.'
    )
  }
  console.log(`[seed-auth] copying ${keys.length} localStorage key(s):`)
  for (const k of keys) console.log(`             • ${k}`)

  if (opts.dryRun) {
    console.log('[seed-auth] --dry-run: not writing to the target.')
    return
  }

  const dst = await connectMainPage(toPort, 'target')
  try {
    const entries = keys.map((k) => [k, data[k]])
    await dst.page.evaluate((pairs) => {
      for (const [k, v] of pairs) localStorage.setItem(k, v)
    }, entries)
    // Firebase rehydrates the session from localStorage at init, so reload the
    // target renderer to pick up the seeded session.
    await dst.page.reload({ waitUntil: 'domcontentloaded', timeout: 15000 })
  } finally {
    await dst.browser.close()
  }

  console.log(
    `[seed-auth] done — target reloaded. ${hasFirebaseUser ? 'It should now be signed in.' : 'Onboarding/prefs seeded.'}`
  )
}

main().catch((err) => {
  console.error(`[seed-auth] ${err.message}`)
  process.exit(1)
})
