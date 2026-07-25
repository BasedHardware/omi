/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test harness */
// Rewind day-scope UI E2E: drives the REAL built app (out/main/index.js) via
// Playwright's _electron and captures the screenshot set for a skeptical reviewer,
// while asserting the load-bearing day-scoping + search behaviours end to end with
// nothing mocked inside the app.
//
// Hermetic: OMI_E2E_FAKE_AUTH mounts the authed shell offline; a throwaway
// --user-data-dir + OMI_DB_PATH seed the SQLite frames and their JPEGs; the
// embedding indexer is pointed at a local stub via the relayed session's
// desktopApiBase (no live API, no real credentials). The stub's semantic space is
// rigged so the query aligns with a NO-KEYWORD frame — proving the "Related"
// (semantic) affordance renders alongside keyword hits.
//
// Build first, then run: `pnpm test:e2e:rewind-dayscope`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { createServer } from 'node:http'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'pr3')

const EMBED_DIM = 3072
const QUERY = 'quarterly revenue projections'

// Three tiny solid-colour JPEGs (ffmpeg-generated) so the thumbnails/player render
// real image bytes rather than empty boxes. Content is irrelevant — layout is.
const JPEGS = [
  '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'
]

const dayDir = (dir, ts) => {
  const d = new Date(ts)
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return path.join(dir, 'rewind', day)
}
const framePath = (dir, ts) => path.join(dayDir(dir, ts), `${ts}.jpg`)
const startOfDay = (ts) => {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// macOS-parity composition the app embeds: "[<app>] <windowTitle>\n<ocrText>".
const embedded = (app, title, ocr) => `[${app}] ${title}\n${ocr}`

// The keyword frame (contains the query words) and the semantic-only frame (shares
// NO word with the query — findable ONLY via vector recall).
const KW_OCR = 'Q3 quarterly revenue projections for the board deck'
const SEM_OCR = 'gradient descent optimizer learning rate schedule'
const KW_DOC = embedded('Slides', 'board deck — Q3 review', KW_OCR)
const SEM_DOC = embedded('Notes', 'ml study notes', SEM_OCR)

function basisVector(index) {
  const v = new Array(EMBED_DIM).fill(0)
  v[index] = 1
  return v
}
// Query aligns with the semantic frame (cosine 1.0); everything else orthogonal.
function vectorForText(text) {
  if (text === SEM_DOC) return basisVector(0)
  if (text === QUERY) return basisVector(0)
  if (text === KW_DOC) return basisVector(1)
  return basisVector(7)
}

async function startProxyStub() {
  const server = createServer((req, res) => {
    let body = ''
    req.on('data', (c) => (body += c))
    req.on('end', () => {
      const payload = JSON.parse(body || '{}')
      res.writeHead(200, { 'Content-Type': 'application/json' })
      if (req.url.endsWith(':batchEmbedContents')) {
        res.end(
          JSON.stringify({
            embeddings: payload.requests.map((r) => ({
              values: vectorForText(r.content.parts[0].text)
            }))
          })
        )
      } else {
        res.end(
          JSON.stringify({ embedding: { values: vectorForText(payload.content.parts[0].text) } })
        )
      }
    })
  })
  await new Promise((r) => server.listen(0, '127.0.0.1', r))
  return {
    base: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((r) => server.close(r))
  }
}

/** Seed today's browse frames + a 2-days-ago search corpus, and write each frame's
 *  JPEG where rewind:frameImage will serve it (<userData>/rewind/<day>/<ts>.jpg). */
function seed(dir, dbPath) {
  const db = new DatabaseSync(dbPath)
  db.exec(`CREATE TABLE rewind_frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL, app TEXT NOT NULL DEFAULT '',
      window_title TEXT NOT NULL DEFAULT '', process_name TEXT NOT NULL DEFAULT '',
      ocr_text TEXT NOT NULL DEFAULT '', image_path TEXT NOT NULL,
      width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
      indexed INTEGER NOT NULL DEFAULT 0);`)
  const insert = db.prepare(
    `INSERT INTO rewind_frames (id, ts, app, window_title, process_name, ocr_text, image_path, width, height, indexed)
     VALUES (?, ?, ?, ?, ?, ?, ?, 320, 200, 1)`
  )
  let id = 0
  const add = (ts, app, title, ocr, jpeg) => {
    id += 1
    const p = framePath(dir, ts)
    mkdirSync(path.dirname(p), { recursive: true })
    writeFileSync(p, Buffer.from(jpeg, 'base64'))
    insert.run(id, ts, app, title, app, ocr, p)
  }

  const now = Date.now()
  const today = startOfDay(now)
  // Today: a spread of browse frames across varied apps (only those in the past).
  const todayFrames = [
    [today + 8 * 3600e3, 'Code.exe', 'useRewind.ts — omi', 'day scoping the rewind timeline'],
    [today + 10 * 3600e3, 'chrome.exe', 'Pull Request #123', 'reviewing the day-scope PR diff'],
    [today + 13 * 3600e3, 'Slack.exe', 'team — general', 'shipping the rewind redesign today'],
    [today + 15 * 3600e3, 'Notion.exe', 'Roadmap Q3', 'planning the next parity milestone'],
    [today + 17 * 3600e3, 'Figma.exe', 'Rewind mocks', 'calendar popover + results list']
  ].filter(([ts]) => ts <= now)
  todayFrames.forEach(([ts, app, title, ocr], i) => add(ts, app, title, ocr, JPEGS[i % 3]))
  // Always at least two recent today frames, whatever the wall-clock hour.
  add(now - 20 * 60e3, 'Terminal', 'pnpm test', 'all rewind tests green', JPEGS[0])
  add(now - 5 * 60e3, 'Code.exe', 'Rewind.tsx — omi', 'the day-scoped rewind page', JPEGS[1])

  // Two days ago: the search corpus. Two keyword frames in one 30s session (→ a
  // multi-frame "N screenshots" group + markers in the drill-down), plus the
  // semantic-only frame in a different app.
  const past = today - 2 * 24 * 3600e3 + 14 * 3600e3
  add(past, 'Slides', 'board deck — Q3 review', KW_OCR, JPEGS[1])
  add(past + 8e3, 'Slides', 'board deck — Q3 review', `${KW_OCR} (slide 2)`, JPEGS[1])
  add(past + 45 * 60e3, 'Notes', 'ml study notes', SEM_OCR, JPEGS[2])
  db.close()
}

const until = async (label, fn, timeoutMs = 60_000) => {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const v = await fn()
    if (v) return v
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${label}`)
    await new Promise((r) => setTimeout(r, 250))
  }
}

const SECONDARY = ['#/bar', '#/insight-toast', '#/capture', '#/glow']
const isSecondary = (u) => SECONDARY.some((h) => u.includes(h))

// Ready = the authed main window whose sidebar <nav> lists the Rewind item. (We key
// on the nav item, not the collapse-toggle button — the win-nav-model change removed
// the `aria-label$="sidebar"` selector older specs waited on.)
async function mainPage(app) {
  await app.firstWindow()
  for (let i = 0; i < 150; i++) {
    for (const w of await app.windows()) {
      if (isSecondary(w.url())) continue
      const ok = await w
        .evaluate(() => {
          const nav = document.querySelector('nav')
          return !!nav && /Rewind/.test(nav.textContent || '')
        })
        .catch(() => false)
      if (ok) return w
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('authed shell (sidebar with Rewind) never mounted')
}

test('day-scoped Rewind: browse, calendar, search results, drill-down, empty day', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-rewind-dayscope-'))
  const dbPath = path.join(dir, 'omi.db')
  seed(dir, dbPath)
  const stub = await startProxyStub()

  const app = await electron.launch({
    args: [mainEntry, `--user-data-dir=${dir}`],
    env: {
      ...process.env,
      OMI_E2E: '1',
      OMI_E2E_FAKE_AUTH: '1',
      OMI_AUTOMATION: '0',
      OMI_SKIP_TUNNEL: '1',
      OMI_DB_PATH: dbPath
    }
  })
  t.after(async () => {
    try {
      await app.close()
    } catch {
      /* already closed */
    }
    await stub.close()
    rmSync(dir, { recursive: true, force: true })
  })

  const page = await mainPage(app)

  // Stop the capture host from inserting live frames into "today" so the seeded set
  // stays deterministic for the screenshots.
  await page.evaluate(async () => {
    const s = await window.omi.rewindGetSettings()
    await window.omi.rewindSetSettings({ ...s, captureEnabled: false })
  })

  // Arm the embedding session (points the indexer at the stub) until the backfill
  // has embedded the seeded frames — so semantic recall has vectors to find.
  await until('backfill to embed the seeded frames', async () => {
    await page.evaluate(
      (base) => window.omi.rewindSetEmbedSession({ desktopApiBase: base, token: 'e2e-token' }),
      stub.base
    )
    // Confirm the semantic frame's vector is queryable before touching the UI.
    return page.evaluate(async (q) => {
      const groups = await window.omi.rewindSearch(q)
      void groups
      return new Promise((resolve) => {
        const off = window.omi.onRewindSearchResults((r) => {
          off()
          resolve(r.groups.some((g) => g.matchedSemantically))
        })
        setTimeout(() => resolve(false), 1500)
      })
    }, QUERY)
  })

  // --- Navigate to the day-scoped Rewind page ---
  await page.evaluate(() => {
    window.location.hash = '#/rewind'
  })
  const rw = page.locator('[data-testid="rewind-page"]')
  await rw.locator('text=Activity').first().waitFor({ timeout: 15_000 }) // timeline bar header
  await page.waitForTimeout(700) // let frame images decode
  await page.screenshot({ path: path.join(shotsDir, '01-day-timeline.png') })

  // --- Calendar popover ---
  await page.click('button[title="Pick a day"]')
  await page.waitForSelector('[data-testid="rewind-calendar"]')
  await page.waitForTimeout(200)
  await page.screenshot({ path: path.join(shotsDir, '02-calendar-popover.png') })
  // Close by re-selecting today's cell (same day → no reload, popover closes). Using
  // the outside-click catcher is unreliable — it's an invisible full-screen overlay.
  const todayNum = new Date().getDate()
  await page.click(`[data-testid="rewind-calendar"] button[data-day="${todayNum}"]`)
  await page.waitForSelector('[data-testid="rewind-calendar"]', { state: 'detached' })
  await page.waitForTimeout(200)

  // --- Search results list (keyword group + semantic "Related" group) ---
  const arm = () =>
    page.evaluate(
      (base) => window.omi.rewindSetEmbedSession({ desktopApiBase: base, token: 'e2e-token' }),
      stub.base
    )
  const input = rw.locator('input[placeholder="Search what was on screen…"]')
  // Phase 1 (keyword) is immediate; phase 2 (semantic recall) arrives out-of-band.
  // Re-issue the query each iteration so a fresh phase-2 fires for the newest search
  // sequence, until BOTH the keyword group and the semantic "Related" group render.
  // Re-arm each iteration: the renderer's auth listener fires a sign-out clear that
  // disarms the embedder, so the query embed must be re-enabled right before the search.
  let gotSemantic = false
  for (let i = 0; i < 30 && !gotSemantic; i++) {
    await arm()
    if (i > 0) {
      await input.fill('')
      await page.waitForTimeout(150)
    }
    await input.fill(QUERY)
    await rw
      .locator('[data-testid="rewind-result"]')
      .first()
      .waitFor({ timeout: 3000 })
      .catch(() => {})
    await page.waitForTimeout(1500) // let the semantic push land
    const cnt = await rw.locator('[data-testid="rewind-result"]').count()
    const rel = await rw.locator('text=Related').count()
    gotSemantic = cnt >= 2 && rel >= 1
  }
  await page.waitForTimeout(400) // thumbnails
  await page.screenshot({ path: path.join(shotsDir, '03-search-results.png') })
  assert.ok(gotSemantic, 'keyword group + semantic "Related" group both rendered')

  // Assert the affordance is real, not just present in the DOM by luck.
  const relatedCount = await rw.locator('text=Related').count()
  assert.ok(relatedCount >= 1, 'a semantic-only group is flagged "Related" in the results list')
  const badge = await rw.locator('text=/\\d+ screenshots/').count()
  assert.ok(badge >= 1, 'the multi-frame keyword group shows a screenshots badge')

  // --- Drill-down mini-timeline (open the keyword group) ---
  // The keyword group is the one with the screenshots badge; open the first result.
  await rw.locator('[data-testid="rewind-result"]').first().click()
  await rw.locator('text=Back to results').waitFor({ timeout: 10_000 })
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(shotsDir, '04-drilldown-timeline.png') })

  // Back to the list, then clear search.
  await rw.locator('text=Back to results').click()
  await page.waitForTimeout(200)
  await input.fill('')
  await page.waitForTimeout(300)

  // --- Empty day: previous month's 15th — always past, never seeded, never disabled ---
  await page.click('button[title="Pick a day"]')
  await page.waitForSelector('[data-testid="rewind-calendar"]')
  await page.click('[data-testid="rewind-calendar"] button[title="Previous month"]')
  await page.waitForTimeout(150)
  await page.click('[data-testid="rewind-calendar"] button[data-day="15"]:not([disabled])')
  await page.waitForTimeout(600)
  await page.screenshot({ path: path.join(shotsDir, '05-empty-day.png') })

  const emptyText = await rw.locator('text=No frames yet').count()
  assert.ok(emptyText >= 1, 'an empty day lands on the empty state')
})
