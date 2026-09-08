/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Onboarding "Data Sources" step E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron on a FRESH, signed-in-but-NOT-
// onboarded throwaway profile, and asserts the deterministic UI/interaction flow
// of the curated data-sources step.
//
// Why NOT OMI_E2E_FAKE_AUTH: that flag hard-codes `onboarded = true` in
// App.tsx:195 (`!!window.omi?.e2eFakeAuth`), which redirects /onboarding → /home,
// so the wizard is unreachable. Instead — exactly like onboarding-layout.spec.mjs
// and onboarding-permission.spec.mjs — we seed an offline Firebase session into
// localStorage (the app uses browserLocalPersistence), OMIT `onboardingCompletedAt`
// so `isOnboardingComplete()` stays false and the app lands on /onboarding, and
// block external network so Firebase keeps the seeded user. Throwaway
// --user-data-dir per launch = a genuine out-of-box first-run profile.
//
// The network is blocked, so this asserts UI + interaction ONLY — never a real
// import round-trip. The Data Sources step is index 12 of 15 (Onboarding.tsx).
//
// Run after a build: node --test e2e/datasources.spec.mjs
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
// `firebase:authUser:<apiKey>:<appName>`, so it must match the built bundle.
const FIREBASE_API_KEY = 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8'

const PREFS_KEY = 'omi-windows-prefs-v1'
// Data Sources is step index 12 of TOTAL_STEPS=15 (Onboarding.tsx renderStep).
const DATA_SOURCES_STEP = 12

// The five curated rows, in the exact order DataSourcesStep renders them. The DOM
// testid uses the connector BRAND, not the display title (Email→gmail, Local
// files→omi), so both are asserted.
const EXPECTED_ROWS = [
  { testid: 'datasource-calendar', title: 'Calendar' },
  { testid: 'datasource-gmail', title: 'Email' },
  { testid: 'datasource-omi', title: 'Local files' },
  { testid: 'datasource-chatgpt', title: 'ChatGPT' },
  { testid: 'datasource-claude', title: 'Claude' }
]

const CHATGPT_ROW = '[data-testid="datasource-chatgpt"]'

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

// NOT OMI_E2E_FAKE_AUTH — see the header. OMI_E2E keeps the app's other E2E seams
// (no tray nagging, deterministic windows) without forcing onboarding complete.
const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

// Hermetic: the renderer is served from file://, so abort all http(s) traffic.
// Aborting (rather than fulfilling) is load-bearing: Firebase reads a transport
// failure as `auth/network-request-failed` and KEEPS the persisted user instead
// of clearing it.
async function blockExternalNetwork(page) {
  await page.route('**/*', (route) => {
    const url = route.request().url()
    if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)) return route.continue()
    if (/^https?:\/\//.test(url)) return route.abort()
    return route.continue()
  })
}

// Offline Firebase session (browserLocalPersistence → localStorage), seeded before
// any app script runs so App's auth gate passes. `onboardingCompletedAt` is
// deliberately absent, so the wizard runs.
function seedAuthScript(apiKey) {
  const now = Date.now()
  localStorage.setItem(
    `firebase:authUser:${apiKey}:[DEFAULT]`,
    JSON.stringify({
      uid: 'e2e-datasources-user',
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
}

// Software-GL switches so the persistent onboarding Brain Map renders on any box
// (incl. a CI runner with no usable GPU) without crashing the GPU process. Same
// switches the app's dev-only workaround applies; the production bundle launched
// here does NOT run them, so production keeps hardware acceleration. This spec's
// assertions are all DOM state, never pixels, so it does not affect the verdict —
// it only keeps the step-12 map (Data Sources shows the map) from destabilizing.
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-shader-disk-cache'
]

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-datasources-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`, ...SWIFTSHADER_ARGS],
    env: baseEnv
  })
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
  for (let i = 0; i < 120; i++) {
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

// Onboarding resumes from the persisted `onboardingStep` pref, so seeding it and
// reloading lands directly on the Data Sources step. We wait on a DataSources-
// specific node (the ChatGPT row), not just the content pane — the pane exists on
// every step, so waiting on it alone could resolve on the wrong step after reload.
async function gotoDataSources(page) {
  await page.evaluate(
    ({ step, PREFS_KEY }) => {
      const prev = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
      delete prev.onboardingCompletedAt
      localStorage.setItem(PREFS_KEY, JSON.stringify({ ...prev, onboardingStep: step }))
    },
    { step: DATA_SOURCES_STEP, PREFS_KEY }
  )
  await page.reload()
  // Generous: under swiftshader + a loaded machine, the step-12 render (which also
  // mounts the persistent Brain Map) can take a while to first paint.
  await page.waitForSelector(CHATGPT_ROW, { timeout: 30000 })
  // Let the row's async status effects (Calendar/Email/memories — all network-
  // blocked, so they resolve to their default text) settle.
  await new Promise((r) => setTimeout(r, 400))
}

// Fresh profile → seed auth → block network → land on Data Sources. Every test
// gets its own throwaway --user-data-dir, so there is no cross-test state bleed and
// each is a genuine first-run.
async function bootToDataSources(t) {
  const { app, cleanup } = await launch()
  t.after(cleanup)
  const page = await mainPage(app)
  await blockExternalNetwork(page)
  await page.addInitScript(seedAuthScript, FIREBASE_API_KEY)
  await page.reload()
  await page.waitForSelector('[data-testid="onboarding-content-pane"]', { timeout: 30000 })
  await gotoDataSources(page)
  return { app, page }
}

describe('Onboarding — Data Sources step (fresh first-run profile)', () => {
  test('renders all five curated rows in order, with Skip + Continue present', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { page } = await bootToDataSources(t)

    // Step identity: the eyebrow + title the DataSourcesStep scaffold renders.
    assert.equal(
      await page.getByText('Your 2nd brain is live.').count(),
      1,
      'on the Data Sources step'
    )

    // Rows exist in the exact DOM order, keyed by connector brand testid, each
    // showing its display title. Poll until all five are attached (the rows mount
    // together with the step, but the async status effects — Calendar/Email/memories,
    // all network-blocked — can trigger a re-render right after the reload; a
    // one-shot querySelectorAll can catch that transient. waitForFunction rides it
    // out and returns the stable snapshot).
    const rows = await page
      .waitForFunction(
        () => {
          const els = [...document.querySelectorAll('[data-testid^="datasource-"]')]
          if (els.length !== 5) return null
          return els.map((e) => ({
            testid: e.getAttribute('data-testid'),
            title: e.querySelector('.font-semibold')?.textContent?.trim()
          }))
        },
        null,
        { timeout: 10000 }
      )
      .then((h) => h.jsonValue())

    assert.deepEqual(
      rows.map((r) => r.testid),
      EXPECTED_ROWS.map((r) => r.testid),
      'five rows in curated order'
    )
    assert.deepEqual(
      rows.map((r) => r.title),
      EXPECTED_ROWS.map((r) => r.title),
      'row titles match'
    )

    // Skip lives in the header; Continue is the primary CTA. Both must be present
    // (both advance — asserted in the dedicated tests below).
    assert.equal(await page.getByRole('button', { name: 'Skip' }).count(), 1, 'Skip present')
    assert.equal(
      await page.getByRole('button', { name: 'Continue' }).count(),
      1,
      'Continue present'
    )

    await page.screenshot({ path: path.join(shotsDir, 'datasources-e2e-default.png') })
  })

  test('ChatGPT row expands and the white Import button is progressively revealed by typed text', async (t) => {
    const { page } = await bootToDataSources(t)
    const row = page.locator(CHATGPT_ROW)

    // Collapsed: no textarea, no Import button.
    assert.equal(await row.locator('textarea').count(), 0, 'collapsed: no textarea')
    assert.equal(
      await row.getByRole('button', { name: /Import ChatGPT/ }).count(),
      0,
      'collapsed: no Import button'
    )

    // Expand the row (the collapsed affordance is a "Connect" pill scoped to THIS
    // row — Calendar/Email also show "Connect", hence the row-scoped locator).
    await row.getByRole('button', { name: 'Connect' }).click()

    // Reveals: the secondary "Open ChatGPT & Copy Prompt" CTA + the paste textarea.
    await row
      .getByRole('button', { name: /Open ChatGPT.*Copy Prompt/ })
      .waitFor({ state: 'visible', timeout: 5000 })
    assert.equal(await row.locator('textarea').count(), 1, 'expanded: textarea present')

    // Progressive reveal — the exact hierarchy fix the UI review validated: the
    // white/primary Import commit does NOT exist while the textarea is empty.
    assert.equal(
      await row.getByRole('button', { name: /Import ChatGPT/ }).count(),
      0,
      'empty textarea: Import button absent'
    )

    // Type a memory export → the Import button appears.
    await row
      .locator('textarea')
      .fill('Here is everything I know about you: you live in New York and love climbing.')
    const importBtn = row.getByRole('button', { name: /Import ChatGPT/ })
    await importBtn.waitFor({ state: 'visible', timeout: 5000 })

    // ...and it is the white/primary treatment (bg-white text-black), matching
    // Connect/Continue — the single-button-system fix.
    const cls = (await importBtn.getAttribute('class')) ?? ''
    assert.ok(
      cls.includes('bg-white') && cls.includes('text-black'),
      `Import is white/primary (class="${cls}")`
    )

    await page.screenshot({ path: path.join(shotsDir, 'datasources-e2e-chatgpt-expanded.png') })

    // Clearing the textarea reactively HIDES Import again — proves the reveal is
    // bound to text presence, not a one-way latch.
    await row.locator('textarea').fill('')
    await importBtn.waitFor({ state: 'detached', timeout: 5000 })
    assert.equal(
      await row.getByRole('button', { name: /Import ChatGPT/ }).count(),
      0,
      'cleared textarea: Import button hidden again'
    )
  })

  test('clicking Import with the network blocked degrades gracefully (no white-screen)', async (t) => {
    const { page } = await bootToDataSources(t)
    const row = page.locator(CHATGPT_ROW)

    await row.getByRole('button', { name: 'Connect' }).click()
    await row.locator('textarea').waitFor({ state: 'visible', timeout: 5000 })
    await row.locator('textarea').fill('Some pasted memory text that cannot actually import offline.')
    await row.getByRole('button', { name: /Import ChatGPT/ }).click()

    // The import path hits the (blocked) backend; the handler must catch and toast,
    // never crash the renderer. Give it a beat, then assert the app is still alive
    // and still on the Data Sources step.
    await new Promise((r) => setTimeout(r, 1500))
    const alive = await page.evaluate(
      () => (document.querySelector('#root')?.childElementCount ?? 0) > 0
    )
    assert.ok(alive, 'renderer did not white-screen')
    assert.equal(await page.locator(CHATGPT_ROW).count(), 1, 'still on the Data Sources step')
  })

  test('Continue advances past the Data Sources step', async (t) => {
    const { page } = await bootToDataSources(t)
    await page.getByRole('button', { name: 'Continue' }).click()
    // Advancing unmounts the Data Sources rows; we are still inside onboarding.
    await page.locator(CHATGPT_ROW).waitFor({ state: 'detached', timeout: 5000 })
    assert.equal(
      await page.locator('[data-testid="onboarding-content-pane"]').count(),
      1,
      'still in the onboarding wizard, just a later step'
    )
  })

  test('Skip advances past the Data Sources step', async (t) => {
    const { page } = await bootToDataSources(t)
    await page.getByRole('button', { name: 'Skip' }).click()
    await page.locator(CHATGPT_ROW).waitFor({ state: 'detached', timeout: 5000 })
    assert.equal(
      await page.locator('[data-testid="onboarding-content-pane"]').count(),
      1,
      'still in the onboarding wizard, just a later step'
    )
  })
})
