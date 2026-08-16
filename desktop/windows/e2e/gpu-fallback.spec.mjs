/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// GPU-resilience E2E: drives the REAL built app (out/main/index.js) via Playwright's
// _electron, twice — once with WebGL forcibly unavailable, once on software GL —
// and proves the brain map degrades to a deliberate static mark instead of leaving
// a black void, without regressing the healthy render.
//
// WARNING — THIS SPEC POPS REAL WINDOWS ON YOUR DESKTOP, ON PURPOSE. One of the runs
// below launches the app with `--disable-gpu` plus a getContext-returns-null shim, so
// you will briefly see the app on screen showing the GREY STATIC MARK where the brain
// map belongs. That is the test doing its job, not the app breaking.
//
// WHAT THE EVIDENCE ACTUALLY SAYS. An earlier version of this header claimed a GPU
// "crash LOOP" — five `child-process-gone type=GPU` in 30s. That claim was FABRICATED
// and is retracted:
//   * REAL: %APPDATA%/omi-windows/crash.log holds 8 genuine `type=GPU reason=crashed`
//     deaths on this machine (2026-07-10 x7, 2026-07-11 x1), scattered across hours —
//     the closest pair 3 minutes apart. GPU-process death is a real event here.
//   * NOT OBSERVED: any crash *loop*. The five lines that started this investigation
//     were `reason=killed exitCode=1` — the signature of a CLEAN QUIT on Windows, where
//     the browser process ends its children with TerminateProcess. Our own Playwright
//     harness produced them by launching and quitting the app five times. The crash-log
//     handler only filtered `clean-exit`, so every ordinary quit forged a "GPU crash"
//     line. That handler bug is fixed (dab54dffd) and is now guarded by the clean-quit
//     test below.
//
// So what this spec guards is the consequence of a GPU death that leaves Chromium
// refusing new 3D contexts: three.js's WebGLRenderer throws and the pane would otherwise
// stay black. Onboarding is where that hurts most — the map is half of a new user's
// first screen. This spec does NOT claim to reproduce a loop.
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
import { mkdtempSync, rmSync, mkdirSync, readFileSync, existsSync } from 'node:fs'
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
// ALSO injected at the exact seam Chromium uses when it domain-blocks 3D APIs after it
// gives up on the GPU: getContext returns null (see refuseWebglScript). That null is the
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
  return { app, cleanup, dir }
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
// the graph actually holds nodes — this launch's --user-data-dir is throwaway, so
// its persisted graph store is empty and a step reached by reload alone would hydrate
// that empty store into a (legitimately) bare map.
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
  // force: the onboarding step card animates, and Playwright's actionability check
  // can wait forever for an element that is never "stable". We only need the click
  // to land; visibility/enabled are already guaranteed by the waits above.
  await page.getByRole('button', { name: 'Continue' }).click({ force: true })
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

  // Regression: a CLEAN QUIT must not be recorded as a GPU crash.
  //
  // On Windows, quitting terminates the GPU process with TerminateProcess, which
  // Chromium reports as `type=GPU reason=killed exitCode=1` — identical in every
  // field to a real GPU kill. The handler only filtered `clean-exit`, so every
  // ordinary quit appended a fatal GPU line to crash.log. Five quits then read as
  // a five-crash "GPU crash loop", which is exactly the phantom that sent us
  // chasing this in the first place — and it would have poisoned any fleet
  // telemetry keyed off this handler.
  test('a clean quit writes no GPU crash to crash.log', async () => {
    const { app, cleanup, dir } = await launch(SWIFTSHADER_ARGS)
    await mainPage(app) // fully booted, GPU process alive
    await app.close() // the real quit path (before-quit → isQuitting())
    // Give the crash handler a beat to have written anything it was going to.
    await new Promise((r) => setTimeout(r, 1500))

    const logPath = path.join(dir, 'crash.log')
    const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''
    console.log(`[clean-quit] crash.log: ${log ? JSON.stringify(log) : '(absent/empty)'}`)

    const gpuFatals = log
      .split('\n')
      .filter((l) => l.includes('[child-process-gone]') && l.includes('type=GPU'))
    assert.equal(
      gpuFatals.length,
      0,
      `a clean quit must not log a GPU crash, but crash.log has:\n${gpuFatals.join('\n')}`
    )
    await cleanup()
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

  // NON-REGRESSION PROOF, and the honest limits of it.
  //
  // This is the test that would have caught the regression that reached the product
  // owner: an earlier cut PRE-PROBED for a WebGL context and mounted the fallback
  // when the probe returned null. Because a probe must CREATE a context to answer,
  // and contexts are a capped shared resource, the probe itself failed near the cap
  // on a HEALTHY machine — and replaced his real brain map with the static mark.
  // The component now fails OPEN (three.js is the only authority on whether a
  // context can be had), so this asserts the real <canvas> mounts and the fallback
  // is absent whenever WebGL works.
  //
  // It does NOT assert pixels — it asserts STRUCTURE (a real <canvas> is mounted, the
  // fallback is not). Do not "strengthen" it with a pixel check by either route we
  // already tried and got wrong:
  //   * Reading back the GL drawing buffer proves NOTHING here. r3f defaults to
  //     `preserveDrawingBuffer: false`, under which the buffer is undefined (in
  //     practice all-zero) after compositing — so a readback returns zeros whether the
  //     graph painted beautifully or not at all. An earlier note in this file cited
  //     exactly such a readback as proof that "BrainGraph paints zero pixels even on a
  //     healthy context". That conclusion was UNSOUND and is retracted; the method
  //     cannot distinguish the two cases. (The orb harness gets away with readPixels
  //     only because orbRenderer.ts explicitly opts into preserveDrawingBuffer.)
  //   * An OS-level PrintWindow capture does not include GPU-composited canvas layers
  //     either, so a black PrintWindow bitmap is equally uninformative.
  // A sound pixel check needs either a canvas created WITH preserveDrawingBuffer, or a
  // real compositor capture (Playwright's page.screenshot, CDP capture). Until someone
  // does that, this test stays structural rather than pretending to more.
  test('healthy (software GL) → the REAL graph mounts; the fallback does NOT steal it', async (t) => {
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
