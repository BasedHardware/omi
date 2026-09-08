/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Cold-start cache-first E2E: proves the per-uid persistentCache mechanism end to
// end in the REAL built app (out/main/index.js) via Playwright's _electron.
//
// The mechanism: a surface persists its last-known rows to a per-uid localStorage
// snapshot; on the NEXT app launch it hydrates from that snapshot and renders
// instantly instead of flashing a spinner, then revalidates. This spec exercises
// the reference consumer (the Memories page) across TWO launches sharing one
// userData dir (so localStorage survives the restart — a real cold start):
//   Launch 1: stub /v3/memories -> fixtures, open Memories, confirm the snapshot
//             is written to localStorage under the per-uid key.
//   Launch 2: ABORT /v3/memories (network down) and confirm the memories STILL
//             render — they can only have come from the persisted snapshot.
//
// Fake auth (OMI_E2E_FAKE_AUTH) mounts the authed shell without Firebase, so it
// never sets omi.lastSignedInUid; the spec sets it explicitly to a fixed test uid.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'cold-start')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const TEST_UID = 'coldstart-e2e-uid'
const SNAPSHOT_KEY = `omi.cache.memories.${TEST_UID}`

// Distinctive content so getByText can't match incidental UI copy.
const MEMORIES = [
  {
    id: 'cs-1',
    uid: TEST_UID,
    content: 'COLDSTART-FIXTURE-ALPHA is my first persisted memory.',
    created_at: '2026-07-01T14:30:00Z',
    updated_at: '2026-07-01T14:30:00Z'
  },
  {
    id: 'cs-2',
    uid: TEST_UID,
    content: 'COLDSTART-FIXTURE-BRAVO is my second persisted memory.',
    created_at: '2026-07-02T09:00:00Z',
    updated_at: '2026-07-02T09:00:00Z'
  }
]

const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

const json = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

async function launch(userDataDir) {
  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${userDataDir}`],
    env: baseEnv
  })
  return app
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

const openMemories = (page) =>
  page.evaluate(() => {
    window.location.hash = '#/memories'
  })

describe('Cold-start cache-first — Memories renders from the persisted snapshot', () => {
  test('launch 1 persists the snapshot; launch 2 renders it with the network down', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    // ONE userData dir shared by both launches = a real app restart.
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-coldstart-e2e-'))
    t.after(() => {
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    // ── Launch 1: populate + persist ─────────────────────────────────────────
    let app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      // Fake auth never sets the uid pointer the cache scopes on — set it here.
      await page.evaluate((uid) => localStorage.setItem('omi.lastSignedInUid', uid), TEST_UID)
      await page.route('**/v3/memories**', (route) => json(route, MEMORIES))

      await openMemories(page)
      await page
        .getByText(/COLDSTART-FIXTURE-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })

      // The per-uid snapshot must now be written to localStorage.
      const snapshot = await page.evaluate((k) => localStorage.getItem(k), SNAPSHOT_KEY)
      assert.ok(snapshot, `launch 1 must persist the snapshot under ${SNAPSHOT_KEY}`)
      const ids = JSON.parse(snapshot).map((m) => m.id)
      assert.deepEqual(ids.sort(), ['cs-1', 'cs-2'], 'snapshot must hold the fetched memories')
      await page.screenshot({ path: path.join(shotsDir, '01-launch1-populated.png') })
    }
    await app.close()

    // ── Launch 2: network down, must render from the snapshot ─────────────────
    app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      // Kill the memories network entirely. If memories still render, they came
      // from the persisted snapshot — the whole point of cache-first cold start.
      await page.route('**/v3/memories**', (route) => route.abort())

      await openMemories(page)
      await page
        .getByText(/COLDSTART-FIXTURE-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })
      await page.getByText(/COLDSTART-FIXTURE-BRAVO/).waitFor({ state: 'visible' })

      // The "No memories yet" empty state must NOT show — we have cached rows.
      assert.equal(
        await page.getByText('No memories yet').count(),
        0,
        'empty state must not show when a snapshot exists'
      )
      await page.screenshot({ path: path.join(shotsDir, '02-launch2-from-cache.png') })
    }
    await app.close()
  })
})

// ── Conversations ────────────────────────────────────────────────────────────
const CONV_SNAPSHOT_KEY = `omi.cache.conversations.${TEST_UID}`
const CONVOS = [
  {
    id: 'cv-1',
    structured: { title: 'COLDSTART-CONV-ALPHA', overview: 'first cached conversation' },
    created_at: '2026-07-01T14:30:00Z'
  },
  {
    id: 'cv-2',
    structured: { title: 'COLDSTART-CONV-BRAVO', overview: 'second cached conversation' },
    created_at: '2026-07-02T09:00:00Z'
  }
]

const openConversations = (page) =>
  page.evaluate(() => {
    window.location.hash = '#/conversations'
  })

// Match GET /v1/conversations exactly (not the folders sub-route) regardless of
// query string.
const isConversationsList = (url) => url.pathname.replace(/\/+$/, '') === '/v1/conversations'

describe('Cold-start cache-first — Conversations renders from the persisted snapshot', () => {
  test('launch 1 persists; launch 2 keeps the cached list with the cloud fetch down', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-coldstart-conv-e2e-'))
    t.after(() => {
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    // ── Launch 1: populate + persist ─────────────────────────────────────────
    let app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      await page.evaluate((uid) => localStorage.setItem('omi.lastSignedInUid', uid), TEST_UID)
      // Serve just the conversations list; other startup calls fail gracefully
      // (fake auth, no tunnel) — narrow stub mirrors the Memories scenario.
      await page.route(isConversationsList, (route) => json(route, CONVOS))

      await openConversations(page)
      await page
        .getByText(/COLDSTART-CONV-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })

      const snapshot = await page.evaluate((k) => localStorage.getItem(k), CONV_SNAPSHOT_KEY)
      assert.ok(snapshot, `launch 1 must persist the snapshot under ${CONV_SNAPSHOT_KEY}`)
      const ids = JSON.parse(snapshot).map((r) => r.id)
      assert.deepEqual(ids.sort(), ['cv-1', 'cv-2'], 'snapshot must hold the fetched conversations')
      await page.screenshot({ path: path.join(shotsDir, '03-conv-launch1-populated.png') })
    }
    await app.close()

    // ── Launch 2: cloud fetch down, must KEEP the cached list (no wipe) ───────
    app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      // Abort just the conversations list so the revalidation's cloud fetch fails;
      // the resilience guard must keep the hydrated rows shown.
      await page.route(isConversationsList, (route) => route.abort())

      await openConversations(page)
      await page
        .getByText(/COLDSTART-CONV-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })

      // Let the failing revalidation complete, then assert the rows did NOT get
      // wiped down to empty (the bug the guard prevents).
      await page.waitForTimeout(1500)
      assert.ok(
        await page.getByText(/COLDSTART-CONV-ALPHA/).isVisible(),
        'cached conversation must stay on screen after a failed revalidation'
      )
      assert.ok(
        await page.getByText(/COLDSTART-CONV-BRAVO/).isVisible(),
        'all cached conversations must stay on screen after a failed revalidation'
      )
      await page.screenshot({ path: path.join(shotsDir, '04-conv-launch2-from-cache.png') })
    }
    await app.close()
  })
})

// ── Apps / Marketplace ───────────────────────────────────────────────────────
const APPS_SNAPSHOT_KEY = `omi.cache.apps.${TEST_UID}`
// Minimal /v2/apps catalog: one 'popular' group with a distinctively named app.
const APPS_CATALOG = {
  groups: [
    {
      capability: { id: 'popular', title: 'Popular' },
      data: [{ id: 'coldstart-app', name: 'COLDSTART-APP-ALPHA', category: 'other' }]
    }
  ]
}

const openApps = (page) =>
  page.evaluate(() => {
    window.location.hash = '#/apps'
  })

const isAppsCatalog = (url) => url.pathname.replace(/\/+$/, '') === '/v2/apps'
const isAppsList = (url) => url.pathname.replace(/\/+$/, '') === '/v1/apps'
const isAppsEnabled = (url) => url.pathname.replace(/\/+$/, '') === '/v1/apps/enabled'

describe('Cold-start cache-first — Apps renders from the persisted snapshot', () => {
  test('launch 1 persists; launch 2 keeps the cached grid with the catalog down', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-coldstart-apps-e2e-'))
    t.after(() => {
      try {
        rmSync(userDataDir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    // ── Launch 1: populate + persist ─────────────────────────────────────────
    let app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      await page.evaluate((uid) => localStorage.setItem('omi.lastSignedInUid', uid), TEST_UID)
      await page.route(isAppsCatalog, (route) => json(route, APPS_CATALOG))
      await page.route(isAppsList, (route) => json(route, []))
      await page.route(isAppsEnabled, (route) => json(route, []))

      await openApps(page)
      await page
        .getByText(/COLDSTART-APP-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })

      const snapshot = await page.evaluate((k) => localStorage.getItem(k), APPS_SNAPSHOT_KEY)
      assert.ok(snapshot, `launch 1 must persist the snapshot under ${APPS_SNAPSHOT_KEY}`)
      const names = JSON.parse(snapshot).allApps.map((a) => a.name)
      assert.ok(names.includes('COLDSTART-APP-ALPHA'), 'snapshot must hold the fetched apps')
      await page.screenshot({ path: path.join(shotsDir, '05-apps-launch1-populated.png') })
    }
    await app.close()

    // ── Launch 2: catalog down, must render the cached grid ───────────────────
    app = await launch(userDataDir)
    {
      const page = await mainPage(app)
      await page.setViewportSize({ width: 1280, height: 800 })
      // Abort the catalog fetch (the one call load() doesn't .catch) so the load
      // fails; the cached grid must stay on screen (load only overwrites on success).
      await page.route(isAppsCatalog, (route) => route.abort())

      await openApps(page)
      await page
        .getByText(/COLDSTART-APP-ALPHA/)
        .waitFor({ state: 'visible', timeout: 20000 })
      await page.waitForTimeout(1200)
      assert.ok(
        await page.getByText(/COLDSTART-APP-ALPHA/).isVisible(),
        'cached app must stay on screen after a failed catalog fetch'
      )
      await page.screenshot({ path: path.join(shotsDir, '06-apps-launch2-from-cache.png') })
    }
    await app.close()
  })
})
