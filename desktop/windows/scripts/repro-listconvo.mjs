// Reproduce the list→conversation "plummet" with a TALL conversation (the real
// app has chat history; fake-auth harness was empty → missed it). Injects chat
// state via the real 'chat:state' IPC from the Electron main context (no main
// code change), expands the bar, then measures + screencasts BOTH directions:
//   ENTER: click the "Omi Chat" row  (list → conversation) — the plummet
//   BACK:  click the back chevron     (conversation → list) — the liked deflate
// Per frame it logs .bar-surface rect and the active view-root rect/transform/
// opacity, so we catch exactly what animates (a translateY drop? a box grow with
// top-anchored content? a keyframe?).
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const OUT = process.env.OUT || path.join(root, '.orb-out', 'listconvo')
mkdirSync(OUT, { recursive: true })
const env = { ...process.env, OMI_E2E: '1', OMI_E2E_FAKE_AUTH: '1', OMI_AUTOMATION: '0', OMI_SKIP_TUNNEL: '1' }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// A tall thread so the conversation view is much taller than the 2-row list.
const MESSAGES = []
for (let i = 0; i < 6; i++) {
  MESSAGES.push({ id: `u${i}`, role: 'user', content: `Question number ${i + 1} about the project roadmap?` })
  MESSAGES.push({
    id: `a${i}`,
    role: 'assistant',
    content: `Here is a fairly detailed answer number ${i + 1} that spans a couple of lines so the conversation view is tall and scrollable, unlike the short two-row list.`
  })
}

async function findBar(app) {
  for (let i = 0; i < 100; i++) {
    const p = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
    if (p) return p
    await sleep(100)
  }
  throw new Error('no bar page')
}

async function injectChat(app, messages) {
  await app.evaluate(({ BrowserWindow }, msgs) => {
    const bar = BrowserWindow.getAllWindows().find((w) => (w.webContents.getURL() || '').includes('#/bar'))
    if (bar) bar.webContents.send('chat:state', { messages: msgs, sending: false, status: 'idle' })
  }, messages)
}

async function record(client, page, dir, label, trigger, ms) {
  mkdirSync(path.join(OUT, dir), { recursive: true })
  // Per-frame rect/transform sampler on .bar-surface + the active view root.
  await page.evaluate(() => {
    window.__s = []
    const t0 = performance.now()
    const tick = () => {
      const t = Math.round(performance.now() - t0)
      const surf = document.querySelector('.bar-surface')
      const view = document.querySelector('.bar-content-active .bar-view-enter, .bar-content-active [class*="flex flex-col"]')
      const rowRect = (el) => (el ? (({ top, height }) => ({ top: Math.round(top), height: Math.round(height) }))(el.getBoundingClientRect()) : null)
      window.__s.push({
        t,
        surf: rowRect(surf),
        surfH: surf ? getComputedStyle(surf).height : null,
        view: rowRect(view),
        viewTf: view ? getComputedStyle(view).transform : null,
        viewOp: view ? getComputedStyle(view).opacity : null,
        anims: view ? view.getAnimations().map((a) => a.animationName || a.transitionProperty).join(',') : ''
      })
      if (t < 700) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
  const frames = []
  const tc0 = Date.now()
  const onFrame = async (p) => {
    frames.push({ t: Date.now() - tc0, data: p.data })
    try { await client.send('Page.screencastFrameAck', { sessionId: p.sessionId }) } catch { /* stopped */ }
  }
  client.on('Page.screencastFrame', onFrame)
  await client.send('Page.startScreencast', { format: 'jpeg', quality: 80, everyNthFrame: 1 })
  await trigger()
  await sleep(ms)
  await client.send('Page.stopScreencast')
  client.off('Page.screencastFrame', onFrame)
  const s = await page.evaluate(() => window.__s)
  let i = 0
  for (const f of frames) {
    writeFileSync(path.join(OUT, dir, `t${String(f.t).padStart(4, '0')}_${String(i).padStart(2, '0')}.jpg`), Buffer.from(f.data, 'base64'))
    i++
  }
  console.log(`\n===== ${label} (${frames.length} frames) =====`)
  let last = ''
  for (const r of s) {
    const sig = JSON.stringify([r.surf, r.view, r.viewTf, r.viewOp])
    if (sig !== last) {
      console.log(`  t=${String(r.t).padStart(3)} surf(top=${r.surf?.top},h=${r.surf?.height}) view(top=${r.view?.top},h=${r.view?.height}) tf=${r.viewTf} op=${r.viewOp} anim=[${r.anims}]`)
      last = sig
    }
  }
}

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-lc-'))
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env })
  try {
    await app.firstWindow()
    await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
    const page = await findBar(app)
    const client = await page.context().newCDPSession(page)
    await app.evaluate((_e, m) => globalThis.__omiE2E.barShow(m), 'expanded')
    await sleep(700)
    await injectChat(app, MESSAGES)
    await sleep(400)

    // ENTER: list → conversation (click the Omi Chat row).
    await record(client, page, 'enter', 'ENTER list→conversation', async () => {
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('.bar-content-active button')].find((b) => (b.textContent || '').includes('Omi Chat'))
        btn?.click()
      })
    }, 700)
    await sleep(400)

    // BACK: conversation → list (click the back chevron, aria-label "Back to list").
    await record(client, page, 'back', 'BACK conversation→list', async () => {
      await page.evaluate(() => {
        document.querySelector('.bar-content-active button[aria-label="Back to list"]')?.click()
      })
    }, 700)

    console.log('\ndone ->', OUT)
  } finally {
    try { await app.close() } catch { /* ignore */ }
    rmSync(dir, { recursive: true, force: true })
  }
}
main().catch((e) => { console.error(e); process.exit(1) })
