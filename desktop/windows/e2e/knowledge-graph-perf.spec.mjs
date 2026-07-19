/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Brain-map PERFORMANCE harness. Drives the REAL built app (out/main/index.js) via
// Playwright's _electron, renders the full-screen interactive #/knowledge-graph
// against an INTERCEPTED synthetic graph matched to the measured real-account
// scale (188 nodes / 474 edges, one ~226-degree hub — see
// e2e/fixtures/brainmap-scale-graph.mjs), and reports:
//   - three.js draw calls / triangles once the scene has settled
//   - a sustained rAF frame rate (fps) over a 4s window
//   - the same after clicking "Show all N nodes" (the escape hatch)
//
// This is EVIDENCE, not a pass/fail assertion of a magic fps number (the dev
// WebGL path is forced to software rendering, so absolute fps is lower than the
// user's hardware GPU — the BEFORE/AFTER delta and the draw-call reduction are
// the hardware-independent signal). Run: `pnpm test:e2e:kg-perf`.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { buildScaleGraph } from './fixtures/brainmap-scale-graph.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'brainmap-perf')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}
const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

const GRAPH = buildScaleGraph()
const MEMORIES = Array.from({ length: 125 }, (_, i) => ({
  id: `m${i}`,
  uid: 'e2e',
  content: `memory ${i}`,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z'
}))

const json = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

async function stubBackend(page) {
  await page.route('**/v1/**', (route) => route.abort())
  await page.route('**/v3/**', (route) => route.abort())
  await page.route('**/v3/memories**', (route) => json(route, MEMORIES))
  await page.route('**/v1/knowledge-graph**', (route) => json(route, GRAPH))
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

// Sustained frame rate: count rAF ticks over `ms`. Reads real compositor cadence.
const measureFps = (page, ms) =>
  page.evaluate(
    (ms) =>
      new Promise((resolve) => {
        let frames = 0
        const t0 = performance.now()
        const tick = () => {
          frames++
          if (performance.now() - t0 >= ms)
            resolve(Math.round((frames * 1000) / (performance.now() - t0)))
          else requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }),
    ms
  )

describe('Brain-map performance at real-account scale', () => {
  test('measure draw calls + fps, default view and show-all', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const dir = mkdtempSync(path.join(tmpdir(), 'omi-kgperf-'))
    const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env: baseEnv })
    t.after(async () => {
      await app.close().catch(() => {})
      try {
        rmSync(dir, { recursive: true, force: true })
      } catch {
        /* best-effort */
      }
    })

    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    await stubBackend(page)
    await page.evaluate(() => (window.location.hash = '#/knowledge-graph'))

    await page.getByText('Brain Map', { exact: true }).waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForFunction(
      () =>
        [...document.querySelectorAll('canvas')].some(
          (c) => c.clientWidth > 600 && c.clientHeight > 400
        ),
      { timeout: 20000 }
    )
    await page.waitForTimeout(3000) // let the layout settle before sampling

    const drawCalls = (p) => p.evaluate(() => window.__omiGraphDrawCalls ?? -1)

    const fpsDefault = await measureFps(page, 4000)
    const callsDefault = await drawCalls(page)
    await page.screenshot({ path: path.join(shotsDir, 'default-view.png') })
    console.log(
      `[kg-perf] DEFAULT nodes=${GRAPH.nodes.length} edges=${GRAPH.edges.length} fps=${fpsDefault} drawCalls=${callsDefault}`
    )

    // Picking after instancing: hovering a node must still name it (instanceId
    // hit-testing on the InstancedMesh). Sweep the dense cloud centre; the pointer
    // cursor flips to 'pointer' the moment the raycast hits an instanced sphere.
    const box = await page
      .locator('canvas')
      .filter({ has: page.locator('visible=true') })
      .first()
      .boundingBox()
      .catch(() => null)
    let hovered = false
    for (let dx = -60; dx <= 60 && !hovered; dx += 20) {
      for (let dy = -60; dy <= 60 && !hovered; dy += 20) {
        await page.mouse.move(640 + dx, 400 + dy)
        await page.waitForTimeout(60)
        hovered = await page.evaluate(() => document.body.style.cursor === 'pointer')
      }
    }
    assert.ok(hovered, 'hovering a node must set the pointer cursor (instanceId picking works)')
    console.log(`[kg-perf] PICKING hover→pointer OK (canvas ${box ? `${Math.round(box.width)}x${Math.round(box.height)}` : 'n/a'})`)

    // Escape hatch: if a "Show all" control exists (post-change), exercise it.
    const showAll = page.getByRole('button', { name: /show all/i })
    if ((await showAll.count()) > 0) {
      await showAll.first().click()
      await page.waitForTimeout(3000)
      const fpsAll = await measureFps(page, 4000)
      const callsAll = await drawCalls(page)
      await page.screenshot({ path: path.join(shotsDir, 'show-all-view.png') })
      console.log(`[kg-perf] SHOW_ALL fps=${fpsAll} drawCalls=${callsAll}`)
    } else {
      console.log('[kg-perf] SHOW_ALL control absent (baseline / capless build)')
    }
  })
})
