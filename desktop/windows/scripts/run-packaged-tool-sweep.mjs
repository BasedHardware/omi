// Packaged-build TOOL SWEEP — exercises every agent-reachable Omi tool in the
// REAL packaged runtime through the LLM-free door, and prints a pass/fail table.
//
// WHY THIS EXISTS. The coding-agent "check my goals" failure was a tool-EXPOSURE
// bug (product tools were invisible to the coding agent's omi MCP), fixed in
// controlMcpBridge.ts. This script answers the second question — "do the tool
// EXECUTORS themselves work in the packaged runtime (native better-sqlite3, the
// backend session/apiBase, asar-unpacked resources)?" — by calling each tool via
// `window.omi.voiceToolExecute` (voiceHub:execute → executeHostTool), the SAME
// in-process host-tool door the coding agent's MCP now dispatches into. It is
// LLM-free: it needs a signed-in Firebase owner, NOT Claude credentials, so it is
// unaffected by expired agent OAuth.
//
// WHAT IT DOES
//   1. Takes an already-built dist/win-unpacked (or --app-dir).
//   2. Creates a THROWAWAY userData profile and seeds the signed-in Firebase
//      session into it: firebase-auth.json (main-side safeStorage/DPAPI session)
//      PLUS the renderer state that gates the signed-in UI — Local State (the
//      Chromium os_crypt key), Local Storage + IndexedDB (the onboarding-complete
//      flag / prefs / Firebase persistence leveldb, encrypted with that key). All
//      decryptable because the throwaway profile runs as the same Windows user.
//      Never touches the real profile — copies out, read-only. Without Local State
//      + Local Storage the app boots to onboarding and never relays the session,
//      so the owner is never wired and waitForOwner times out.
//   3. Boots the real exe with that isolated profile + a CDP port.
//   4. Waits for the signed-in owner to be wired (voiceToolExecute stops
//      returning "sign-in has not completed").
//   5. Calls each read-only tool with benign args; records OK / ERROR / SKIPPED.
//   6. Prints a table and exits non-zero if any non-skipped tool errored.
//   7. Kills the isolated app and removes the throwaway profile.
//
// LIVE + NOT HERMETIC: needs a machine already signed in to Omi (real Firebase
// session) and hits the real backend. NOT wired into `pnpm test` / CI. Run after a
// build:
//   pnpm build:win
//   pnpm smoke:packaged-tools
//
// Env overrides:
//   OMI_SMOKE_APP_DIR   — path to win-unpacked (default: ./dist/win-unpacked)
//   OMI_SMOKE_AUTH_FILE — firebase-auth.json to seed (default: %APPDATA%/omi-windows/firebase-auth.json)
//   OMI_SMOKE_DB_FILE   — optional omi.db to seed for real LOCAL-tool data (default: none → fresh empty db)
//   OMI_SMOKE_CDP_PORT  — CDP port (default: 9533)

import { spawn, execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function arg(name) {
  const i = process.argv.indexOf(name)
  return i >= 0 ? process.argv[i + 1] : undefined
}

const APP_DIR =
  arg('--app-dir') || process.env.OMI_SMOKE_APP_DIR || path.join(ROOT, 'dist', 'win-unpacked')
const EXE = path.join(APP_DIR, 'omi-windows.exe')
// The signed-in profile to copy the session + renderer state OUT of (read-only).
const SRC_PROFILE =
  process.env.OMI_SMOKE_SRC_PROFILE || path.join(process.env.APPDATA || '', 'omi-windows')
const AUTH_FILE = process.env.OMI_SMOKE_AUTH_FILE || path.join(SRC_PROFILE, 'firebase-auth.json')
const DB_FILE = process.env.OMI_SMOKE_DB_FILE || ''
const CDP_PORT = Number(process.env.OMI_SMOKE_CDP_PORT || 9533)

// Renderer state that must ride along with firebase-auth.json so the app boots
// signed-in AND past onboarding (else it shows onboarding and never relays the
// session). Best-effort: a missing one is skipped.
const SEED_RENDERER_STATE = ['Local State', 'Local Storage', 'IndexedDB', 'Session Storage']

// The agent-reachable tools, with benign read-only args. `mutation`/`native-ui`
// tools are SKIPPED with a documented reason — they share the same session/db
// infrastructure the read tools exercise, and running them would create backend
// rows or capture the user's screen. `expectError` marks a tool whose benign input
// deliberately yields a validation error string (still proves the executor ran).
const SWEEP = [
  // --- backend-backed reads (prove session/apiBase/net.fetch in packaged) ---
  { name: 'get_goals', args: {} },
  { name: 'get_memories', args: {} },
  { name: 'search_memories', args: { query: 'notes' } },
  { name: 'get_conversations', args: { limit: 3 } },
  { name: 'search_conversations', args: { query: 'notes' } },
  { name: 'get_action_items', args: { limit: 5 } },
  // --- local reads (prove native better-sqlite3 + resource paths in packaged) ---
  { name: 'execute_sql', args: { query: 'SELECT 1 AS ok' } },
  { name: 'search_tasks', args: { query: 'anything' } },
  { name: 'semantic_search', args: { query: 'anything', days: 7 } },
  { name: 'get_daily_recap', args: { days_ago: 1 } },
  { name: 'get_work_context', args: {} },
  // --- validation-only (proves the product executor is reached, no mutation) ---
  {
    name: 'save_knowledge_graph',
    args: { nodes: [], edges: [] },
    expectError: /no valid nodes to save/
  },
  // --- a read-only control tool (proves the control path in packaged) ---
  { name: 'list_agent_sessions', args: {} },
  // --- skipped: mutations / native UI / cost ---
  { name: 'create_action_item', skip: 'mutation — would create a real backend task' },
  { name: 'update_action_item', skip: 'mutation — needs an existing task id' },
  { name: 'complete_task', skip: 'mutation — needs an existing task id' },
  { name: 'delete_task', skip: 'destructive — would delete a real task' },
  { name: 'capture_screen', skip: 'native UI — captures the user screen; needs consent gate' },
  { name: 'spawn_agent', skip: 'starts a real background agent / costs tokens' }
]

// The agent-control tools return a JSON `{ok:...}` envelope; product tools return
// an opaque string (or an "Error: …" string on failure). Only list_agent_sessions
// is swept here.
const CONTROL_TOOL_NAMES = new Set(['list_agent_sessions'])
function isAgentControlTool(name) {
  return CONTROL_TOOL_NAMES.has(name)
}

function fail(msg) {
  console.error(`\n[packaged-tool-sweep] FAIL: ${msg}\n`)
  process.exitCode = 1
}

if (!existsSync(EXE)) {
  fail(`packaged exe not found at ${EXE}\n  Build first: pnpm build:win`)
  process.exit(1)
}
if (!existsSync(AUTH_FILE)) {
  fail(
    `no Firebase session at ${AUTH_FILE}\n  Sign in to Omi in the app first, or set OMI_SMOKE_AUTH_FILE.`
  )
  process.exit(1)
}

const chromium = require('playwright').chromium
const profileDir = mkdtempSync(path.join(tmpdir(), 'omi-pkg-tool-sweep-'))
const logFile = path.join(profileDir, 'app.log')
let child = null

function cleanup() {
  try {
    if (child && child.pid) {
      execFileSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], {
        windowsHide: true,
        stdio: 'ignore'
      })
    }
  } catch {
    /* already gone */
  }
  try {
    rmSync(profileDir, { recursive: true, force: true })
  } catch {
    /* best effort */
  }
}

async function main() {
  // Seed the isolated profile: the signed-in Firebase session goes where the app's
  // encrypted persistence reads it — <userData>/firebase-auth.json — plus the
  // renderer state (Local State key + Local Storage/IndexedDB) that gates the
  // signed-in, past-onboarding UI.
  mkdirSync(profileDir, { recursive: true })
  cpSync(AUTH_FILE, path.join(profileDir, 'firebase-auth.json'))
  for (const name of SEED_RENDERER_STATE) {
    const src = path.join(SRC_PROFILE, name)
    if (existsSync(src)) {
      cpSync(src, path.join(profileDir, name), { recursive: true })
    }
  }
  console.log(`[packaged-tool-sweep] seeded session + renderer state from ${SRC_PROFILE}`)
  if (DB_FILE && existsSync(DB_FILE)) {
    cpSync(DB_FILE, path.join(profileDir, 'omi.db'))
    console.log(`[packaged-tool-sweep] seeded omi.db from ${DB_FILE}`)
  }

  const logStream = require('node:fs').createWriteStream(logFile)
  console.log(`[packaged-tool-sweep] booting ${EXE}`)
  console.log(`[packaged-tool-sweep] isolated profile: ${profileDir}`)
  child = spawn(EXE, [`--user-data-dir=${profileDir}`, `--remote-debugging-port=${CDP_PORT}`], {
    env: { ...process.env, OMI_AUTOMATION: '0' },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  })
  child.stdout.pipe(logStream)
  child.stderr.pipe(logStream)

  const browser = await connectWithRetry(`http://127.0.0.1:${CDP_PORT}`, 30_000)
  const page = await findMainPage(browser, 25_000)
  if (!page) throw new Error('main app window (index.html) never appeared')

  // The app mounts the authed shell (which relays the pi-mono session → owner)
  // only when onboarding is complete: `onboarded = isOnboardingComplete()` and
  // that is `typeof prefs.onboardingCompletedAt === 'number'` (App.tsx /
  // lib/preferences.ts). The seeded prefs can lack it (leveldb flush/origin
  // timing), leaving the app on the wizard so it never relays. The real user IS
  // onboarded, so mark it complete + reload — the same shape as the app's own
  // dev/e2e onboarded-bypass. Firebase itself is already signed in from the seed.
  await page.evaluate(() => {
    const KEY = 'omi-windows-prefs-v1'
    let prefs = {}
    try {
      prefs = JSON.parse(localStorage.getItem(KEY) || '{}')
    } catch {
      prefs = {}
    }
    if (typeof prefs.onboardingCompletedAt !== 'number') {
      prefs.onboardingCompletedAt = Date.now()
      localStorage.setItem(KEY, JSON.stringify(prefs))
    }
  })
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {})

  // Wait for the signed-in owner to be wired (renderer relays the Firebase session
  // to main → setControlPlaneOwner). Until then voiceToolExecute fails closed.
  await waitForOwner(page, 60_000)

  const results = []
  for (const t of SWEEP) {
    if (t.skip) {
      results.push({ name: t.name, status: 'SKIPPED', detail: t.skip })
      continue
    }
    const out = await page.evaluate(
      async ({ name, args }) => {
        try {
          const r = await window.omi.voiceToolExecute({
            name,
            argumentsJSON: JSON.stringify(args)
          })
          return { ok: true, result: String(r) }
        } catch (e) {
          return { ok: false, result: String(e) }
        }
      },
      { name: t.name, args: t.args }
    )
    const raw = (out.result || '').replace(/\s+/g, ' ').trim()
    const preview = raw.slice(0, 140)
    // Failure signal: a product executor returns an "Error: …" STRING on failure
    // (this is exactly how the bug surfaced: "Error: index.getBackendSession is not
    // a function"). A structured JSON result — even one with `ok:false` and a
    // `failure_code` like get_work_context's `no_recent_capture` — is a VALID
    // executor response, not a failure. A control tool (list_agent_sessions) returns
    // a JSON envelope; flag it only if that envelope is `ok:false`.
    let status = 'OK'
    if (t.expectError) {
      status = t.expectError.test(raw) ? 'OK' : 'ERROR'
    } else if (!out.ok) {
      status = 'ERROR'
    } else if (/^Error:/i.test(raw)) {
      status = 'ERROR'
    } else if (isAgentControlTool(t.name) && /^\{/.test(raw) && /"ok"\s*:\s*false/.test(raw)) {
      status = 'ERROR'
    }
    results.push({ name: t.name, status, detail: preview })
  }

  await browser.close().catch(() => {})

  // --- table ---
  console.log('\n=== PACKAGED TOOL SWEEP (via voiceToolExecute — LLM-free) ===')
  const pad = (s, n) => (s + ' '.repeat(n)).slice(0, n)
  console.log(`${pad('TOOL', 24)} ${pad('STATUS', 8)} DETAIL`)
  console.log('-'.repeat(100))
  for (const r of results) {
    console.log(`${pad(r.name, 24)} ${pad(r.status, 8)} ${r.detail}`)
  }
  const errors = results.filter((r) => r.status === 'ERROR')
  const oks = results.filter((r) => r.status === 'OK')
  const skips = results.filter((r) => r.status === 'SKIPPED')
  console.log('-'.repeat(100))
  console.log(`OK: ${oks.length}   ERROR: ${errors.length}   SKIPPED: ${skips.length}\n`)

  if (errors.length > 0) {
    let log = ''
    try {
      log = readFileSync(logFile, 'utf8')
    } catch {
      /* ignore */
    }
    const tail = log
      .split('\n')
      .filter((l) => /tool|relay|goal|error|backend|sql|sqlite/i.test(l))
      .slice(-15)
      .join('\n')
    throw new Error(
      `${errors.length} tool(s) errored: ${errors.map((e) => e.name).join(', ')}\n--- app log tail ---\n${tail}`
    )
  }
  console.log('[packaged-tool-sweep] PASS — every exercised tool succeeded.\n')
}

async function waitForOwner(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let last = ''
  while (Date.now() < deadline) {
    const r = await page.evaluate(async () => {
      try {
        return String(await window.omi.voiceToolExecute({ name: 'get_goals', argumentsJSON: '{}' }))
      } catch (e) {
        return `threw: ${String(e)}`
      }
    })
    last = r
    if (!/sign-in has not completed/i.test(r)) {
      console.log('[packaged-tool-sweep] signed-in owner is ready.')
      return
    }
    await sleep(1000)
  }
  throw new Error(`signed-in owner never wired within ${timeoutMs}ms (last: ${last.slice(0, 120)})`)
}

async function connectWithRetry(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let lastErr
  while (Date.now() < deadline) {
    try {
      return await chromium.connectOverCDP(url)
    } catch (e) {
      lastErr = e
      await sleep(500)
    }
  }
  throw new Error(`could not connect to CDP at ${url}: ${lastErr}`)
}

async function findMainPage(browser, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    for (const ctx of browser.contexts()) {
      for (const p of ctx.pages()) {
        const u = p.url()
        if (u.includes('index.html') && !u.includes('#/')) return p
      }
    }
    await sleep(500)
  }
  return null
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    try {
      cleanup()
    } finally {
      process.exit(130)
    }
  })
}

main()
  .catch((e) => fail(e && e.stack ? e.stack : String(e)))
  .finally(cleanup)
