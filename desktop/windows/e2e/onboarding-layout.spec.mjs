/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Onboarding split-pane layout E2E (Track 6): drives the REAL built app
// (out/main/index.js) via Playwright's _electron and asserts the onboarding
// shell never squishes the step card.
//
// The bug this guards: both panes were `flex-1`, and a flex item defaults to
// min-width:auto — it cannot shrink below its content's intrinsic width. The
// brain-map pane's child was `aspect-square h-full`, whose intrinsic width
// equals the pane HEIGHT (~716px at the default 1280x820 window). That pane
// therefore refused to shrink below ~780px and stole the width from the content
// pane, collapsing the StepScaffold card from its natural 400px to ~395px at
// 1280 and ~201px at 1024/900. The fix ports Mac's split shape: the content pane
// is bounded by its OWN constraints (470-560) and the map takes the remainder,
// the map square is WIDTH-driven, and the map is hidden below `lg` (1024px).
//
// Hermetic, and deliberately NOT via OMI_E2E_FAKE_AUTH: that flag hard-codes
// `onboarded = true` in App.tsx, which redirects /onboarding → /home, so the
// wizard would be unreachable. Instead we seed an offline Firebase session into
// localStorage (the app uses browserLocalPersistence) and block external
// network, exactly like onboarding-permission.spec.mjs. Throwaway
// --user-data-dir per launch. Screenshots land in .playwright-mcp/.
//
// Run after a build: node --test e2e/onboarding-layout.spec.mjs
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
// The StepScaffold card's natural width (StepScaffold `max-w-[400px]`). The card
// must never render narrower than this — narrower means it is being compressed.
const CARD_WIDTH = 400
// Below this the map pane is hidden outright (Tailwind `lg`), so the step card
// always gets the full canvas — a split pane is nonsense near minWidth: 500.
const MAP_BREAKPOINT = 1024
// Mac's split shape (OnboardingStepScaffold.swift `.frame(minWidth: 470,
// idealWidth: 520, maxWidth: 560)`): at lg+ the content pane is bounded by its
// OWN constraints and the map pane takes the remainder. The defect was the
// reverse — the map's intrinsic width dictating the content pane's width.
const CONTENT_MIN = 470
const CONTENT_MAX = 560

// Steps under test. 0 = Name (map hidden by step logic). 5 / 7 = permission
// steps (map shown — macOS shows the graph on ALL permission steps). 1 =
// Language, reached by completing the Name step for real, which is what actually
// puts NODES in the graph.
//
// Why the other steps' maps look bare: each launch gets a throwaway
// --user-data-dir, so the persisted graph store is empty. Onboarding's mount effect
// (initOnboardingGraph) clears at step 0 and HYDRATES the persisted store on a resume
// — hydrating an empty store yields an empty map. So a step reached by seeding
// `onboardingStep` and reloading legitimately draws (nearly) nothing. That is a
// property of the throwaway profile, not a GPU or layout failure — and it does not
// affect the verdict here, since every assertion below is a DOM measurement.
const STEPS = [0, 1, 5, 7]
// Steps reached by driving the real flow rather than by seeding `onboardingStep`.
const SEEDED_GRAPH_STEPS = new Set([1])
// 900 and 1000 prove the map is gone below `lg` (1000 straddles the breakpoint);
// the rest cover the default (1280) and the wide windows where the bug was
// invisible.
const WIDTHS = [900, 1000, 1024, 1280, 1600, 1920]

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

// Offline Firebase session (browserLocalPersistence → localStorage), seeded
// before any app script runs so App's auth gate passes. `onboardingCompletedAt`
// is deliberately absent, so the wizard runs.
function seedAuthScript(apiKey) {
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
}

// Software-GL switches, so the graph renders the same way on any machine that runs
// this spec (including a CI box with no usable GPU) and the captured screenshots are
// comparable. They are the same switches the app's dev-only workaround applies
// (src/main/dev/bench.ts applyDevGpuStability, gated on `import.meta.env.DEV` at
// src/main/index.ts) — which the PRODUCTION bundle launched here does NOT run, so
// production keeps hardware acceleration.
//
// That gating is a fact; what an earlier version of this comment did with it was not.
// It asserted the gating "means hardware WebGL dies on hybrid-GPU Windows boxes and
// the BrainGraph paints nothing" in production. That was never established and is
// retracted. The blank-map sightings are attributed to two real, separately fixed
// bugs: resetOnboardingGraph() wiping the map on every mount (71f9035b9) and a
// visibility:hidden canvas strand.
//
// Either way it does not affect this spec's verdict: the ASSERTIONS below are DOM
// measurements (getBoundingClientRect), never pixels.
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--disable-gpu-shader-disk-cache'
]

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-onboarding-e2e-'))
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

// Resize the REAL BrowserWindow (not just the viewport) so the CSS breakpoints
// and the flex layout see the same width a user's window would have.
async function setContentSize(app, width, height) {
  await app.evaluate(
    ({ BrowserWindow }, { width, height, SECONDARY_HASHES }) => {
      const win = BrowserWindow.getAllWindows().find((b) => {
        const u = b.webContents.getURL()
        return !SECONDARY_HASHES.some((h) => u.includes(h))
      })
      win.setResizable(true)
      win.setContentSize(width, height)
    },
    { width, height, SECONDARY_HASHES }
  )
  await new Promise((r) => setTimeout(r, 350))
}

// Onboarding resumes from the persisted `onboardingStep` pref, so seeding it and
// reloading lands directly on the step under test.
async function gotoStep(page, step) {
  await page.evaluate(
    ({ step, PREFS_KEY }) => {
      const prev = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
      delete prev.onboardingCompletedAt
      localStorage.setItem(PREFS_KEY, JSON.stringify({ ...prev, onboardingStep: step }))
    },
    { step, PREFS_KEY }
  )
  await page.reload()
  await page.waitForSelector('[data-testid="onboarding-content-pane"]', { timeout: 10000 })
  await new Promise((r) => setTimeout(r, 500))
}

// Step 1 (Language) with a POPULATED graph: complete the Name step for real, so
// `addUserNode` puts a node in the map. Seeding a later step and reloading would
// instead hydrate this throwaway profile's empty graph store, and the map would
// render nothing.
async function gotoLanguageStepViaNameEntry(page) {
  await gotoStep(page, 0)
  await page.locator('input[placeholder="Your name"]').fill('E2E User')
  await page.getByRole('button', { name: 'Continue' }).click()
  // The name input is gone once step 1 has mounted. (Don't wait on the map pane
  // being visible — below `lg` it is correctly hidden.)
  await page
    .locator('input[placeholder="Your name"]')
    .waitFor({ state: 'detached', timeout: 10000 })
  // Let the graph mount and run its reveal.
  await new Promise((r) => setTimeout(r, 2500))
}

async function measure(page) {
  return page.evaluate(() => {
    const content = document.querySelector('[data-testid="onboarding-content-pane"]')
    const map = document.querySelector('[data-testid="onboarding-map-pane"]')
    const card = content?.firstElementChild
    const square = map?.firstElementChild
    const box = (el) => {
      if (!el) return { w: 0, h: 0, left: 0, right: 0 }
      const r = el.getBoundingClientRect()
      return {
        w: Math.round(r.width),
        h: Math.round(r.height),
        left: Math.round(r.left),
        right: Math.round(r.right)
      }
    }
    const mapBox = box(map)
    return {
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      content: box(content),
      map: mapBox,
      mapVisible: mapBox.w > 0,
      card: box(card),
      square: box(square)
    }
  })
}

describe('Onboarding — split-pane layout never squishes the step card', () => {
  test('card keeps its natural width; map shrinks, hides below lg, stays square', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)
    const page = await mainPage(app)

    // Boot the wizard: block the network, seed the offline session, reload so
    // Firebase rehydrates it. The app then lands on /onboarding (no
    // onboardingCompletedAt), and gotoStep parks it on the step under test.
    await blockExternalNetwork(page)
    await page.addInitScript(seedAuthScript, FIREBASE_API_KEY)
    await page.reload()
    await page.waitForSelector('[data-testid="onboarding-content-pane"]', { timeout: 15000 })

    for (const step of STEPS) {
      for (const width of WIDTHS) {
        await setContentSize(app, width, 820)
        if (SEEDED_GRAPH_STEPS.has(step)) {
          await gotoLanguageStepViaNameEntry(page)
        } else {
          await gotoStep(page, step)
        }
        // Re-apply: the reload can restore the window's previous content size.
        await setContentSize(app, width, 820)
        const m = await measure(page)
        const at = `step ${step} @ ${width}px`

        // setContentSize can land a pixel off after DPI scaling — assert we got
        // the width we asked for within rounding, then measure against reality.
        assert.ok(
          Math.abs(m.innerWidth - width) <= 2,
          `${at}: window really is ~${width}px wide (got ${m.innerWidth})`
        )

        // 1. The card is never compressed below its natural max-w-[400px].
        assert.ok(
          m.card.w >= CARD_WIDTH,
          `${at}: card width ${m.card.w} >= ${CARD_WIDTH} (not squished)`
        )

        // 2. The card is fully inside the content pane (not clipped).
        assert.ok(
          m.card.left >= m.content.left - 1 && m.card.right <= m.content.right + 1,
          `${at}: card [${m.card.left},${m.card.right}] inside content pane [${m.content.left},${m.content.right}]`
        )

        // 3. No horizontal overflow anywhere on the page.
        assert.ok(
          m.scrollWidth <= m.innerWidth + 1,
          `${at}: no horizontal overflow (scrollWidth ${m.scrollWidth} <= innerWidth ${m.innerWidth})`
        )

        // 4. Below the lg breakpoint the map pane is gone entirely.
        if (m.innerWidth < MAP_BREAKPOINT) {
          assert.equal(m.mapVisible, false, `${at}: map pane hidden below ${MAP_BREAKPOINT}px`)
        }

        // 4b. With no map beside it, the card owns the whole canvas — the
        // content pane must NOT stay pinned to its split-mode basis, or the card
        // is stranded left of a wall of dead space.
        if (!m.mapVisible) {
          assert.ok(
            Math.abs(m.content.w - m.innerWidth) <= 2,
            `${at}: map-less step gets the full window (content ${m.content.w} ≈ ${m.innerWidth})`
          )
        }

        if (m.mapVisible) {
          // 5. Mac's split shape: the content pane is bounded by its OWN
          // constraints (470-560), and the map takes the remainder. This is the
          // core regression — the map's intrinsic width must never dictate the
          // content pane's width.
          assert.ok(
            m.content.w >= CONTENT_MIN && m.content.w <= CONTENT_MAX,
            `${at}: content pane ${m.content.w} within Mac's [${CONTENT_MIN}, ${CONTENT_MAX}]`
          )
          assert.ok(
            Math.abs(m.map.w - (m.innerWidth - m.content.w)) <= 2,
            `${at}: map pane ${m.map.w} takes the remainder (${m.innerWidth - m.content.w})`
          )
          // 6. The graph is still a square, and fits inside its pane.
          assert.ok(
            Math.abs(m.square.w - m.square.h) <= 2,
            `${at}: brain map is square (${m.square.w}x${m.square.h})`
          )
          assert.ok(
            m.square.w <= m.map.w && m.square.h <= m.map.h,
            `${at}: brain map ${m.square.w}x${m.square.h} fits pane ${m.map.w}x${m.map.h}`
          )
        }

        console.log(
          `[measure] step=${step} win=${m.innerWidth} content=${m.content.w} map=${m.mapVisible ? m.map.w : '(hidden)'} square=${m.square.w}x${m.square.h} card=${m.card.w} overflow=${m.scrollWidth > m.innerWidth + 1 ? 'YES' : 'no'}`
        )
        await page.screenshot({ path: path.join(shotsDir, `onboarding-step${step}-${width}.png`) })
      }
    }
  })
})
