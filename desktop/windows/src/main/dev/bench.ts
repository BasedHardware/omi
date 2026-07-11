// Dev-only benchmarking / sandbox machinery, quarantined out of production main.
//
// Every export is a hard no-op in packaged builds (`app.isPackaged`), and every
// call site in index.ts is behind `import.meta.env.DEV`, so electron-vite/Rollup
// drops this whole module from the packaged `out/main/index.js` bundle. Keeping
// it here — rather than inline in index.ts — is what keeps production main clean.
import { app, ipcMain, type BrowserWindow } from 'electron'
import { join } from 'path'
import { perfMark, flushPerfMarks } from '../../shared/perf'

// OMI_BENCH drives a fixed startup-timing run that quits when done; OMI_ANIM_BENCH
// records the renderer's animation-jank summary instead. Both are dev-only: a
// packaged binary never honors the env vars even if they are set.
export function isBenchMode(): boolean {
  return !app.isPackaged && process.env.OMI_BENCH === '1'
}
export function isAnimBenchMode(): boolean {
  return !app.isPackaged && process.env.OMI_ANIM_BENCH === '1'
}

// Default the perf log to userData so dev runs capture marks on disk. Packaged
// builds write nothing unless OMI_PERF_LOG is explicitly set — no silent prod
// telemetry file. Must run before the first perfMark() call.
export function applyDevPerfLogDefault(): void {
  if (app.isPackaged) return
  if (!process.env.OMI_PERF_LOG) {
    process.env.OMI_PERF_LOG = join(app.getPath('userData'), 'perf.jsonl')
  }
}

// OMI_SANDBOX pins a throwaway userData dir so parallel dev worktrees can run
// side by side without clobbering the real profile's omi.db / local_kg / signed-in
// Firebase session. Must run before any DB open (db.ts resolves userData lazily on
// first IPC) and before the single-instance lock, so distinct sandbox profiles get
// their own lock. Never repin in bench mode (the runner's --user-data-dir must win)
// and never in a packaged build.
//
// The VALUE names the profile, so concurrent worktrees each get their OWN userData
// dir and never contend for the shared Chromium GPU/disk/quota caches (that
// contention crashes the WebGL brain map — the only GPU-backed surface — while the
// plain-DOM UI survives). OMI_SANDBOX=1 keeps the legacy shared "…-sandbox-chat-kg"
// profile (no re-login). This is intentionally OPT-IN, NOT auto-derived from the
// worktree folder: the real data + Firebase session + onboarding floor live in the
// DEFAULT profile, so the MAIN worktree stays default and only SECONDARY worktrees
// set OMI_SANDBOX=<name>. (An earlier auto-derive moved a worktree off the default
// profile and blanked the brain map's onboarding floor — never do that.)
export function applySandboxUserDataOverride(): void {
  if (app.isPackaged) return
  const sandbox = process.env.OMI_SANDBOX
  if (sandbox && process.env.OMI_BENCH !== '1') {
    const suffix = sandbox === '1' ? 'chat-kg' : sandbox.replace(/[^a-zA-Z0-9._-]/g, '-')
    app.setPath('userData', join(app.getPath('appData'), `omi-windows-sandbox-${suffix}`))
  }
}

// Trivial IPC round-trip used to measure raw IPC overhead in bench mode. Gated so
// it is not a stray always-on IPC surface in production.
export function registerBenchIpc(): void {
  if (app.isPackaged) return
  ipcMain.handle('bench:echo', async (_e, x: number) => x)
}

// After the renderer loads, wait for the startup marks, flush, and quit. The
// DB/IPC workload (src/main/bench/workload.ts) was removed for the public release
// (commit dd1904d), so this now only records the startup-timing marks captured by
// the perf:mark / perf:firstPaint handlers, then flushes and quits.
export function runBenchDriver(win: BrowserWindow): void {
  if (!isBenchMode()) return
  // Resolve when the renderer reports its first painted frame, so we can be sure
  // the renderer:first-paint mark is recorded before we quit.
  const firstPaint = new Promise<void>((resolve) => {
    ipcMain.once('perf:firstPaint', () => resolve())
  })
  // Resolve when the AUTHENTICATED shell reports it has mounted+painted
  // (renderer:app-ready). Only fires when signed in + onboarded; on the
  // unauthenticated Login path it never arrives, so we keep a fallback below.
  const appReady = new Promise<void>((resolve) => {
    const onMark = (_e: unknown, name: string): void => {
      if (String(name) === 'renderer:app-ready') {
        ipcMain.off('perf:mark', onMark)
        resolve()
      }
    }
    ipcMain.on('perf:mark', onMark)
  })
  win.webContents.once('did-finish-load', async () => {
    // Animation bench: just wait for the renderer probe's jank summary, record it,
    // and quit. We deliberately DON'T run any workload here — main-thread + IPC
    // traffic during the recording window would pollute the frame-timing measure.
    if (isAnimBenchMode()) {
      await new Promise<void>((resolve) => {
        ipcMain.once('perf:animResult', (_e, stats) => {
          perfMark('anim:startup', stats as Record<string, unknown>)
          resolve()
        })
        setTimeout(resolve, 15000)
      })
      flushPerfMarks()
      app.quit()
      return
    }
    try {
      // Wait for the authed shell to be ready before finishing, so the bench
      // measures the real authed-startup path. Fall back to first-paint (an
      // unauthenticated Login run) with an 8s grace to let app-ready win, and a
      // hard 30s cap so the bench always completes.
      await Promise.race([
        appReady,
        firstPaint.then(() => new Promise((r) => setTimeout(r, 8000))),
        new Promise((r) => setTimeout(r, 30000))
      ])
    } catch (e) {
      console.error('[bench] driver failed:', e)
    } finally {
      flushPerfMarks()
      app.quit()
    }
  })
}
