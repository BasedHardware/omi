/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Onboarding microphone-permission E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron and exercises the mic step of
// the onboarding wizard (Onboarding.tsx step 7 → MicPermissionStep →
// PermissionStep).
//
// REGRESSION GUARD. Two bugs:
//   * A denied microphone rendered "Granted" and auto-advanced.
//   * Worse, the step FALSE-GRANTED on every run: it read
//     `navigator.permissions.query({name:'microphone'})`, which Electron answers
//     'granted' unconditionally, so it self-granted and self-skipped on mount without
//     ever calling getUserMedia. This spec used to STUB that very API — which is why it
//     stayed green through the bug. It no longer stubs it.
//
// The three cases:
//   1. denied  → "Blocked by Windows" + recovery button, never "Granted", still on the
//                mic step, persisted `onboardingStep` still 7.
//   2. granted → the CLICK grants; "Granted", then onboarding advances to step 8.
//   3. real    → nothing stubbed at all. Chromium still claims 'granted'; the step must
//                NOT advance without a click. This is the case whose absence hid the bug.
//
// Hermetic, and deliberately NOT via OMI_E2E_FAKE_AUTH: that flag hard-codes
// `onboarded = true` in App.tsx, which redirects /onboarding → /home, so the
// wizard is unreachable under it. Instead we seed a persisted Firebase session
// into the renderer's localStorage (the app uses `browserLocalPersistence`) and
// abort every non-localhost request. Firebase's startup `reloadAndSetCurrentUser`
// then fails with `auth/network-request-failed`, which it treats as "offline —
// keep the stored user", so the shell boots signed-in with ZERO network. The OS mic
// answer is driven by the OMI_E2E_MIC_STATE seam (main's registry read), and only
// `getUserMedia` is stubbed, so a click never opens a real Windows prompt. Each launch
// gets its own throwaway --user-data-dir; screenshots land in .playwright-mcp/.
//
// Run after a build: node --test e2e/onboarding-permission.spec.mjs
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp')

// Same public Firebase web config the renderer is built with (desktop/windows/.env
// → VITE_FIREBASE_API_KEY). The persisted-session localStorage key is
// `firebase:authUser:<apiKey>:<appName>`, so the key must match the built bundle.
const FIREBASE_API_KEY = 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8'

const PREFS_KEY = 'omi-windows-prefs-v1'
// Onboarding.tsx: step 7 is MicPermissionStep, step 8 is AutomationPermissionStep.
const MIC_STEP = 7
const NEXT_STEP = 8

// NOT OMI_E2E_FAKE_AUTH — see the header. OMI_E2E keeps the app's other E2E seams
// (no tray nagging, deterministic windows) without forcing onboarding complete.
const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

// `micState` drives the REAL permission seam the step reads (main's registry lookup,
// overridable only under OMI_E2E). Passing it here — rather than stubbing a browser API —
// is the whole lesson of this spec: see the unstubbed test at the bottom.
async function launch(micState) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-onboarding-e2e-'))
  const env = micState ? { ...baseEnv, OMI_E2E_MIC_STATE: micState } : baseEnv
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env })
  const cleanup = async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
  return { app, cleanup }
}

async function mainPage(app) {
  await app.firstWindow()
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((w) => !isSecondary(w.url()))
    if (page) {
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('main-window shell never mounted')
}

// Hermetic: the renderer itself is served from http://localhost:<port> (electron-vite
// preview server), so only NON-localhost traffic is aborted. Aborting (rather than
// fulfilling) is load-bearing: Firebase reads a transport failure as
// `auth/network-request-failed` and keeps the persisted user instead of clearing it.
async function blockExternalNetwork(page) {
  await page.route('**/*', (route) => {
    const url = route.request().url()
    if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)) return route.continue()
    if (/^https?:\/\//.test(url)) return route.abort()
    return route.continue()
  })
}

/**
 * Runs BEFORE any app script on the next load. Seeds (a) an offline Firebase
 * session so App's auth gate passes, (b) onboarding parked on the mic step
 * (`onboardingCompletedAt` absent ⇒ the wizard runs; `onboardingStep` ⇒ it resumes
 * there), and (c) `getUserMedia`, so clicking Grant never opens a real OS prompt or
 * touches a real device.
 *
 * `navigator.permissions.query` is deliberately NOT stubbed any more. The step no longer
 * reads it — it reads the real Windows consent registry via main — and stubbing it was
 * exactly what let this spec stay green through a total false-grant. The OS answer is
 * driven by `launch(micState)` instead (the OMI_E2E_MIC_STATE seam).
 *
 * `grant: true`  → getUserMedia resolves, so the CLICK drives the grant, like the real flow.
 * `grant: false` → getUserMedia rejects NotAllowedError (a Windows-blocked mic).
 * `stubMic: false` → nothing is stubbed at all: real getUserMedia, real
 *                  `navigator.permissions`, real registry. See the last test.
 */
function seedScript(args) {
  {
    const { apiKey, step, grant, prefsKey, stubMic } = args

    // (a) Offline Firebase session (browserLocalPersistence → localStorage).
    // A far-future expirationTime stops the SDK from trying a token refresh.
    const now = Date.now()
    localStorage.setItem(
      `firebase:authUser:${apiKey}:[DEFAULT]`,
      JSON.stringify({
        uid: 'e2e-onboarding-user',
        email: 'e2e@local',
        emailVerified: true,
        displayName: 'E2E User',
        isAnonymous: false,
        photoURL: null,
        providerData: [],
        stsTokenManager: {
          refreshToken: 'e2e-refresh',
          accessToken: 'e2e-access',
          expirationTime: now + 365 * 24 * 3600 * 1000
        },
        createdAt: String(now),
        lastLoginAt: String(now),
        apiKey,
        appName: '[DEFAULT]'
      })
    )

    // (b) Onboarding parked on the mic step: no onboardingCompletedAt.
    localStorage.setItem(
      prefsKey,
      JSON.stringify({ onboardingStep: step, displayName: 'E2E User' })
    )

    // (c) getUserMedia only — the click path, so no OS prompt and no real device.
    // Skipped entirely when stubMic is false: that case runs the REAL browser APIs.
    if (!stubMic) return
    const fakeStream = {
      getTracks: () => [
        {
          stop() {
            /* nothing to release — no real device was ever opened */
          }
        }
      ]
    }

    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      configurable: true,
      value: () =>
        grant
          ? Promise.resolve(fakeStream)
          : Promise.reject(new DOMException('Permission denied', 'NotAllowedError'))
    })
  }
}

// Lands the app on the onboarding mic step with the mic APIs stubbed. The first
// load boots signed-out (/login) — we install the route + init script, then reload
// so everything above runs before the app's scripts on the next document.
async function openMicStep(app, { grant, stubMic = true }) {
  const page = await mainPage(app)
  await blockExternalNetwork(page)
  await page.addInitScript(seedScript, {
    apiKey: FIREBASE_API_KEY,
    step: MIC_STEP,
    grant,
    stubMic,
    prefsKey: PREFS_KEY
  })
  await page.reload()
  await mainPage(app)
  // The mic step's real title (MicPermissionStep.tsx).
  await page
    .getByText('Let Omi use your mic', { exact: true })
    .waitFor({ state: 'visible', timeout: 20000 })
  return page
}

const persistedStep = (page) =>
  page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? '{}').onboardingStep, PREFS_KEY)

describe('Onboarding — microphone permission', () => {
  test('DENIED does not claim Granted and does not advance', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    // Windows is actively blocking the mic.
    const { app, cleanup } = await launch('denied')
    t.after(cleanup)

    const page = await openMicStep(app, { grant: false })
    assert.equal(await persistedStep(page), MIC_STEP, 'parked on the mic step')

    // Pre-click: the idle copy, and no grant claimed.
    await page
      .getByText('Not granted yet', { exact: true })
      .waitFor({ state: 'visible', timeout: 8000 })

    // Ask for the mic — the stub rejects with NotAllowedError.
    await page.getByRole('button', { name: 'Grant access', exact: true }).click()

    // Denied state: the status card flips to "Blocked by Windows", the button
    // offers a retry, and the real denial copy (MicPermissionStep's NotAllowedError
    // message, surfaced by PermissionStep as `error`) explains the recovery.
    await page
      .getByText('Blocked by Windows', { exact: true })
      .waitFor({ state: 'visible', timeout: 8000 })
    await page
      .getByRole('button', { name: 'Try again', exact: true })
      .waitFor({ state: 'visible', timeout: 8000 })
    await page
      .getByText(/Windows blocked microphone access\./)
      .waitFor({ state: 'visible', timeout: 8000 })

    // The recovery affordance: opens Windows' mic privacy settings.
    await page
      .getByRole('button', { name: 'Open Windows Settings', exact: true })
      .waitFor({ state: 'visible', timeout: 8000 })

    // THE REGRESSION: nothing may ever say "Granted"…
    assert.equal(
      await page.getByText('Granted', { exact: true }).count(),
      0,
      'denied mic must never render the granted status/button label'
    )

    // …and onboarding must not advance. Wait past the 350ms auto-advance AND a
    // full 1s poll tick (the poll keeps running while denied — it must read the
    // stubbed 'denied' state and never rescue the step into granted).
    await new Promise((r) => setTimeout(r, 1800))
    await page
      .getByText('Let Omi use your mic', { exact: true })
      .waitFor({ state: 'visible', timeout: 2000 })
    assert.equal(
      await page.getByText('Let Omi act when asked', { exact: true }).count(),
      0,
      'the next step (Automation) must not have been reached'
    )
    assert.equal(
      await persistedStep(page),
      MIC_STEP,
      'persisted onboardingStep is still the mic step'
    )

    await page.screenshot({ path: path.join(shotsDir, 'onboarding-mic-denied.png') })
  })

  test('GRANTED reports granted and advances', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    // Never asked yet, so the step starts idle and the CLICK is what grants.
    const { app, cleanup } = await launch('unknown')
    t.after(cleanup)

    const page = await openMicStep(app, { grant: true })
    assert.equal(await persistedStep(page), MIC_STEP, 'parked on the mic step')
    await page
      .getByText('Not granted yet', { exact: true })
      .waitFor({ state: 'visible', timeout: 8000 })

    // Grant → the stub resolves a stream; PermissionStep marks granted, then
    // auto-advances 350ms later.
    await page.getByRole('button', { name: 'Grant access', exact: true }).click()

    // The granted status renders (status card + button both read "Granted").
    await page
      .getByText('Granted', { exact: true })
      .first()
      .waitFor({ state: 'visible', timeout: 4000 })
    await page.screenshot({ path: path.join(shotsDir, 'onboarding-mic-granted.png') })

    // …and onboarding advances off the mic step onto Automation (step 8).
    await page
      .getByText('Let Omi act when asked', { exact: true })
      .waitFor({ state: 'visible', timeout: 4000 })
    assert.equal(
      await page.getByText('Let Omi use your mic', { exact: true }).count(),
      0,
      'the mic step is gone after the auto-advance'
    )
    await assertEventually(
      async () => (await persistedStep(page)) === NEXT_STEP,
      `persisted onboardingStep advanced to ${NEXT_STEP}`
    )
  })

  // THE GUARD THAT WAS MISSING. The ORIGINAL, vacuous version of this spec stubbed
  // `getUserMedia` AND `navigator.permissions.query` — the exact two APIs whose real
  // implementations were broken — which is precisely why it stayed green through the
  // bug. (The two tests above no longer do that: they stub only `getUserMedia` for the
  // click path and drive the OS answer through the real `OMI_E2E_MIC_STATE` seam, not
  // by faking a browser API.) This test stubs NOTHING, so nothing can mask the defect.
  //
  // The bug: Electron registers no `setPermissionCheckHandler`, so Chromium's default
  // `GetPermissionStatus` answers `granted` unconditionally — on a brand-new profile,
  // with the Windows microphone privacy toggle actively blocking the app. The step read
  // that as truth on mount, marked itself granted, wrote `continuousRecording: true`, and
  // auto-advanced. getUserMedia was never called and the OS was never asked.
  //
  // So this case stubs NOTHING. It runs the real APIs on a throwaway profile and asserts
  // the only thing that is true on every machine regardless of the user's actual mic
  // setting: the step MUST NOT advance on its own. Onboarding may only move when the user
  // clicks. Against the pre-fix code this fails — the step advances to step 8 within
  // ~350ms without a single click.
  test('does NOT auto-advance without a click, against the REAL permissions API', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)

    const page = await openMicStep(app, { grant: false, stubMic: false })
    assert.equal(await persistedStep(page), MIC_STEP, 'parked on the mic step')

    // Chromium says 'granted' here no matter what Windows thinks. Pinned so this test
    // keeps its teeth: if Electron ever starts answering honestly, the assertion below
    // is still correct, but this line tells the next reader why the guard exists.
    const chromiumSays = await page.evaluate(async () => {
      try {
        return (await navigator.permissions.query({ name: 'microphone' })).state
      } catch {
        return 'unsupported'
      }
    })
    console.log(`[e2e] real navigator.permissions.query(microphone) => ${chromiumSays}`)

    // Well past the 350ms auto-advance and several 1s poll ticks. No click has happened.
    await new Promise((r) => setTimeout(r, 3000))

    // The regression signal is the PERSISTED step, not the on-screen title. The
    // pre-fix false-grant fires on mount and persists step 8 within ~350ms — so a
    // regression is caught here regardless of what is rendered 3s later. Asserting the
    // title is deliberately avoided: the offline-auth harness intermittently drops the
    // renderer to /login seconds in (a harness fault, unrelated to onboarding), which
    // does NOT advance onboardingStep — so the step check stays honest while the title
    // check would flake.
    assert.equal(
      await page.getByText('Let Omi act when asked', { exact: true }).count(),
      0,
      'the mic step must not hand off to the Automation step on its own'
    )
    assert.equal(
      await persistedStep(page),
      MIC_STEP,
      'persisted onboardingStep must still be the mic step — nothing was clicked'
    )

    await page.screenshot({ path: path.join(shotsDir, 'onboarding-mic-real-permissions.png') })
  })
})

async function assertEventually(pred, message, timeout = 4000) {
  const deadline = Date.now() + timeout
  for (;;) {
    if (await pred()) return
    if (Date.now() > deadline) assert.fail(message)
    await new Promise((r) => setTimeout(r, 100))
  }
}
