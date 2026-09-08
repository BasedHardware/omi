/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Knowledge-Graph viewer (PR10) E2E: drives the REAL built app (out/main/index.js)
// via Playwright's _electron and exercises the full-screen, INTERACTIVE brain-map
// route (#/knowledge-graph) against INTERCEPTED backend responses — page.route()
// fulfills the /v3/memories + /v1/knowledge-graph calls the viewer needs from
// fixtures, and a catch-all aborts everything else, so this never touches a real
// backend or real account data.
//
// Captures the screenshot set to .playwright-mcp/pr10/ for an INDEPENDENT
// reviewer. Build first, then run: `pnpm test:e2e:kg-viewer`.
import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'pr10')

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

const SECONDARY_HASHES = ['#/bar', '#/insight', '#/notch', '#/capture', '#/glow']
const isSecondary = (url) => SECONDARY_HASHES.some((h) => url.includes(h))

// ── Fixtures ────────────────────────────────────────────────────────────────
// Memories the viewer scopes the server KG to (useMemories -> useMemoryGraph).
const MEMORIES = [
  {
    id: 'mem-1',
    uid: 'e2e',
    content: 'I am building the Omi Windows desktop app.',
    created_at: '2026-07-01T14:30:00Z',
    updated_at: '2026-07-01T14:30:00Z'
  },
  {
    id: 'mem-2',
    uid: 'e2e',
    content: 'I write it in TypeScript with React and Electron.',
    created_at: '2026-07-02T09:00:00Z',
    updated_at: '2026-07-02T09:00:00Z'
  }
]

// Server knowledge graph. node_type/memory_ids match the backend snake_case shape
// (mapGraphResponse maps it). Every node references a CURRENT memory id so the
// memory-scoping keeps it; a person node makes it the auto-centered "you".
const GRAPH = {
  nodes: [
    { id: 'you', label: 'You', node_type: 'person', aliases: [], memory_ids: ['mem-1', 'mem-2'] },
    { id: 'omi', label: 'Omi', node_type: 'organization', aliases: [], memory_ids: ['mem-1'] },
    { id: 'windows-app', label: 'Windows App', node_type: 'thing', aliases: [], memory_ids: ['mem-1', 'mem-2'] },
    { id: 'typescript', label: 'TypeScript', node_type: 'thing', aliases: [], memory_ids: ['mem-2'] },
    { id: 'react', label: 'React', node_type: 'thing', aliases: [], memory_ids: ['mem-2'] },
    { id: 'electron', label: 'Electron', node_type: 'concept', aliases: [], memory_ids: ['mem-2'] }
  ],
  edges: [
    { id: 'e1', source_id: 'you', target_id: 'omi', label: 'builds', memory_ids: ['mem-1'] },
    { id: 'e2', source_id: 'you', target_id: 'windows-app', label: 'builds', memory_ids: ['mem-1'] },
    { id: 'e3', source_id: 'windows-app', target_id: 'typescript', label: 'uses', memory_ids: ['mem-2'] },
    { id: 'e4', source_id: 'windows-app', target_id: 'react', label: 'uses', memory_ids: ['mem-2'] },
    { id: 'e5', source_id: 'windows-app', target_id: 'electron', label: 'uses', memory_ids: ['mem-2'] }
  ]
}

const json = (route, body) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: { 'access-control-allow-origin': '*' },
    body: JSON.stringify(body)
  })

// Serve the two endpoints the viewer needs; abort everything else so no live
// traffic can leak (structural hermeticity — the catch-all is registered first so
// the specific handlers below win by Playwright's reverse-precedence).
async function stubBackend(page, { memories }) {
  await page.route('**/v1/**', (route) => route.abort())
  await page.route('**/v3/**', (route) => route.abort())
  await page.route('**/v3/memories**', (route) => json(route, memories))
  await page.route('**/v1/knowledge-graph**', (route) => json(route, GRAPH))
}

async function launch() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-kg-e2e-'))
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env: baseEnv })
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

const openGraph = (page) =>
  page.evaluate(() => {
    window.location.hash = '#/knowledge-graph'
  })

describe('Knowledge-Graph viewer — full-screen interactive brain map', () => {
  test('renders the interactive graph from memory-scoped data', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)

    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    await stubBackend(page, { memories: MEMORIES })

    await openGraph(page)

    // The full-screen chrome (title + back) renders regardless of WebGL health.
    await page.getByText('Brain Map', { exact: true }).waitFor({ state: 'visible', timeout: 20000 })
    await page.getByRole('button', { name: 'Back' }).waitFor({ state: 'visible' })
    // The interactive controls are present (this is the whole point vs the inline card).
    await page.getByRole('button', { name: /rebuild/i }).waitFor({ state: 'visible' })

    // The 3D scene mounted: a full-bleed WebGL <canvas> exists and fills the pane.
    // Pick the LARGEST canvas — the sidebar Orb is also an r3f canvas, so a naive
    // querySelector('canvas') can grab that tiny one instead of the brain map.
    const biggestCanvas = () => {
      const list = [...document.querySelectorAll('canvas')]
      let best = null
      for (const c of list) {
        const area = c.clientWidth * c.clientHeight
        if (!best || area > best.w * best.h) best = { w: c.clientWidth, h: c.clientHeight }
      }
      return best
    }
    await page.waitForFunction(
      () => {
        const list = [...document.querySelectorAll('canvas')]
        return list.some((c) => c.clientWidth > 600 && c.clientHeight > 400)
      },
      { timeout: 20000 }
    )
    const canvas = await page.evaluate(biggestCanvas)
    assert.ok(canvas, 'interactive brain-map canvas must be mounted')
    assert.ok(canvas.w > 600 && canvas.h > 400, `canvas must be full-bleed, got ${canvas.w}x${canvas.h}`)

    // The empty state must NOT be showing when there is graph data.
    assert.equal(
      await page.getByText('Your brain map is empty').count(),
      0,
      'empty state must not show with a populated graph'
    )

    await page.waitForTimeout(1200) // let the reveal animation settle for the shot
    await page.screenshot({ path: path.join(shotsDir, '01-populated-graph.png') })

    // Back returns to Memories (route is not a dead end).
    await page.getByRole('button', { name: 'Back' }).click()
    await page.waitForFunction(() => window.location.hash.includes('/memories'), { timeout: 8000 })
  })

  test('shows a sensible empty state (no blank canvas) when there is no graph', async (t) => {
    mkdirSync(shotsDir, { recursive: true })
    const { app, cleanup } = await launch()
    t.after(cleanup)

    const page = await mainPage(app)
    await page.setViewportSize({ width: 1280, height: 800 })
    // No memories => memory-scoped graph is empty (fresh profile has no onboarding floor).
    await stubBackend(page, { memories: [] })

    await openGraph(page)

    await page
      .getByText('Your brain map is empty')
      .waitFor({ state: 'visible', timeout: 20000 })
    // No brain-map WebGL scene is mounted for an empty graph. (The tiny sidebar
    // Orb is also an r3f canvas, so assert there's no LARGE/full-bleed canvas
    // rather than zero canvases outright.)
    const hasBigCanvas = await page.evaluate(() =>
      [...document.querySelectorAll('canvas')].some((c) => c.clientWidth > 600 && c.clientHeight > 400)
    )
    assert.equal(hasBigCanvas, false, 'empty graph must not mount a full-bleed brain-map canvas')
    // Chrome is still present (back affordance).
    await page.getByRole('button', { name: 'Back' }).waitFor({ state: 'visible' })

    await page.screenshot({ path: path.join(shotsDir, '02-empty-state.png') })
  })
})
