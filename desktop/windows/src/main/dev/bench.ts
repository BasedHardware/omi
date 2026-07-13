// Dev-only benchmarking / sandbox machinery, quarantined out of production main.
//
// Every export is a hard no-op in packaged builds (`app.isPackaged`), and every
// call site in index.ts is behind `import.meta.env.DEV`, so electron-vite/Rollup
// drops this whole module from the packaged `out/main/index.js` bundle. Keeping
// it here — rather than inline in index.ts — is what keeps production main clean.
import { app, ipcMain, type BrowserWindow } from 'electron'
import { join } from 'path'
import { rmSync } from 'fs'
import { perfMark, flushPerfMarks } from '../../shared/perf'
import { resolveDevInstance } from '../devInstance'

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

// Pin a throwaway userData dir so parallel dev worktrees run side by side without
// clobbering the real profile's omi.db / local_kg / signed-in Firebase session.
// Each worktree gets its OWN dir, so concurrent instances never contend for the
// shared Chromium GPU/disk/quota caches (that contention crashes the WebGL brain
// map — the only GPU-backed surface — while the plain-DOM UI survives). Must run
// before any DB open (db.ts resolves userData lazily on first IPC) and before the
// single-instance lock, so distinct profiles get their own lock. Never repin in
// bench mode (the runner's --user-data-dir must win) or in a packaged build.
//
// Two ways a profile is chosen:
//   • Explicit OMI_SANDBOX=<name> (opt-in): names the profile. OMI_SANDBOX=1 keeps
//     the legacy shared "…-sandbox-chat-kg" profile.
//   • Otherwise, a LINKED git worktree auto-isolates to a profile named after its
//     folder. The PRIMARY checkout resolves to isPrimary and stays on the DEFAULT
//     profile (the real data + Firebase session + onboarding floor live there, so
//     the main flow is unchanged). Auto-isolation is safe now that fresh worktree
//     profiles are populated on demand by `pnpm seed:auth` (scripts/seed-auth.mjs)
//     — earlier the auto-derive blanked the onboarding floor because nothing
//     re-seeded the new profile; the seed step is what makes it safe. Force the
//     default profile from a linked worktree with OMI_INSTANCE=primary.
export function applySandboxUserDataOverride(): void {
  if (app.isPackaged) return
  if (process.env.OMI_BENCH === '1') return
  const explicit = process.env.OMI_SANDBOX
  let suffix: string | null = null
  if (explicit) {
    suffix = explicit === '1' ? 'chat-kg' : explicit.replace(/[^a-zA-Z0-9._-]/g, '-')
  } else if (!hasCliSwitch('user-data-dir')) {
    // A caller that pinned --user-data-dir (E2E / soak harness) owns the profile;
    // never override it. Otherwise auto-isolate a linked worktree.
    const instance = resolveDevInstance()
    if (!instance.isPrimary) suffix = instance.name
  }
  if (suffix) {
    app.setPath('userData', join(app.getPath('appData'), `omi-windows-sandbox-${suffix}`))
  }
}

/** True if `--<name>` (or `--<name>=…`) is present on the process command line. */
function hasCliSwitch(name: string): boolean {
  return process.argv.some((a) => a === `--${name}` || a.startsWith(`--${name}=`))
}

// Append the dev instance's title suffix (e.g. " — multi-worktree-dev") to the
// native window title so overlapping worktree windows are tellable apart in the
// taskbar / Alt-Tab. Re-applies on every renderer title update. No-op on the
// primary checkout (empty suffix) and in packaged builds.
export function applyDevWindowTitleSuffix(win: BrowserWindow): void {
  if (app.isPackaged) return
  const suffix = resolveDevInstance().titleSuffix
  if (!suffix) return
  const withSuffix = (base: string): string =>
    (base.endsWith(suffix) ? base.slice(0, -suffix.length) : base) + suffix
  win.setTitle(withSuffix(win.getTitle()))
  win.webContents.on('page-title-updated', (e, title) => {
    e.preventDefault()
    win.setTitle(withSuffix(title))
  })
}

// --- Dev GPU stability ------------------------------------------------------
// The app's only GPU-backed surfaces (the WebGL orb + brain map, backdrop blur,
// smooth compositing) all ride Chromium's GPU process. On dev / automated runs —
// hybrid-GPU laptops, an asleep display, headless soak — hardware WebGL
// (ANGLE→D3D11) destabilises and the GPU process crashes. A dead context makes
// the orb's shader "compile" fail (getShaderInfoLog === null), and Chromium then
// BLOCKS 3D APIs per-origin "until restart". Within one instance's origin +
// userData profile that block, plus a corrupt GPU disk cache, PERSIST across
// launches and break every GPU surface for the next run — the recurring "stale"
// breakage (the primary checkout reuses localhost:5179 + the default profile every
// time; a linked worktree reuses its own derived origin + profile). In dev we
// render in SOFTWARE
// (no GPU process to crash) while keeping WebGL alive on SwiftShader, and stop
// the per-origin 3D block so a crash can never permanently blocklist WebGL. Opt
// back into hardware with OMI_DEV_HW_GPU=1 (interactive perf on a healthy
// display). Packaged builds are never touched — they keep full hardware
// acceleration. Must run before the app is ready.
export function applyDevGpuStability(): void {
  if (app.isPackaged) return
  // Headless CDP endpoint (WebGL/GPU state, console, network) — also what powers
  // cross-instance auth seeding (scripts/seed-auth.mjs). Default the port to THIS
  // instance's derived CDP port so every dev instance is reachable and two
  // instances never share one port; OMI_DEV_REMOTE_DEBUG pins an explicit port,
  // OMI_DEV_NO_REMOTE_DEBUG=1 turns it off. Localhost-only and dev-only (packaged
  // builds return above, so the port never opens in production).
  if (process.env.OMI_DEV_NO_REMOTE_DEBUG !== '1' && !hasCliSwitch('remote-debugging-port')) {
    // resolveDevInstance().cdpPort already folds in OMI_DEV_REMOTE_DEBUG >
    // OMI_DEV_CDP_PORT > derived (see computeDevInstance), so the app, the seed
    // script, and `pnpm dev:instance` all agree on the port.
    app.commandLine.appendSwitch('remote-debugging-port', String(resolveDevInstance().cdpPort))
    app.commandLine.appendSwitch('remote-allow-origins', '*')
  }
  // A GPU crash must never permanently blocklist WebGL for the shared dev origin.
  app.disableDomainBlockingFor3DAPIs()
  if (process.env.OMI_DEV_HW_GPU === '1') return
  // Software compositing: the GPU process can't crash the UI…
  app.disableHardwareAcceleration()
  // …and pin GL to ANGLE's SwiftShader (CPU) so WebGL keeps working. Explicit
  // because disableHardwareAcceleration() alone doesn't reliably force the CPU
  // path on Windows (electron#50469); enable-unsafe-swiftshader is required since
  // Chromium removed the silent SwiftShader fallback for WebGL. Use the FULL
  // 'swiftshader' backend, NOT 'swiftshader-webgl': the -webgl variant leaves the
  // compositor on hardware D3D11, whose crashes take down the entire GPU process
  // (and every live WebGL context with it) — the exact instability we're killing.
  app.commandLine.appendSwitch('use-gl', 'angle')
  app.commandLine.appendSwitch('use-angle', 'swiftshader')
  app.commandLine.appendSwitch('enable-unsafe-swiftshader')
  // Never persist a GPU shader cache in dev — a force-killed build corrupts it and
  // the corruption poisons the next launch's WebGL (belt with clearStaleGpuCaches).
  app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')
}

// Wipe Chromium's GPU/shader disk caches for the resolved userData profile before
// the GPU process opens them. Dev builds get force-killed constantly (every
// restart / kill), which corrupts these caches, and the corruption poisons the
// next launch's WebGL. Preserves Local Storage / IndexedDB (sign-in + chat
// history). Must run AFTER any OMI_SANDBOX repin so it targets the live profile.
export function clearStaleGpuCaches(): void {
  if (app.isPackaged) return
  const ud = app.getPath('userData')
  const caches = [
    'GPUCache',
    'GrShaderCache',
    'ShaderCache',
    'DawnCache',
    'DawnGraphiteCache',
    'DawnWebGPUCache'
  ]
  for (const name of caches) {
    try {
      rmSync(join(ud, name), { recursive: true, force: true })
    } catch {
      /* best-effort — a locked cache dir must never block startup */
    }
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
