// Live end-to-end verification of Google sign-in in the REAL built app.
// Launches out/main/index.js via Playwright _electron with a THROWAWAY
// --user-data-dir (fresh renderer origin → starts signed OUT), clicks the
// "Sign in with Google" button, prints the authorize URL the app opened in the
// system browser, then waits (≤5 min) for the loopback callback + Firebase
// custom-token sign-in and asserts the renderer really has a signed-in user.
//
// The Google account click-through in the system browser is the HUMAN /
// orchestrator step — this script is self-checking around it:
//   exit 0  sign-in completed end to end (prints uid/email)
//   exit 2  the flow reached "waiting for the browser" but nobody finished the
//           Google consent (or it was cancelled) — needs the human step
//   exit 1  harness/app failure before the browser step
//
// Usage: node scripts/verify-oauth-flow.mjs [--no-build]
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { _electron as electron } from 'playwright'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const WAIT_MS = 5 * 60_000 + 30_000 // app flow times out at 5 min; small margin

if (!process.argv.includes('--no-build')) {
  console.log('[verify-oauth] building (electron-vite build)…')
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-oauth-verify-'))
let app
let exitCode = 1
try {
  app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: { ...process.env, OMI_AUTOMATION: '0' }
  })

  // Relay main-process output; the sign-in flow logs a stable
  // "[google-signin] … authorize-url <url>" marker we surface prominently.
  const surfaced = { authorizeUrl: null }
  const onChunk = (chunk) => {
    const text = String(chunk)
    for (const line of text.split(/\r?\n/)) {
      if (!line.includes('[google-signin]')) continue
      console.log(line)
      const m = line.match(/authorize-url (\S+)/)
      if (m) {
        surfaced.authorizeUrl = m[1]
        console.log('\n[verify-oauth] >>> authorize URL opened in the system browser:')
        console.log(`[verify-oauth] >>> ${m[1]}\n`)
      }
    }
  }
  app.process().stdout?.on('data', onChunk)
  app.process().stderr?.on('data', onChunk)

  const page = await app.firstWindow()
  const signInButton = page.getByRole('button', { name: /sign in with google/i })
  await signInButton.waitFor({ state: 'visible', timeout: 60_000 })
  console.log('[verify-oauth] app is up and signed out — clicking "Sign in with Google"')
  await signInButton.click()

  console.log(
    '[verify-oauth] waiting for the browser round-trip (finish the Google consent in the opened browser; up to 5 min)…'
  )

  // Success signal: Firebase browserLocalPersistence writes the signed-in user
  // to localStorage under firebase:authUser:<apiKey>:[DEFAULT].
  const deadline = Date.now() + WAIT_MS
  let user = null
  let uiError = null
  while (Date.now() < deadline && !user && !uiError) {
    user = await page.evaluate(() => {
      const key = Object.keys(localStorage).find((k) => k.startsWith('firebase:authUser:'))
      if (!key) return null
      try {
        const u = JSON.parse(localStorage.getItem(key))
        return { uid: u?.uid ?? null, email: u?.email ?? null }
      } catch {
        return null
      }
    })
    if (!user) {
      // The Login page surfaces flow failures (timeout/cancel/state mismatch)
      // as a visible error paragraph — treat that as the "needs human" signal.
      uiError = await page
        .locator('p.text-red-400\\/90')
        .textContent({ timeout: 250 })
        .catch(() => null)
      if (!user && !uiError) await new Promise((r) => setTimeout(r, 2000))
    }
  }

  if (user?.uid) {
    console.log(`[verify-oauth] SUCCESS — signed in as uid=${user.uid} email=${user.email ?? '(none)'}`)
    exitCode = 0
  } else {
    console.error(
      `[verify-oauth] NOT SIGNED IN — ${
        uiError
          ? `the app reported: "${uiError.trim()}"`
          : 'no Firebase user appeared within the wait window'
      }.`
    )
    console.error(
      '[verify-oauth] This step needs a human/orchestrator: run again and complete the Google '
    )
    console.error(
      '[verify-oauth] consent in the system browser (the authorize URL is printed above).'
    )
    exitCode = 2
  }
} catch (e) {
  console.error('[verify-oauth] harness failure:', e)
  exitCode = 1
} finally {
  try {
    await app?.close()
  } catch {
    /* already closed */
  }
  try {
    rmSync(userDataDir, { recursive: true, force: true })
  } catch {
    /* best-effort */
  }
}
process.exitCode = exitCode
