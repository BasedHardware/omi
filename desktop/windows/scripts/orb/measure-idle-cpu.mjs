// Orb/bar idle-cost measurement: launches the REAL built app (hermetic,
// throwaway profile), reveals the bar in peek (orb animating at its 30fps idle
// throttle), and samples app.getAppMetrics() for N minutes. Reports mean/max
// CPU for the bar renderer process specifically and the app total.
// Run: node scripts/orb/measure-idle-cpu.mjs [minutes=10]
// (build first: npx electron-vite build)
import { _electron as electron } from 'playwright'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const minutes = Number(process.argv[2] ?? 10)
const SAMPLE_MS = 5000

async function main() {
  const dir = mkdtempSync(path.join(tmpdir(), 'omi-cpu-'))
  const app = await electron.launch({
    args: [path.join(root, 'out', 'main', 'index.js'), `--user-data-dir=${dir}`],
    env: { ...process.env, OMI_E2E: '1', OMI_AUTOMATION: '0', OMI_SKIP_TUNNEL: '1' }
  })
  try {
    await app.firstWindow()
    // Reveal the bar (peek) and wait for it to settle at the idle throttle.
    await app.evaluate(() => globalThis.__omiE2E.barShow('peek'))
    for (let i = 0; i < 100; i++) {
      const s = await app.evaluate(() => globalThis.__omiE2E.barState())
      if (s.visible) break
      await new Promise((r) => setTimeout(r, 100))
    }
    const barPid = await app.evaluate(({ BrowserWindow }) => {
      const s = globalThis.__omiE2E.barState()
      const win = BrowserWindow.fromId(s.id)
      return win ? win.webContents.getOSProcessId() : null
    })
    console.log(`[idle-cpu] sampling ${minutes}min (bar renderer pid ${barPid})…`)
    // Prime the differential CPU counters.
    await app.evaluate(({ app }) => void app.getAppMetrics())
    await new Promise((r) => setTimeout(r, SAMPLE_MS))

    const samples = []
    const n = Math.round((minutes * 60000) / SAMPLE_MS)
    for (let i = 0; i < n; i++) {
      const m = await app.evaluate(({ app }) =>
        app.getAppMetrics().map((p) => ({ pid: p.pid, type: p.type, cpu: p.cpu.percentCPUUsage }))
      )
      const bar = m.find((p) => p.pid === barPid)?.cpu ?? 0
      const total = m.reduce((a, p) => a + p.cpu, 0)
      samples.push({ bar, total })
      if (i % 12 === 0) {
        console.log(
          `[idle-cpu] ${((i * SAMPLE_MS) / 60000).toFixed(1)}min — bar ${bar.toFixed(2)}% total ${total.toFixed(2)}%`
        )
      }
      await new Promise((r) => setTimeout(r, SAMPLE_MS))
    }
    const mean = (k) => samples.reduce((a, s) => a + s[k], 0) / samples.length
    const max = (k) => Math.max(...samples.map((s) => s[k]))
    console.log(
      `[idle-cpu] RESULT over ${minutes}min (${samples.length} samples):\n` +
        `  bar renderer: mean ${mean('bar').toFixed(2)}% · max ${max('bar').toFixed(2)}%\n` +
        `  app total:    mean ${mean('total').toFixed(2)}% · max ${max('total').toFixed(2)}%`
    )
    const pass = mean('bar') < 1
    console.log(`[idle-cpu] ${pass ? 'PASS' : 'FAIL'} — bar renderer mean < 1% budget`)
    process.exitCode = pass ? 0 : 1
  } finally {
    try {
      await app.close()
    } catch {
      /* closed */
    }
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
