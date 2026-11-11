/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS verification harness */
// LIVE verification for fix/win-rewind-timeline-scroll: drives the REAL built app
// (out/main/index.js) via Playwright's _electron. Seeds a heavy, CONTINUOUS "today"
// so the Activity timeline bar genuinely overflows the viewport, then drives real
// mouse-wheel pans and asserts:
//   1. the timeline bar is genuinely scrollable (scrollWidth > clientWidth),
//   2. PAUSED: a wheel pan moves it and it STAYS put (no re-center yank),
//   3. hover routing: wheel over the timeline pans the timeline (filmstrip untouched)
//      and wheel over the filmstrip pans the filmstrip (timeline untouched),
//   4. PLAYING: a small wheel pan STAYS instead of being snapped back to center every
//      700ms (the reported "can't scroll it" bug).
// Hermetic: OMI_E2E_FAKE_AUTH mounts the authed shell offline; a throwaway
// --user-data-dir + OMI_DB_PATH seed the frames + JPEGs. No live API, no credentials.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { _electron as electron } from 'playwright'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const shotsDir = path.join(root, '.playwright-mcp', 'rewind-scroll')

// One tiny solid JPEG — content is irrelevant, only that a file exists at the path.
const JPEG =
  '/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYyLjI4LjEwMAD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABMAAEBAAAAAAAAAAAAAAAAAAAABgEBAQAAAAAAAAAAAAAAAAAAAAUQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCADIAUADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCEAVU0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB//2Q=='
const JPEG_BYTES = Buffer.from(JPEG, 'base64')

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

// A continuous 5-min-cadence day from local midnight → now: no ≥30min gap, so the
// mapping is one linear piece ~= (hoursSoFar * 140)px wide, which overflows any
// normal window. Every frame gets a real JPEG so the player/filmstrip don't error.
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
  const now = Date.now()
  const today = startOfDay(now)
  const step = 5 * 60e3
  const apps = ['Code.exe', 'chrome.exe', 'Slack.exe', 'Notion.exe', 'Figma.exe']
  let id = 0
  let count = 0
  db.exec('BEGIN')
  for (let ts = today + step; ts <= now - 60e3; ts += step) {
    id += 1
    count += 1
    const p = framePath(dir, ts)
    mkdirSync(path.dirname(p), { recursive: true })
    writeFileSync(p, JPEG_BYTES)
    const app = apps[id % apps.length]
    insert.run(id, ts, app, `${app} — window ${id}`, app, `frame ${id} on-screen text`, p)
  }
  db.exec('COMMIT')
  db.close()
  return { count, spanH: (now - (today + step)) / 3600e3 }
}

const SECONDARY = ['#/bar', '#/insight-toast', '#/capture', '#/glow']
const isSecondary = (u) => SECONDARY.some((h) => u.includes(h))
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

const readBar = (loc) =>
  loc.evaluate((el) => ({ sl: Math.round(el.scrollLeft), cw: el.clientWidth, sw: el.scrollWidth }))

async function wheelOver(page, loc, dy) {
  const box = await loc.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.wheel(0, dy)
  await page.waitForTimeout(120)
}

test('rewind timeline bar: overflow, wheel pan stays, hover routing, play does not yank', async (t) => {
  mkdirSync(shotsDir, { recursive: true })
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-rewind-scroll-'))
  const dbPath = path.join(dir, 'omi.db')
  const info = seed(dir, dbPath)
  console.log(`[seed] ${info.count} frames spanning ${info.spanH.toFixed(1)}h of continuous today`)

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
    rmSync(dir, { recursive: true, force: true })
  })

  const page = await mainPage(app)
  // Freeze the seeded set: stop the live capture host inserting today frames.
  await page.evaluate(async () => {
    const s = await window.omi.rewindGetSettings()
    await window.omi.rewindSetSettings({ ...s, captureEnabled: false })
  })

  await page.evaluate(() => {
    window.location.hash = '#/rewind'
  })
  const rw = page.locator('[data-testid="rewind-page"]')
  await rw.locator('text=Activity').first().waitFor({ timeout: 15_000 })
  await page.waitForTimeout(800)

  const timeline = rw.locator('.no-scrollbar.overflow-x-auto')
  const filmstrip = rw.locator('.overflow-x-auto.py-2')

  // 1) Genuinely scrollable.
  const t0 = await readBar(timeline)
  console.log('[timeline] initial', t0)
  assert.ok(t0.sw > t0.cw + 50, `timeline overflows viewport (sw=${t0.sw} > cw=${t0.cw})`)

  // 2) PAUSED wheel pan + hover routing (wheel over timeline only moves timeline).
  const f0 = await readBar(filmstrip)
  const tDir = t0.sl < (t0.sw - t0.cw) / 2 ? 1 : -1 // pan toward the roomy side
  await wheelOver(page, timeline, tDir * 600)
  const t1 = await readBar(timeline)
  const f1 = await readBar(filmstrip)
  console.log('[paused] after wheel over timeline: timeline', t1, 'filmstrip', f1)
  assert.ok(Math.abs(t1.sl - t0.sl) > 100, `wheel panned the timeline (${t0.sl} → ${t1.sl})`)
  assert.equal(f1.sl, f0.sl, 'filmstrip did NOT move when wheeling over the timeline (routing)')

  // 3) It STAYS put (no re-center yank while paused).
  await page.waitForTimeout(1600)
  const t2 = await readBar(timeline)
  console.log('[paused] 1.6s later (still paused):', t2)
  assert.ok(Math.abs(t2.sl - t1.sl) <= 3, `paused pan stayed put (${t1.sl} → ${t2.sl})`)
  await page.screenshot({ path: path.join(shotsDir, '01-paused-panned.png') })

  // 4) Reverse routing: wheel over the filmstrip scrolls the FILMSTRIP. (The timeline
  //    then follows the shared cursor via the filmstrip's onScroll → onSeek → cursorTs;
  //    that sibling re-center is by design, so we only assert the filmstrip moved.)
  const fBase = await readBar(filmstrip)
  const fDir = fBase.sl < (fBase.sw - fBase.cw) / 2 ? 1 : -1
  await wheelOver(page, filmstrip, fDir * 600)
  const fAfter = await readBar(filmstrip)
  const tAfter = await readBar(timeline)
  console.log('[routing] after wheel over filmstrip: filmstrip', fAfter, 'timeline', tAfter, '(timeline follows shared cursor)')
  assert.ok(Math.abs(fAfter.sl - fBase.sl) > 100, `wheel panned the filmstrip (${fBase.sl} → ${fAfter.sl})`)

  // 5) PLAYING. Seek the playhead into the EARLY part of the day and pin the scroll
  //    left, so playback advances FORWARD (no newest→oldest wrap) and stays near the
  //    left edge (target ≈ 0) for the whole measurement — deterministic.
  await wheelOver(page, timeline, -6000) // pin scroll to the left edge
  const tlBox = await timeline.boundingBox()
  await page.mouse.click(tlBox.x + 60, tlBox.y + tlBox.height / 2) // seek near the oldest frame
  await page.waitForTimeout(200)
  await page.click('button[title="Play"]')
  assert.ok(await rw.locator('button[title="Pause"]').count(), 'playback engaged (Pause button shown)')

  // 5a) Prove playback is LIVE and big offsets still follow the playhead: a LARGE pan
  //     (past the tolerance) snaps back toward the playhead within a couple of ticks.
  //     If playback were frozen the cursor wouldn't change and this would NOT re-center.
  await wheelOver(page, timeline, 700) // pan far right, well past a quarter-viewport
  const big1 = await readBar(timeline)
  await page.waitForTimeout(1600) // ~2 ticks
  const big2 = await readBar(timeline)
  console.log(`[playing] large pan ${big1.sl} → after 1.6s ${big2.sl} (should snap back toward the playhead)`)
  assert.ok(big1.sl > 400, 'the large wheel actually panned the bar far from the playhead')
  assert.ok(big2.sl < big1.sl / 2, `playback re-centered a far pan (live playback + follow): ${big1.sl} → ${big2.sl}`)

  // 5b) THE FIX: a SMALL pan (within a quarter-viewport of the playhead) STAYS put across
  //     several ticks. The old unconditional re-center snapped it back to center every
  //     700ms, so the bar felt un-scrollable while playing.
  const q0 = await readBar(timeline)
  const panDelta = Math.max(90, Math.min(150, Math.round(q0.cw / 4) - 40))
  await wheelOver(page, timeline, panDelta) // small pan right, within tolerance
  const q1 = await readBar(timeline)
  console.log(`[playing] small pan by ${panDelta}: ${q0.sl} → ${q1.sl} (cw=${q0.cw})`)
  assert.ok(Math.abs(q1.sl - q0.sl) > 40, 'the small wheel actually panned while playing')
  await page.waitForTimeout(2300) // ~3 playback ticks
  const q2 = await readBar(timeline)
  console.log(`[playing] 2.3s later: ${q2.sl} (stayed near ${q1.sl}? old code would snap toward ${q0.sl})`)
  await page.screenshot({ path: path.join(shotsDir, '02-playing-stayed.png') })
  assert.ok(
    Math.abs(q2.sl - q1.sl) < panDelta * 0.5,
    `playing small pan stayed put (q1=${q1.sl} → q2=${q2.sl}); would have snapped toward ${q0.sl} without the tolerance guard`
  )
  await page.click('button[title="Pause"]').catch(() => {})

  console.log('[PASS] timeline overflow + wheel pan + routing + play-no-yank all verified')
})
