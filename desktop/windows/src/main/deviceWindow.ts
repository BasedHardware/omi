// The hidden device window: the renderer that owns WebBluetooth. Chromium's BLE
// stack (scanning, GATT, notifications) is only reachable from a renderer, and a
// wearable must keep streaming while every UI window is closed, so the device
// lives here for the app lifetime exactly like the capture window. UI windows
// drive it over the device bridge (see ipc/deviceBridge.ts).
import { BrowserWindow } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import iconPath from '../../resources/icon.png?asset'
import { rendererBaseUrl } from './rendererServer'
import { isQuitting } from './lifecycle'
import { emitDeviceEventFromMain } from './ipc/deviceBridge'
import { killSessionsForOwner } from './ipc/omiListen'

let deviceWindow: BrowserWindow | null = null
let spawnTimes: number[] = []
let firstWindowCreated = false
// Per-window wiring (the Bluetooth chooser handler) supplied by main. It lives
// on the webContents, so a respawned window must be wired again or pairing has
// nothing to answer requestDevice() with.
let onWindowCreated: ((win: BrowserWindow) => void) | null = null

export function setDeviceWindowWiring(wire: (win: BrowserWindow) => void): void {
  onWindowCreated = wire
}

const RESPAWN_WINDOW_MS = 60_000
const RESPAWN_MAX = 3
const RESPAWN_DELAY_MS = 300

export function getDeviceWindow(): BrowserWindow | null {
  return deviceWindow
}

export function getDeviceWc(): Electron.WebContents | null {
  return deviceWindow && !deviceWindow.isDestroyed() ? deviceWindow.webContents : null
}

/**
 * Whether a died device window should be respawned: allowed only if fewer than
 * RESPAWN_MAX respawns happened in the last RESPAWN_WINDOW_MS. Pure so the
 * crash-loop budget is testable, matching the capture window's contract.
 */
export function decideDeviceRespawn(
  recentSpawns: number[],
  now: number
): { allow: boolean; times: number[] } {
  const times = recentSpawns.filter((t) => now - t < RESPAWN_WINDOW_MS)
  return { allow: times.length < RESPAWN_MAX, times }
}

export function createDeviceWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 480,
    height: 320,
    show: false,
    skipTaskbar: true,
    icon: iconPath,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      // A throttled renderer would stall GATT notification delivery, which is
      // the entire job of this window.
      backgroundThrottling: false
    }
  })

  win.on('closed', () => {
    const wasDevice = deviceWindow === win
    // Only drop the reference when the CURRENT host closed: an older window
    // closing after a replacement was installed must not orphan the new one.
    if (wasDevice) deviceWindow = null
    if (!wasDevice || isQuitting()) return
    // Its listen session would otherwise linger as an open WebSocket.
    killSessionsForOwner(win.webContents.id)
    const now = Date.now()
    const { allow, times } = decideDeviceRespawn(spawnTimes, now)
    if (!allow) {
      console.error(
        `[device] window died ${RESPAWN_MAX}+ times in ${RESPAWN_WINDOW_MS / 1000}s — not respawning (the wearable stays disconnected until relaunch)`
      )
      spawnTimes = times
      return
    }
    spawnTimes = [...times, now]
    console.warn('[device] window closed unexpectedly — respawning')
    setTimeout(() => {
      if (isQuitting()) return
      // A device command may have recreated the host during the delay; a second
      // one would leave two renderers owning WebBluetooth.
      const current = getDeviceWindow()
      if (current && !current.isDestroyed()) return
      createDeviceWindow()
    }, RESPAWN_DELAY_MS)
  })

  // Every load after the first window's initial load means a restart, so UI
  // windows must re-issue standing commands and the device must reconnect.
  const isFirstWindow = !firstWindowCreated
  firstWindowCreated = true
  let announcedFirstLoad = false
  win.webContents.on('did-finish-load', () => {
    if (isFirstWindow && !announcedFirstLoad) {
      announcedFirstLoad = true
      return
    }
    emitDeviceEventFromMain({ type: 'device-window-restarted' }, win.webContents.id)
  })

  win.webContents.on('did-fail-load', (_e, code, desc, url) =>
    console.error('[device] did-fail-load', code, desc, url)
  )

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/device.html#/device`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/device.html#/device`)
  } else {
    win.loadFile(join(__dirname, '../renderer/device.html'), { hash: 'device' })
  }

  deviceWindow = win
  // Wire the new webContents (chooser handler) before it can service a command.
  onWindowCreated?.(win)
  return win
}
