// No-audio smoke for the Phase 6 voice surface: launches the BUILT app with a
// fresh (signed-out) profile and drives the real voice controller through the
// OMI_E2E hook. Asserts the session machine's error path is graceful:
//   start → 'connecting' (observed) → 'error' (mint rejected: signed-out 401,
//   or unreachable token endpoint) — with a human-readable message, the app
//   still alive, and stop() returning the machine to 'idle'.
//
// Deliberately emits NO audio and changes NO audio devices (safe to run during
// the idle soak): the mint fails before any provider session or player exists.
// The speakers/echo-loop verification is the separate post-soak deliverable
// (run-voice-loop-check.mjs).
//
// Exit codes: 0 pass · 1 assertion failed · 2 skipped (build missing).
import { execFileSync } from 'node:child_process'
import { _electron as electron } from 'playwright'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

function log(m) {
  console.log(`[voice-smoke] ${m}`)
}

async function findMainWindow(app) {
  for (let i = 0; i < 40; i++) {
    const page = app
      .windows()
      .find((w) => !/#\/(capture|overlay|insight-toast)/.test(w.url()) && w.url() !== 'about:blank')
    if (page) return page
    await new Promise((r) => setTimeout(r, 500))
  }
  return null
}

async function voiceEval(page, fnBody) {
  return page.evaluate(fnBody)
}

async function main() {
  if (!NO_BUILD) {
    log('building app…')
    execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
  }
  const mainEntry = path.join(root, 'out', 'main', 'index.js')
  if (!fs.existsSync(mainEntry)) {
    log(`built main not found (${mainEntry}) — run without --no-build`)
    process.exit(2)
  }

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-voicesmoke-ud-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0' }
  })

  let exitCode = 0
  const fail = (msg) => {
    log(`FAIL: ${msg}`)
    exitCode = 1
  }

  try {
    const page = await findMainWindow(app)
    if (!page) {
      fail('main window never appeared')
      return
    }
    await page.waitForLoadState('domcontentloaded')

    // Wait for the hook (attached at the App root once React mounts).
    let hooked = false
    for (let i = 0; i < 30 && !hooked; i++) {
      hooked = await voiceEval(page, () => typeof globalThis.__omiVoice?.start === 'function')
      if (!hooked) await new Promise((r) => setTimeout(r, 500))
    }
    if (!hooked) {
      fail('window.__omiVoice hook never attached (OMI_E2E path broken)')
      return
    }
    log('hook attached; starting a voice session signed-out…')

    // Kick off a session and trace the machine states as they change.
    await voiceEval(page, () => {
      globalThis.__omiVoiceTrace = [globalThis.__omiVoice.getState().status]
      const push = () => {
        const s = globalThis.__omiVoice.getState().status
        const t = globalThis.__omiVoiceTrace
        if (t[t.length - 1] !== s) t.push(s)
      }
      globalThis.__omiVoiceTraceTimer = setInterval(push, 25)
      void globalThis.__omiVoice.start('openai')
      push()
    })

    // Wait (up to 30s) for the machine to settle in 'error'.
    let finalState = null
    for (let i = 0; i < 60; i++) {
      finalState = await voiceEval(page, () => globalThis.__omiVoice.getState())
      if (finalState.status === 'error') break
      await new Promise((r) => setTimeout(r, 500))
    }
    const trace = await voiceEval(page, () => {
      clearInterval(globalThis.__omiVoiceTraceTimer)
      return globalThis.__omiVoiceTrace
    })
    log(`state trace: ${trace.join(' → ')}`)

    if (!trace.includes('connecting')) fail(`machine never reached 'connecting' (${trace})`)
    if (finalState?.status !== 'error') {
      fail(`machine did not settle in 'error' (got ${JSON.stringify(finalState)})`)
    } else {
      log(`error surfaced cleanly: "${finalState.message}" (retryable=${finalState.retryable})`)
      if (typeof finalState.message !== 'string' || finalState.message.length === 0) {
        fail('error state carries no message')
      }
    }

    // The app must still be alive and responsive (no crash / white screen).
    const alive = await voiceEval(page, () => document.body != null)
    if (!alive) fail('renderer unresponsive after the error path')

    // stop() from error must land back in idle (the dismiss path).
    const after = await voiceEval(page, () => {
      globalThis.__omiVoice.stop()
      return globalThis.__omiVoice.getState().status
    })
    if (after !== 'idle') fail(`stop() from error should land in idle, got '${after}'`)

    if (exitCode === 0) log('PASS: connecting observed, clean error, no crash, idle after stop')
  } finally {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    fs.rmSync(userDataDir, { recursive: true, force: true })
  }
  process.exit(exitCode)
}

main().catch((e) => {
  console.error(`[voice-smoke] error: ${e?.stack || e}`)
  process.exit(1)
})
