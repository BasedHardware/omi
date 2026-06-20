// Auto-update against GitHub Releases (public repo andermont/omi-windows). The
// packaged build embeds an app-update.yml generated from the `publish:` block in
// electron-builder.yml; electron-updater reads it, compares versions, downloads
// the new installer in the background, and installs it on quit (or on the user's
// "Restart now"). Pure decision logic lives in updateLogic.ts so it can be tested.
import { app, dialog, BrowserWindow } from 'electron'
import { is } from '@electron-toolkit/utils'
import electronUpdater from 'electron-updater'
import { shouldCheckForUpdates } from './updateLogic'
import { showUpdateProgress, hideUpdateProgress } from './progressDialog'

const { autoUpdater } = electronUpdater

// Re-check on long-running sessions so someone who never quits still gets fixes.
const RECHECK_INTERVAL_MS = 6 * 60 * 60 * 1000

let wired = false
// The version we've already shown the "Update available" prompt for, so the 6h
// recheck doesn't re-nag mid-session.
let promptedVersion: string | null = null

// ── Shared update UI ────────────────────────────────────────────────────────
// The native dialogs + taskbar progress bar, factored out so the real updater
// flow and the simulateUpdateUi() smoke test drive the identical UI.

// Download progress: an on-screen pop-up window (the live bar) PLUS the native
// Windows taskbar-icon fill. percent is 0..100.
function reportProgress(window: BrowserWindow, version: string, percent: number): void {
  if (!window.isDestroyed()) window.setProgressBar(Math.max(0, Math.min(1, percent / 100)))
  showUpdateProgress(version, percent)
}

// Hide both progress indicators (download finished / cancelled / errored).
function clearProgress(window: BrowserWindow): void {
  if (!window.isDestroyed()) window.setProgressBar(-1)
  hideUpdateProgress()
}

/** Native "Omi X is available — Download / Later". Resolves true if Download. */
function promptDownload(window: BrowserWindow, version: string): Promise<boolean> {
  return dialog
    .showMessageBox(window, {
      type: 'info',
      buttons: ['Download', 'Later'],
      defaultId: 0,
      cancelId: 1,
      title: 'Update available',
      message: `Omi ${version} is available.`,
      detail:
        'Download it now? You can keep using Omi while it downloads — a progress bar shows on the taskbar — and you’ll be asked to restart when it’s ready.'
    })
    .then(({ response }) => response === 0)
    .catch(() => false)
}

/** Native "Omi X downloaded — Restart now / Later". Resolves true if Restart. */
function promptRestart(window: BrowserWindow, version: string): Promise<boolean> {
  return dialog
    .showMessageBox(window, {
      type: 'info',
      buttons: ['Restart now', 'Later'],
      defaultId: 0,
      cancelId: 1,
      title: 'Update ready',
      message: `Omi ${version} has been downloaded.`,
      detail: 'Restart to apply it now, or it will install automatically next time you quit Omi.'
    })
    .then(({ response }) => response === 0)
    .catch(() => false)
}

/**
 * UI smoke test: walk the full update experience (available dialog → animated
 * taskbar progress → restart dialog) with a fake version and synthetic progress,
 * touching no network and never installing. Triggered by OMI_SIMULATE_UPDATE=1 so
 * the dialogs/progress bar can be exercised in `pnpm dev` without publishing a
 * release. Runs regardless of dev/packaged (it's opt-in via the env var).
 */
export async function simulateUpdateUi(window: BrowserWindow, version = '9.9.9'): Promise<void> {
  console.log('[autoUpdate] SIMULATION: update-UI smoke test for', version)
  const accepted = await promptDownload(window, version)
  if (!accepted) {
    console.log('[autoUpdate] SIMULATION: user chose Later')
    return
  }
  // Animate 0 → 100% over ~8s on the native taskbar bar (slow enough to clearly
  // watch the Omi taskbar icon fill).
  await new Promise<void>((resolve) => {
    let pct = 0
    const id = setInterval(() => {
      pct = Math.min(pct + 4, 100)
      reportProgress(window, version, pct)
      if (pct >= 100) {
        clearInterval(id)
        resolve()
      }
    }, 320)
  })
  clearProgress(window)
  const restart = await promptRestart(window, version)
  await dialog
    .showMessageBox(window, {
      type: 'info',
      buttons: ['OK'],
      title: 'Update simulation complete',
      message: restart ? 'You chose “Restart now”.' : 'You chose “Later”.',
      detail: 'UI smoke test (OMI_SIMULATE_UPDATE) — no real update was downloaded or installed.'
    })
    .catch(() => {})
}

/**
 * Wire up background auto-update. Safe to call once the main window exists; it
 * no-ops in dev / unpacked / bench so day-to-day development is unaffected.
 */
export function initAutoUpdate(window: BrowserWindow): void {
  if (wired) return
  if (
    !shouldCheckForUpdates({
      isDev: is.dev,
      isPackaged: app.isPackaged,
      isBench: process.env.OMI_BENCH === '1'
    })
  ) {
    return
  }
  wired = true

  // Don't download until the user opts in via the native prompt below.
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('error', (err) => {
    // Never surface updater failures to the user — a missing release, no network,
    // or a rate-limited GitHub API should just leave them on the current version.
    clearProgress(window) // clear any stuck bar
    console.warn('[autoUpdate] error:', err?.message ?? err)
  })

  // Ask the user (native dialog) before downloading, so they decide when to take
  // the sizable download instead of it happening silently. Guard against the 6h
  // recheck re-prompting the same version within a session.
  autoUpdater.on('update-available', (info) => {
    console.log('[autoUpdate] update available:', info.version)
    if (window.isDestroyed() || promptedVersion === info.version) return
    promptedVersion = info.version
    void promptDownload(window, info.version).then((accepted) => {
      if (accepted) {
        reportProgress(window, info.version, 0) // show the pop-up immediately
        autoUpdater.downloadUpdate().catch((err) => {
          clearProgress(window)
          console.warn('[autoUpdate] download failed:', err?.message ?? err)
        })
      } else {
        promptedVersion = null // declined — re-offer on the next launch
      }
    })
  })

  // Pop-up + taskbar progress while the chosen update downloads.
  autoUpdater.on('download-progress', (p) => {
    reportProgress(window, promptedVersion ?? '', p.percent ?? 0)
  })
  autoUpdater.on('update-not-available', () => {
    console.log('[autoUpdate] already up to date')
  })
  autoUpdater.on('update-downloaded', (info) => {
    if (window.isDestroyed()) return // window gone — install on the next quit
    clearProgress(window) // download finished — clear the bars
    void promptRestart(window, info.version).then((restart) => {
      // quitAndInstall(isSilent=true, isForceRunAfter=true): apply the update
      // SILENTLY (runs the assisted installer with /S, no wizard, reusing the
      // existing install dir) and relaunch into the new version. If they chose
      // "Later", autoInstallOnAppQuit installs it on the next quit instead.
      if (restart) autoUpdater.quitAndInstall(true, true)
    })
  })

  // Check only — the download starts after the user accepts the prompt above.
  autoUpdater.checkForUpdates().catch((err) => {
    console.warn('[autoUpdate] check failed:', err?.message ?? err)
  })

  const timer = setInterval(() => {
    autoUpdater.checkForUpdates().catch(() => {})
  }, RECHECK_INTERVAL_MS)
  // Don't let the recheck timer keep the process alive on quit.
  timer.unref?.()
}
