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
import iconPath from '../../resources/icon.png?asset'
import { rendererBaseUrl } from './rendererServer'
import { isQuitting } from './lifecycle'
import { emitCaptureEventFromMain } from './ipc/captureBridge'
import { killSessionsForOwner } from './ipc/omiListen'

let captureWindow: BrowserWindow | null = null
// Timestamps of recent (re)spawns, used to bound the crash-loop respawn rate.
let spawnTimes: number[] = []
// Whether any capture window has been created yet this process (the FIRST
// window's initial load is startup; everything after signals a restart).
let firstWindowCreated = false

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
    // Never shown, but set the app icon anyway so it can't surface the default
    // Electron icon in Alt-Tab/Task-Manager style listings.
    icon: iconPath,
    // Never visible, but a real (offscreen) window so getUserMedia/AudioContext
    // and the Rewind <video> decode run exactly as they would in a UI window.
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
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
    // The dead window's listen sessions would otherwise linger as open
    // WebSockets in the main process until server timeout.
    killSessionsForOwner(win.webContents.id)
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

  // On every load AFTER the first-ever WINDOW's initial load attempt (crash
  // reload, or a freshly recreated window), tell UI windows the capture window
  // restarted so they re-issue their standing commands (live-view, screen-view,
  // audio-start). Keyed to the first WINDOW, not the first successful load —
  // if the very first load fails and a respawn recovers it, consumers still
  // deserve the signal.
  const isFirstWindow = !firstWindowCreated
  firstWindowCreated = true
  let announcedFirstLoad = false
  win.webContents.on('did-finish-load', () => {
    if (isFirstWindow && !announcedFirstLoad) {
      announcedFirstLoad = true
      return
    }
    emitCaptureEventFromMain({ type: 'capture-window-restarted' }, win.webContents.id)
  })

  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[capture] did-fail-load', code, desc, url)
  )

  // Slim per-window entry (capture.html) instead of the full-app index.html — see
  // perf/win-slim-aux-windows. The `#/capture` hash is preserved so window-role
  // detection (windowRole.ts) and IPC sender labeling (voicePlaneIpc.ts) are
  // unchanged.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/capture.html#/capture`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/capture.html#/capture`)
  } else {
    win.loadFile(join(__dirname, '../renderer/capture.html'), { hash: 'capture' })
  }

  captureWindow = win
  return win
}
