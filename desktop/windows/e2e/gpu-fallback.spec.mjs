/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// GPU-resilience E2E: drives the REAL built app (out/main/index.js) via Playwright's
// _electron, twice — once with WebGL forcibly unavailable, once on software GL —
// and proves the brain map degrades to a deliberate static mark instead of leaving
// a black void, without regressing the healthy render.
//
// The bug this guards (from the product owner's crash.log): on hybrid-GPU Windows
// laptops Chromium's GPU process crash-LOOPS (`child-process-gone type=GPU`, five in
// 30s). The renderer's remount-based recovery is capped at 4, so a loop exhausts it
// and — once Chromium refuses new 3D contexts — three.js's WebGLRenderer throws and
// the pane stays permanently black. Onboarding is where that hurts most: the map is
// half of a new user's first screen.
//
// Auth/onboarding seeding, network blocking and the step-driving helpers are lifted
// from onboarding-layout.spec.mjs (same hermetic recipe: offline Firebase session in
// localStorage, throwaway --user-data-dir, all external http aborted).
//
// Run after a build: pnpm exec electron-vite build && node --test e2e/gpu-fallback.spec.mjs
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
// Defaults to the standard build output. OMI_E2E_MAIN points at a COPY of an `out/`
// tree instead — needed when something else in the checkout may rebuild `out/`
// (a dev server, a parallel agent) while this spec is running: the bundle
// assertions below are about the PRODUCTION bundle specifically, and a dev-mode
// rebuild underneath them would make this spec grade the wrong artifact.
const mainEntry = process.env.OMI_E2E_MAIN
  ? path.resolve(process.env.OMI_E2E_MAIN)
  : path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp')

const FIREBASE_API_KEY = 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8'
const PREFS_KEY = 'omi-windows-prefs-v1'
const WIDTHS = [1280, 1920]

// WebGL forcibly unavailable: no GPU process at all.
//
// NOTE (measured, not assumed): --disable-gpu and --disable-3d-apis passed through
// Electron's argv do NOT stop Chromium granting a WebGL context here — the first run
// of this spec asserted `webglAvailable === false` and got `true`. So the refusal is
// ALSO injected at the exact seam Chromium uses when it domain-blocks 3D APIs after
// a GPU crash loop: getContext returns null (see refuseWebglScript). That null is the
// real, observable symptom — it is what makes three's WebGLRenderer throw ("Error
// creating WebGL context.", verified against three r184 in
// components/graph/webglRendererThrows.test.ts) — so the app code under test takes
// exactly the branch it takes in the field.
const NO_GL_ARGS = ['--disable-gpu']

// Chromium's post-crash refusal, reproduced at its observable seam. Installed via
// addInitScript so it is in place before any app script runs, on every reload.
function refuseWebglScript() {
  const orig = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    if (typeof type === 'string' && type.includes('webgl')) return null
    return orig.call(this, type, ...rest)
  }
}
// Healthy control: software GL, WebGL alive (what dev builds use).
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-shader-disk-cache'
]

const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture']
const isSecondary = (u) => SECONDARY_HASHES.some((h) => u.includes(h))

const baseEnv = { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0', OMI_SKIP_TUNNEL: '1' }

async function blockExternalNetwork(page) {
  await page.route('**/*', (route) => {
    const url = route.request().url()
    if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)) return route.continue()
    if (/^https?:\/\//.test(url)) return route.abort()
    return route.continue()
  })
}

function seedAuthScript(apiKey) {
  const now = Date.now()
  localStorage.setItem(
    `firebase:authUser:${apiKey}:[DEFAULT]`,
    JSON.stringify({
      uid: 'e2e-gpu-user',
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

async function launch(glArgs) {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-gpu-e2e-'))
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`, ...glArgs],
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

async function setContentSize(app, width, height) {
  await app.evaluate(
    ({ BrowserWindow }, { width, height, SECONDARY_HASHES }) => {
      const win = BrowserWindow.getAllWindows().find(
        (b) => !SECONDARY_HASHES.some((h) => b.webContents.getURL().includes(h))
      )
      win.setResizable(true)
      win.setContentSize(width, height)
    },
    { width, height, SECONDARY_HASHES }
  )
  await new Promise((r) => setTimeout(r, 350))
}

// Land on the Language step (map shown) by completing the Name step for real, so
// the graph actually holds nodes — Onboarding calls resetOnboardingGraph on mount,
// so a step reached by reload alone would render an empty (legitimately bare) map.
async function gotoPopulatedMapStep(page) {
  await page.evaluate(
    ({ PREFS_KEY }) => {
      const prev = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
      delete prev.onboardingCompletedAt
      localStorage.setItem(PREFS_KEY, JSON.stringify({ ...prev, onboardingStep: 0 }))
    },
    { PREFS_KEY }
  )
  await page.reload()
  await page.waitForSelector('[data-testid="onboarding-content-pane"]', { timeout: 15000 })
  await page.locator('input[placeholder="Your name"]').fill('E2E User')
  await page.getByRole('button', { name: 'Continue' }).click()
  await page
    .locator('input[placeholder="Your name"]')
    .waitFor({ state: 'detached', timeout: 10000 })
  await new Promise((r) => setTimeout(r, 2500)) // let the map mount + reveal
}

async function bootOnboarding(app, { refuseWebgl = false } = {}) {
  const page = await mainPage(app)
  await blockExternalNetwork(page)
  if (refuseWebgl) await page.addInitScript(refuseWebglScript)
  await page.addInitScript(seedAuthScript, FIREBASE_API_KEY)
  await page.reload()
  await page.waitForSelector('[data-testid="onboarding-content-pane"]', { timeout: 15000 })
  return page
}

// What is actually on screen in the map pane?
async function inspectMap(page) {
  return page.evaluate(() => {
    const pane = document.querySelector('[data-testid="onboarding-map-pane"]')
    const probe = (() => {
      try {
        return document.createElement('canvas').getContext('webgl2') != null
      } catch {
        return false
      }
    })()
    return {
      webglAvailable: probe,
      hasFallback: !!document.querySelector('[data-testid="brain-graph-fallback"]'),
      canvasCount: document.querySelectorAll('canvas').length,
      // The pane must not be an empty hole: something has to be painted in it.
      paneChildren: pane?.querySelectorAll('svg, canvas').length ?? 0,
      onboardingAlive: !!document.querySelector('[data-testid="onboarding-content-pane"]')
    }
  })
}

describe('BrainGraph GPU resilience', () => {
  // The whole reason this bug shipped: the prevention was dev-gated, so nobody
  // checked the PRODUCTION bundle. Assert against the built artifact itself.
  test('the built production main bundle disables 3D-API domain blocking', () => {
    const built = readFileSync(mainEntry, 'utf8')
    assert.match(
      built,
      /app\.disableDomainBlockingFor3DAPIs\(\)/,
      'prod main must call disableDomainBlockingFor3DAPIs (a GPU crash must never permanently blocklist WebGL)'
    )
    // ...and it must not be smuggled in behind the dev-only software-render path,
    // which Rollup drops from the packaged bundle entirely.
    assert.doesNotMatch(
      built,
      /disableHardwareAcceleration/,
      'the dev-only GPU stability block must stay out of the production bundle'
    )
  })

  test('WebGL unavailable → static fallback, not a black void or a crashed screen', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch(NO_GL_ARGS)
    t.after(cleanup)
    const page = await bootOnboarding(app, { refuseWebgl: true })

    for (const width of WIDTHS) {
      await setContentSize(app, width, 820)
      await gotoPopulatedMapStep(page)
      await setContentSize(app, width, 820)

      const m = await inspectMap(page)
      const at = `@ ${width}px`
      console.log(`[no-gl ${at}]`, JSON.stringify(m))

      // The scenario really is GPU-less — otherwise this test proves nothing.
      assert.equal(m.webglAvailable, false, `${at}: WebGL really is unavailable`)
      // The screen survived (a throwing WebGLRenderer must not take onboarding down).
      assert.equal(m.onboardingAlive, true, `${at}: onboarding screen still mounted`)
      // The map degraded to the static mark rather than an empty pane.
      assert.equal(m.hasFallback, true, `${at}: static brain-map fallback is rendered`)
      assert.ok(m.paneChildren > 0, `${at}: map pane paints something (not an empty hole)`)

      await page.screenshot({ path: path.join(shotsDir, `gpu-fallback-${width}.png`) })
    }
  })

  // Scope note, so this is not read as more than it is: this asserts the WebGL
  // canvas still MOUNTS and the new fallback/boundary stays out of the way. It does
  // NOT assert pixels. The captured healthy screenshot shows a dark map pane — and
  // the identical pane is dark in .playwright-mcp/onboarding-step1-1280.png, which
  // onboarding-layout.spec.mjs captured on the SAME step with the SAME SwiftShader
  // args BEFORE this change. So that blank is a pre-existing paint issue (under
  // separate investigation), not a regression from the probe/fallback — and this
  // fallback deliberately does NOT fire for it, since WebGL is available there.
  test('healthy (software GL) → the WebGL canvas still mounts, no fallback, no throw', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch(SWIFTSHADER_ARGS)
    t.after(cleanup)
    const page = await bootOnboarding(app)

    for (const width of WIDTHS) {
      await setContentSize(app, width, 820)
      await gotoPopulatedMapStep(page)
      await setContentSize(app, width, 820)

      const m = await inspectMap(page)
      const at = `@ ${width}px`
      console.log(`[healthy ${at}]`, JSON.stringify(m))

      assert.equal(m.webglAvailable, true, `${at}: WebGL is available`)
      assert.equal(m.onboardingAlive, true, `${at}: onboarding screen still mounted`)
      // No regression: the real canvas mounts and the fallback stays out of the way.
      assert.ok(m.canvasCount > 0, `${at}: the WebGL canvas is mounted`)
      assert.equal(m.hasFallback, false, `${at}: no fallback on a healthy GPU`)

      await page.screenshot({ path: path.join(shotsDir, `gpu-healthy-${width}.png`) })
    }
  })
})
