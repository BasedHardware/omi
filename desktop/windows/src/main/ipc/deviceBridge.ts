import { ipcMain, BrowserWindow, type WebContents } from 'electron'
import type { DeviceCommand, DeviceEvent } from '../../shared/types'

// Bridges the hidden device window (which owns WebBluetooth) and the UI
// windows. Two channels, mirroring the capture bridge:
//   'omi-device:cmd'   — a UI window sends a DeviceCommand; main forwards it to
//                        the device window after checking the sender is allowed
//                        to issue it.
//   'omi-device:event' — the device window emits a DeviceEvent; main accepts it
//                        ONLY from the device window (spoof guard) and fans it
//                        out to the UI windows that render device state.
// Pairing, connecting and forgetting a device are main-UI decisions, so an
// auxiliary renderer (toast, glow, overlay) can never unpair someone's device
// or start a Bluetooth scan.

const MAIN_ONLY_COMMANDS = new Set<DeviceCommand['type']>([
  'device-pair',
  'device-pair-cancel',
  'device-pair-select',
  'device-connect',
  'device-disconnect',
  'device-forget',
  'device-request-state',
  // Recovery moves audio off the device and deletes the device's copy, so it
  // belongs to the same set as unpairing rather than to any auxiliary window.
  'device-storage-recover',
  'device-storage-cancel'
])

/**
 * Whether a renderer may issue this device command. Pairing and lifecycle
 * commands come from the main window only; settings and auth pushes originate
 * in main itself (senderId undefined). Pure for testability.
 */
export function canForwardRendererDeviceCommand(
  command: DeviceCommand,
  senderId: number,
  mainWindowId?: number
): boolean {
  if (MAIN_ONLY_COMMANDS.has(command.type)) return senderId === mainWindowId
  switch (command.type) {
    // Settings and sign-in changes are pushed by main, but the main window may
    // also forward them right after the user edits them.
    case 'device-settings':
    case 'auth-changed':
      return senderId === mainWindowId
    default:
      return false
  }
}

// Main-process taps on device events (post spoof-guard) so tray, toasts and the
// reconnect policy can observe device state without a BrowserWindow. Listeners
// must never throw.
const mainEventListeners = new Set<(event: DeviceEvent) => void>()

export function onDeviceEventInMain(cb: (event: DeviceEvent) => void): () => void {
  mainEventListeners.add(cb)
  return () => mainEventListeners.delete(cb)
}

function notifyMainEventListeners(event: DeviceEvent): void {
  for (const cb of mainEventListeners) {
    try {
      cb(event)
    } catch (err) {
      console.warn('[device] main event listener threw:', err)
    }
  }
}

/**
 * Emit a device event that ORIGINATES in main (window restarted, chooser
 * candidates) to every window except the device window itself.
 */
export function emitDeviceEventFromMain(event: DeviceEvent, deviceWcId: number | null): void {
  notifyMainEventListeners(event)
  for (const w of BrowserWindow.getAllWindows()) {
    if (w.isDestroyed() || w.webContents.id === deviceWcId) continue
    w.webContents.send('omi-device:event', event)
  }
}

// Commands issued before the device host is ready. A window created on demand
// (the user just hit "Pair") is still loading when the pair command arrives, and
// webContents.send on an unloaded page is dropped silently, so the command waits
// here until the host announces itself.
let pendingCommands: DeviceCommand[] = []
let hostReady = false
const PENDING_COMMANDS_MAX = 16

/** Called when the device host mounts (or when its window dies). */
export function setDeviceHostReady(ready: boolean, getDeviceWc: () => WebContents | null): void {
  hostReady = ready
  if (!ready) return
  const queued = pendingCommands
  pendingCommands = []
  const wc = getDeviceWc()
  if (!wc || wc.isDestroyed()) return
  for (const cmd of queued) wc.send('omi-device:cmd', { cmd })
}

/** Send a command to the device window from main (settings pushes, reconnect). */
export function sendDeviceCommandFromMain(
  getDeviceWc: () => WebContents | null,
  command: DeviceCommand
): void {
  const wc = getDeviceWc()
  if (!wc || wc.isDestroyed() || !hostReady) {
    // Bounded: a host that never comes up must not accumulate commands forever.
    pendingCommands = [...pendingCommands, command].slice(-PENDING_COMMANDS_MAX)
    return
  }
  wc.send('omi-device:cmd', { cmd: command })
}

/**
 * Wire the device bridge. `getDeviceWc` is read live on every message so a
 * respawned device window is picked up automatically.
 */
export function registerDeviceBridge(
  getDeviceWc: () => WebContents | null,
  getMainWc: () => WebContents | null,
  /** Creates the device window if it does not exist yet; most users never pair
   *  a wearable, so the window is not spawned until one is needed. */
  ensureDeviceWindow: () => void
): void {
  ipcMain.on('omi-device:cmd', (e, cmd: DeviceCommand) => {
    if (!cmd || typeof cmd !== 'object' || typeof cmd.type !== 'string') return
    const mainWc = getMainWc()
    const mainWindowId = mainWc && !mainWc.isDestroyed() ? mainWc.id : undefined
    if (!canForwardRendererDeviceCommand(cmd, e.sender.id, mainWindowId)) {
      console.warn('[device] rejected unauthorized command:', cmd.type)
      return
    }
    ensureDeviceWindow()
    sendDeviceCommandFromMain(getDeviceWc, cmd)
  })

  ipcMain.on('omi-device:event', (e, event: DeviceEvent) => {
    const wc = getDeviceWc()
    // Spoof guard: only the device window may report device state. Without it a
    // compromised UI window could forge a pairing or a battery reading.
    if (!wc || wc.isDestroyed() || e.sender.id !== wc.id) return
    if (!event || typeof event !== 'object' || typeof event.type !== 'string') return
    if (event.type === 'device-ready') setDeviceHostReady(true, getDeviceWc)
    notifyMainEventListeners(event)
    for (const w of BrowserWindow.getAllWindows()) {
      if (w.isDestroyed() || w.webContents.id === wc.id) continue
      w.webContents.send('omi-device:event', event)
    }
  })
}
