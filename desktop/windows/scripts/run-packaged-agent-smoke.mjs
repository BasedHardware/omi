// Packaged-build agent smoke — the test that would have caught the
// "-32603 Internal error on every agent spawn" packaging bug.
//
// WHY THIS EXISTS (and why the existing vitest agent E2E did not catch it):
// src/main/codingAgent/acp.e2e.test.ts constructs AcpRuntimeAdapter DIRECTLY and
// points `acpEntry` at the on-disk source claude-acp-entry.mjs — so it exercises
// neither the `?asset` runtime path resolution nor the packaged app.asar layout.
// The packaging bug lived precisely there: the `?asset` entry resolved INSIDE
// app.asar, and the SDK could not exec claude.exe from the archive. Only booting
// the REAL packaged binary and spawning through the REAL ClaudeCodeRuntimeAdapter
// (which uses `?asset`) reproduces it. This script does exactly that.
//
// WHAT IT DOES
//   1. Takes an already-built dist/win-unpacked (or an explicit --app-dir).
//   2. Creates a THROWAWAY userData profile and seeds the signed-in Claude agent
//      creds into it (never touches the real profile — copies out, read-only).
//   3. Boots the real exe with that isolated profile + a CDP port.
//   4. Drives window.omi.codingAgentRun('acp', ...) — the exact path a user's
//      agent spawn takes — and asserts the run reaches ok:true with text output.
//   5. Fails loudly (non-zero exit) if the run returns "Internal error" or any
//      failure, printing the app's ACP spawn log for diagnosis.
//   6. Kills the isolated app and removes the throwaway profile.
//
// LIVE + NOT HERMETIC: needs a machine already signed in to Claude in the Omi app
// (real OAuth creds) and costs a few cents per run. It is therefore NOT wired into
// `pnpm test` / CI. Run it locally after a build:
//
//   pnpm build:win            # or: pnpm exec electron-vite build && pnpm exec electron-builder --dir --config electron-builder.config.mjs
//   pnpm smoke:packaged-agent  # this script
//
// Env overrides:
//   OMI_SMOKE_APP_DIR    — path to the win-unpacked dir (default: ./dist/win-unpacked)
//   OMI_SMOKE_CREDS_DIR  — path to a claude-agent creds dir to seed
//                          (default: %APPDATA%/omi-windows/claude-agent)
//   OMI_SMOKE_CDP_PORT   — CDP port (default: 9522)

import { spawn } from 'node:child_process'
import { execFileSync } from 'node:child_process'
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

const APP_DIR = arg('--app-dir') || process.env.OMI_SMOKE_APP_DIR || path.join(ROOT, 'dist', 'win-unpacked')
const EXE = path.join(APP_DIR, 'omi-windows.exe')
const CREDS_DIR =
  process.env.OMI_SMOKE_CREDS_DIR ||
  path.join(process.env.APPDATA || '', 'omi-windows', 'claude-agent')
const CDP_PORT = Number(process.env.OMI_SMOKE_CDP_PORT || 9522)
const PROMPT =
  'Reply with exactly the single word READY and nothing else. Do not use any tools.'

function fail(msg) {
  console.error(`\n[packaged-agent-smoke] FAIL: ${msg}\n`)
  process.exitCode = 1
}

if (!existsSync(EXE)) {
  fail(`packaged exe not found at ${EXE}\n  Build first: pnpm build:win (or electron-builder --dir)`)
  process.exit(1)
}
if (!existsSync(path.join(CREDS_DIR, '.credentials.json'))) {
  fail(
    `no Claude creds at ${CREDS_DIR}/.credentials.json\n  Sign in to Claude in the Omi app first, or set OMI_SMOKE_CREDS_DIR.`
  )
  process.exit(1)
}

const chromium = require('playwright').chromium
const profileDir = mkdtempSync(path.join(tmpdir(), 'omi-pkg-agent-smoke-'))
const logFile = path.join(profileDir, 'app.log')
let child = null

function cleanup() {
  try {
    if (child && child.pid) {
      execFileSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { windowsHide: true, stdio: 'ignore' })
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
  // Seed the isolated profile: Claude agent creds go where the app reads them —
  // <userData>/claude-agent (app pins CLAUDE_CONFIG_DIR there at startup).
  mkdirSync(profileDir, { recursive: true })
  cpSync(CREDS_DIR, path.join(profileDir, 'claude-agent'), { recursive: true })

  const logStream = require('node:fs').createWriteStream(logFile)
  console.log(`[packaged-agent-smoke] booting ${EXE}`)
  console.log(`[packaged-agent-smoke] isolated profile: ${profileDir}`)
  child = spawn(
    EXE,
    [`--user-data-dir=${profileDir}`, `--remote-debugging-port=${CDP_PORT}`],
    { env: { ...process.env, OMI_AUTOMATION: '0' }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true }
  )
  child.stdout.pipe(logStream)
  child.stderr.pipe(logStream)

  // Wait for the CDP endpoint to come up.
  const browser = await connectWithRetry(`http://127.0.0.1:${CDP_PORT}`, 30_000)

  // Find the main app window (index.html), retrying while it loads.
  const page = await findMainPage(browser, 20_000)
  if (!page) throw new Error('main app window (index.html) never appeared')

  // Confirm the Claude adapter reports connected (creds seeded correctly).
  const auth = await page.evaluate(async () => {
    try {
      return await window.omi.codingAgentAuthStatus()
    } catch (e) {
      return { error: String(e) }
    }
  })
  console.log(`[packaged-agent-smoke] claude auth:`, JSON.stringify(auth))
  if (!auth || !auth.connected) {
    throw new Error(`Claude adapter not connected in packaged app: ${JSON.stringify(auth)}`)
  }

  // Drive the real spawn path.
  console.log(`[packaged-agent-smoke] spawning agent…`)
  const result = await page.evaluate(async (prompt) => {
    const taskId = 'pkg-smoke-' + Date.now()
    try {
      const r = await window.omi.codingAgentRun({ taskId, prompt, agentId: 'acp' })
      return { ok: r.ok, error: r.error, adapterId: r.adapterId, text: (r.text || '').slice(0, 200) }
    } catch (e) {
      return { threw: String(e) }
    }
  }, PROMPT)
  console.log(`[packaged-agent-smoke] run result:`, JSON.stringify(result))

  await browser.close().catch(() => {})

  if (!result || !result.ok) {
    // Surface the app's ACP spawn log — the real cause lives there.
    let log = ''
    try {
      log = readFileSync(logFile, 'utf8')
    } catch {
      /* ignore */
    }
    const acpLines = log
      .split('\n')
      .filter((l) => /acp|claude|subprocess|Internal|failed to launch/i.test(l))
      .slice(-15)
      .join('\n')
    throw new Error(
      `agent run did not succeed: ${JSON.stringify(result)}\n--- app ACP log tail ---\n${acpLines}`
    )
  }
  if (!result.text || !result.text.trim()) {
    throw new Error(`agent run reported ok but produced no text output: ${JSON.stringify(result)}`)
  }

  console.log(`\n[packaged-agent-smoke] PASS — agent replied: ${JSON.stringify(result.text)}\n`)
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
        if (p.url().includes('index.html')) return p
      }
    }
    await sleep(500)
  }
  return null
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Ctrl-C / kill must still tear down: the throwaway profile holds a COPY of
// real Claude credentials, and an orphaned app process would keep running.
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
