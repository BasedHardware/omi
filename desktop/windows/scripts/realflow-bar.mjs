// Full real-production open flow in the sandbox: REAL summon (handleSummonPress)
// → pill entrance → REAL pill DOM click → expand. Records .bar-slide/.bar-surface
// translateY throughout AND a CDP screencast, so we see exactly what the user's
// "open a chat" looks like (and whether the WHOLE surface drops via translateY).
import { _electron as electron } from 'playwright'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const mainEntry = path.join(root, 'out', 'main', 'index.js')
const OUT = process.env.OUT || path.join(root, '.orb-out', 'bar-realflow')
mkdirSync(OUT, { recursive: true })
const env = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function findBar(app) {
  for (let i = 0; i < 100; i++) {
    const p = (await app.windows()).find((w) => w.url().includes('#/bar')) ?? null
    if (p) return p
    await sleep(100)
  }
  throw new Error('no bar page')
}
const tyOf = (m) => {
  if (!m || m === 'none') return 0
  const g = m.match(/matrix\(([^)]+)\)/)
  return g ? parseFloat(g[1].split(',')[5]) : 0
}

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-realflow-'))
  const app = await electron.launch({ args: [mainEntry, `--user-data-dir=${dir}`], env })
  try {
    await app.firstWindow()
    // Hold peek open so the retract watchdog can't hide the pill before we click.
    await app.evaluate(() => globalThis.__omiE2E.barHoldPeekOpen(true))
    const page = await findBar(app)
    const client = await page.context().newCDPSession(page)

    // Continuous translateY sampler on .bar-slide + .bar-surface.
    await page.evaluate(() => {
      const rec = []
      window.__rec = rec
      const t0 = performance.now()
      const tick = () => {
        const t = Math.round(performance.now() - t0)
        for (const sel of ['.bar-slide', '.bar-surface']) {
          const el = document.querySelector(sel)
          if (el) {
            const cs = getComputedStyle(el)
            rec.push({ t, sel, tf: cs.transform, op: cs.opacity })
          }
        }
        requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    })

    // Screencast the whole flow.
    const frames = []
    const tc0 = Date.now()
    client.on('Page.screencastFrame', async (p) => {
      frames.push({ t: Date.now() - tc0, data: p.data })
      try {
        await client.send('Page.screencastFrameAck', { sessionId: p.sessionId })
      } catch {
        /* stopped */
      }
    })
    await client.send('Page.startScreencast', { format: 'jpeg', quality: 80, everyNthFrame: 1 })

    // 1) REAL summon (the production hotkey path).
    await app.evaluate(() => globalThis.__omiE2E.barSummonFire())
    // Wait until visible + settle the pill entrance.
    for (let i = 0; i < 60; i++) {
      if ((await app.evaluate(() => globalThis.__omiE2E.barState())).visible) break
      await sleep(50)
    }
    await sleep(650)
    // 2) REAL pill click → expand.
    await page.locator('.bar-content[role="button"]').click()
    await sleep(700)

    await client.send('Page.stopScreencast')
    const rec = await page.evaluate(() => window.__rec)

    // Report translateY + scale + opacity ranges per element across the whole
    // flow. After the entrance grow fix, .bar-slide translateY span must be ~0
    // (no drop); the reveal shows up as scale 0.7→1 + opacity 0→1 instead.
    const scaleOf = (m) => {
      if (!m || m === 'none') return 1
      const g = m.match(/matrix\(([^)]+)\)/)
      return g ? parseFloat(g[1].split(',')[0]) : 1
    }
    for (const sel of ['.bar-slide', '.bar-surface']) {
      const rows = rec.filter((r) => r.sel === sel)
      const tys = rows.map((r) => tyOf(r.tf))
      const scs = rows.map((r) => scaleOf(r.tf))
      const ops = rows.map((r) => parseFloat(r.op))
      console.log(
        `${sel}: translateY span ${(Math.max(...tys) - Math.min(...tys)).toFixed(1)}px | ` +
          `scale [${Math.min(...scs).toFixed(2)}..${Math.max(...scs).toFixed(2)}] | ` +
          `opacity [${Math.min(...ops).toFixed(2)}..${Math.max(...ops).toFixed(2)}]`
      )
      // Print notable transitions (ty, scale, or opacity changing).
      let prev = null
      for (const r of rows) {
        const ty = tyOf(r.tf)
        const sc = scaleOf(r.tf)
        const op = parseFloat(r.op)
        const sig = `${ty.toFixed(0)}|${sc.toFixed(2)}|${op.toFixed(2)}`
        if (sig !== prev) {
          console.log(
            `   t=${String(r.t).padStart(4)} ty=${ty.toFixed(1)} scale=${sc.toFixed(2)} op=${op.toFixed(2)}`
          )
          prev = sig
        }
      }
    }
    // Save screencast frames.
    let i = 0
    for (const f of frames) {
      writeFileSync(
        path.join(OUT, `t${String(f.t).padStart(4, '0')}_${String(i).padStart(2, '0')}.jpg`),
        Buffer.from(f.data, 'base64')
      )
      i++
    }
    console.log(`\n${frames.length} screencast frames -> ${OUT}`)
  } finally {
    try {
      await app.close()
    } catch {
      /* ignore */
    }
    rmSync(dir, { recursive: true, force: true })
  }
}
main().catch((e) => {
  console.error(e)
  process.exit(1)
})
