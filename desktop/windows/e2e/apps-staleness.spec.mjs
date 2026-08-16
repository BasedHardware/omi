/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Live E2E for the two Apps-page bugs from the 2026-07-19 C/D/E sweep, exercised in
// the REAL built app (out/main/index.js) via Playwright's _electron:
//
//   Bug 1 (enabled-set staleness): the enabled set is only fetched on mount, so an
//     app enabled out-of-band (web / another device) stays "Install" until relaunch.
//     Fix: revalidate load() on window focus. Here we flip the /v1/apps/enabled
//     response, dispatch a window 'focus' event, and confirm the card flips to
//     "Installed" — proving the enabled set was re-fetched without a relaunch.
//
//   Bug 2 (search fallback): when /v2/apps/search fails the page must fall back to a
//     client-side search of the already-loaded catalog rather than render empty.
//     Here we ABORT /v2/apps/search, type a query, and confirm the local match plus
//     the "search temporarily unavailable" hint render.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'apps-staleness')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const TEST_UID = 'apps-staleness-e2e-uid'
const APP_ID = 'searchable-app'
const APP_NAME = 'SEARCHABLE-WIDGET-ALPHA'

const CATALOG = {
  groups: [
    {
      capability: { id: 'popular', title: 'Popular' },
      data: [{ id: APP_ID, name: APP_NAME, category: 'other', description: 'A findable widget.' }]
    }
  ]
}

const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

const json = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

const isAppsCatalog = (url) => url.pathname.replace(/\/+$/, '') === '/v2/apps'
const isAppsList = (url) => url.pathname.replace(/\/+$/, '') === '/v1/apps'
const isAppsEnabled = (url) => url.pathname.replace(/\/+$/, '') === '/v1/apps/enabled'
const isAppsSearch = (url) => url.pathname.replace(/\/+$/, '') === '/v2/apps/search'

async function launch(userDataDir) {
  return electron.launch({ args: [mainEntry, `--user-data-dir=${userDataDir}`], env: baseEnv })
}

async function mainPage(app) {
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

const openApps = (page) =>
  page.evaluate(() => {
    window.location.hash = '#/apps'
  })

describe('Apps staleness + search-fallback — live', () => {
  test('bug 1: enabled set revalidates on window focus (out-of-band install appears)', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-apps-focus-e2e-'))
    t.after(() => {
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    const app = await launch(userDataDir)
    t.after(() => app.close())
    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.evaluate((uid) => localStorage.setItem('omi.lastSignedInUid', uid), TEST_UID)

    // The enabled set starts empty and flips to [APP_ID] out-of-band. We count hits so
    // we can prove the focus event triggered a fresh fetch (not just cache).
    let enabledFlipped = false
    let enabledHits = 0
    await page.route(isAppsCatalog, (route) => json(route, CATALOG))
    await page.route(isAppsList, (route) => json(route, []))
    await page.route(isAppsEnabled, (route) => {
      enabledHits += 1
      return json(route, enabledFlipped ? [APP_ID] : [])
    })

    await openApps(page)
    // The card renders and shows "Install" (not enabled yet).
    await page.getByText(APP_NAME).waitFor({ state: 'visible', timeout: 20000 })
    await page
      .getByRole('button', { name: 'Install', exact: true })
      .first()
      .waitFor({ state: 'visible', timeout: 20000 })
    const hitsAfterMount = enabledHits
    assert.ok(hitsAfterMount >= 1, 'the enabled set is fetched on mount')
    await page.screenshot({ path: path.join(shotsDir, '01-before-focus-not-installed.png') })

    // Out-of-band install happens (another device / the web app), then the window
    // regains focus. The fix must re-fetch the enabled set and flip the card.
    enabledFlipped = true
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))

    await page
      .getByRole('button', { name: 'Installed', exact: true })
      .first()
      .waitFor({ state: 'visible', timeout: 20000 })
    assert.ok(enabledHits > hitsAfterMount, 'focus must trigger a fresh /v1/apps/enabled fetch')
    await page.screenshot({ path: path.join(shotsDir, '02-after-focus-installed.png') })
  })

  test('bug 2: search falls back to the local catalog when /v2/apps/search fails', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-apps-search-e2e-'))
    t.after(() => {
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    const app = await launch(userDataDir)
    t.after(() => app.close())
    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.evaluate((uid) => localStorage.setItem('omi.lastSignedInUid', uid), TEST_UID)

    await page.route(isAppsCatalog, (route) => json(route, CATALOG))
    await page.route(isAppsList, (route) => json(route, []))
    await page.route(isAppsEnabled, (route) => json(route, []))
    // The remote search endpoint is down.
    await page.route(isAppsSearch, (route) => route.abort())

    await openApps(page)
    await page.getByText(APP_NAME).waitFor({ state: 'visible', timeout: 20000 })

    // Type a query that only the local catalog can satisfy (remote search aborts).
    await page.getByPlaceholder('Search apps…').fill('SEARCHABLE')

    // The fallback hint appears AND the local match still renders (not an empty list).
    await page
      .getByText(/search is temporarily unavailable/i)
      .waitFor({ state: 'visible', timeout: 20000 })
    assert.ok(
      await page.getByText(APP_NAME).isVisible(),
      'the locally-matched app must render from the fallback, not an empty result'
    )
    assert.equal(
      await page.getByText('No apps match').count(),
      0,
      'a fallback with hits must not show the empty state'
    )
    await page.screenshot({ path: path.join(shotsDir, '03-search-fallback.png') })
  })
})
