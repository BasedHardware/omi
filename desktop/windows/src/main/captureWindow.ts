// The hidden, always-alive capture window. It loads the renderer at the
// `#/capture` hash route and owns ALL capture — continuous mic, system-audio
// loopback, screen-session audio, push-to-talk (warm mic + pre-roll), and Rewind
// frame capture. UI windows are pure UI; they drive capture over the capture
// bridge (see ipc/captureBridge.ts). Kept alive for the app lifetime so capture
// never depends on a UI window being open, and recreated (within a budget) if it
// ever dies, so a renderer crash can't silently stop recording.
import { BrowserWindow } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { rendererBaseUrl } from './rendererServer'
import { isQuitting } from './lifecycle'
import { emitCaptureEventFromMain } from './ipc/captureBridge'

let captureWindow: BrowserWindow | null = null
// Timestamps of recent (re)spawns, used to bound the crash-loop respawn rate.
let spawnTimes: number[] = []
// The capture window's first load is startup, not a recreate/reload — only
// LATER loads (crash reload, or a recreated window) should tell UI windows to
// re-issue their standing capture commands.
let firstEverLoad = true

const RESPAWN_WINDOW_MS = 60_000
const RESPAWN_MAX = 3
const RESPAWN_DELAY_MS = 300

export function getCaptureWindow(): BrowserWindow | null {
  return captureWindow
}

export function getCaptureWc(): Electron.WebContents | null {
  return captureWindow && !captureWindow.isDestroyed() ? captureWindow.webContents : null
}

/**
 * Decide whether to respawn a died capture window, given the recent spawn
 * timestamps and now. Pure so the crash-loop budget is unit-testable: allow a
 * respawn only if fewer than RESPAWN_MAX happened in the last RESPAWN_WINDOW_MS.
 * Returns the decision plus the pruned timestamp list to carry forward.
 */
export function decideRespawn(
  recentSpawns: number[],
  now: number
): { allow: boolean; times: number[] } {
  const times = recentSpawns.filter((t) => now - t < RESPAWN_WINDOW_MS)
  return { allow: times.length < RESPAWN_MAX, times }
}

export function createCaptureWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 480,
    height: 320,
    show: false,
    skipTaskbar: true,
    // Never visible, but a real (offscreen) window so getUserMedia/AudioContext
    // and the Rewind <video> decode run exactly as they would in a UI window.
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // webSecurity stays ON (default). The capture window talks to the Omi API
      // only through the main-process WebSocket (omi-listen:*), so it never needs
      // the CORS workaround the UI windows historically used.
      // Keep audio/screen capture running at full rate while hidden — the whole
      // point of this window is background capture.
      backgroundThrottling: false
    }
  })

  win.on('closed', () => {
    const wasCapture = captureWindow === win
    captureWindow = null
    if (!wasCapture || isQuitting()) return
    const now = Date.now()
    const { allow, times } = decideRespawn(spawnTimes, now)
    if (!allow) {
      console.error(
        `[capture] window died ${RESPAWN_MAX}+ times in ${RESPAWN_WINDOW_MS / 1000}s — not respawning (capture is stopped until relaunch)`
      )
      spawnTimes = times
      return
    }
    spawnTimes = [...times, now]
    console.warn('[capture] window closed unexpectedly — respawning')
    setTimeout(() => {
      if (!isQuitting()) createCaptureWindow()
    }, RESPAWN_DELAY_MS)
  })

  // On every load AFTER the first-ever one (crash reload, or a freshly recreated
  // window), tell UI windows the capture window restarted so they re-issue their
  // standing commands (live-view, screen-view). An in-flight PTT is abandoned.
  win.webContents.on('did-finish-load', () => {
    if (firstEverLoad) {
      firstEverLoad = false
      return
    }
    emitCaptureEventFromMain({ type: 'capture-window-restarted' }, win.webContents.id)
  })

  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[capture] did-fail-load', code, desc, url)
  )

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#/capture`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/index.html#/capture`)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'), { hash: 'capture' })
  }

  captureWindow = win
  return win
}
