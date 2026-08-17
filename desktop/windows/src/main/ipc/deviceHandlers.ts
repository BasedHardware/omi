import { ipcMain, type WebContents } from 'electron'
import type {
  DeviceSettings,
  WearableDeviceCandidate,
  WearableDeviceInfo
} from '../../shared/types'
import { getAppSettings, setAppSettings } from '../appSettings'
import { emitDeviceEventFromMain, sendDeviceCommandFromMain } from './deviceBridge'

// Device settings + the Bluetooth chooser live in main because a wearable must
// reconnect with no UI window open, and because Chromium routes device
// selection through the main process: `navigator.bluetooth.requestDevice()` in
// the device window fires 'select-bluetooth-device' here, and the page hangs
// until the callback is invoked. Reconnects answer it immediately with the
// remembered id; a user-driven pairing streams the candidate list to the
// Settings UI and waits for a pick.

type PendingChooser = {
  callback: (deviceId: string) => void
  candidates: WearableDeviceCandidate[]
  /** Set when the device window asked to reconnect to a known device. */
  autoSelectId: string | null
  timer: ReturnType<typeof setTimeout> | null
}

let pending: PendingChooser | null = null

/** Chromium keeps the chooser open indefinitely; without a bound, a pairing the
 *  user walked away from would keep scanning forever. */
const CHOOSER_TIMEOUT_MS = 60_000

export function getDeviceSettings(): DeviceSettings {
  return getAppSettings().device
}

export function setPairedDevice(device: WearableDeviceInfo | null): DeviceSettings {
  const next = setAppSettings({
    device: { ...getAppSettings().device, pairedDevice: device }
  })
  return next.device
}

/**
 * Pick the device id to answer the chooser with. Returns null while the user
 * still has to choose. Pure so the auto-answer rule is testable: a reconnect to
 * a remembered device must never surface a picker, and a pairing must never
 * auto-answer.
 */
export function resolveChooserSelection(
  candidates: WearableDeviceCandidate[],
  autoSelectId: string | null
): string | null {
  if (autoSelectId === null) return null
  const match = candidates.find((c) => c.deviceId === autoSelectId)
  return match ? match.deviceId : null
}

/** True while a chooser is open and waiting for a selection. */
export function isChooserPending(): boolean {
  return pending !== null
}

/** Called by the renderer (through the bridge) to answer an open chooser. */
export function selectChooserDevice(deviceId: string | null): void {
  const current = pending
  if (current === null) return
  pending = null
  if (current.timer !== null) clearTimeout(current.timer)
  // An empty string is Chromium's documented "user cancelled" answer.
  current.callback(deviceId ?? '')
}

/**
 * Install the chooser handler on the device window's webContents. `getDeviceWc`
 * is read live so a respawned window is rewired by the caller.
 */
export function attachBluetoothChooser(
  wc: WebContents,
  options: {
    /** Device id to answer with silently (auto-reconnect), if any. */
    autoSelectId: () => string | null
    onCandidates: (candidates: WearableDeviceCandidate[]) => void
  }
): void {
  wc.on('select-bluetooth-device', (event, deviceList, callback) => {
    event.preventDefault()
    const candidates: WearableDeviceCandidate[] = deviceList.map((d) => ({
      deviceId: d.deviceId,
      deviceName: d.deviceName
    }))
    const autoSelectId = options.autoSelectId()
    const auto = resolveChooserSelection(candidates, autoSelectId)
    if (auto !== null) {
      callback(auto)
      return
    }
    if (pending !== null && pending.timer !== null) clearTimeout(pending.timer)
    const timer = setTimeout(() => {
      if (pending?.callback !== callback) return
      pending = null
      console.warn('[device] Bluetooth chooser timed out with no selection')
      callback('')
    }, CHOOSER_TIMEOUT_MS)
    pending = { callback, candidates, autoSelectId, timer }
    // Chromium re-fires this event as new devices are discovered, so the list
    // grows while the user is looking at it.
    options.onCandidates(candidates)
  })
}

/** Audio recovered off a wearable's own storage, handed to the offline log. */
export interface RecoveredAudio {
  bytes: Uint8Array
  timerStart: number
  seconds: number
  totalFrames: number
  codec: string
  sampleRate: number
  frameSize: number
  device: string
}

/** Rejects anything that is not a complete recovered recording. The device
 *  window sends this over IPC, so the payload is validated rather than trusted:
 *  a bad timestamp becomes a permanently refused upload, and a bad duration
 *  misreports how much audio the user got back. */
export function parseRecoveredAudio(raw: unknown): RecoveredAudio | null {
  if (raw === null || typeof raw !== 'object') return null
  const v = raw as Record<string, unknown>
  const bytes =
    v.bytes instanceof Uint8Array
      ? v.bytes
      : v.bytes instanceof ArrayBuffer
        ? new Uint8Array(v.bytes)
        : null
  if (bytes === null || bytes.byteLength === 0) return null
  const positiveInt = (value: unknown): number | null =>
    typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null
  const timerStart = positiveInt(v.timerStart)
  const seconds = positiveInt(v.seconds)
  const totalFrames = positiveInt(v.totalFrames)
  const sampleRate = positiveInt(v.sampleRate)
  const frameSize = positiveInt(v.frameSize)
  if (
    timerStart === null ||
    seconds === null ||
    totalFrames === null ||
    sampleRate === null ||
    frameSize === null
  ) {
    return null
  }
  if (typeof v.codec !== 'string' || v.codec.length === 0) return null
  if (typeof v.device !== 'string' || v.device.length === 0) return null
  return {
    bytes,
    timerStart,
    seconds,
    totalFrames,
    sampleRate,
    frameSize,
    codec: v.codec,
    device: v.device
  }
}

export function registerDeviceHandlers(
  getDeviceWc: () => WebContents | null,
  /** The main window's webContents id. Writes and chooser answers are accepted
   *  from it alone: every renderer shares one preload, so without this check an
   *  auxiliary window could unpair a device or answer an open chooser. */
  getMainWcId: () => number | undefined,
  /** Persists audio recovered off the device. Optional so tests that only
   *  exercise settings do not need the offline log. */
  storeRecovered?: (audio: RecoveredAudio) => Promise<'stored' | 'duplicate' | 'failed'>
): void {
  const fromMainWindow = (event: { sender: WebContents }): boolean => {
    const mainId = getMainWcId()
    if (mainId !== undefined && event.sender.id === mainId) return true
    console.warn('[device] rejected settings/chooser call from a non-main window')
    return false
  }

  // Reading is harmless and the Settings tab is not always the main window in
  // tests, so only writes and chooser answers are gated.
  ipcMain.handle('omi-device:get-settings', () => getDeviceSettings())

  ipcMain.handle('omi-device:set-settings', (e, patch: Partial<DeviceSettings>) => {
    if (!fromMainWindow(e)) return getDeviceSettings()
    const current = getAppSettings().device
    const next = setAppSettings({
      device: {
        pairedDevice: patch.pairedDevice === undefined ? current.pairedDevice : patch.pairedDevice,
        autoReconnect:
          typeof patch.autoReconnect === 'boolean' ? patch.autoReconnect : current.autoReconnect,
        deviceListenEnabled:
          typeof patch.deviceListenEnabled === 'boolean'
            ? patch.deviceListenEnabled
            : current.deviceListenEnabled
      }
    }).device
    // The device window holds the live session, so it needs the new policy
    // immediately rather than at the next reconnect.
    sendDeviceCommandFromMain(getDeviceWc, { type: 'device-settings', settings: next })
    emitDeviceEventFromMain({ type: 'device-listen-state', state: 'settings-updated' }, null)
    return next
  })

  ipcMain.handle('omi-device:select', (e, deviceId: string | null) => {
    if (!fromMainWindow(e)) return
    selectChooserDevice(deviceId)
  })

  // Only the device window may write recovered audio. Every renderer shares one
  // preload, so without this guard any window could inject recordings into the
  // offline log and have them uploaded as the user's conversations.
  ipcMain.handle('omi-device:store-recovered', async (e, raw: unknown) => {
    const wc = getDeviceWc()
    if (wc === null || wc.isDestroyed() || e.sender.id !== wc.id) {
      console.warn('[device] rejected recovered audio from a non-device window')
      return 'failed'
    }
    if (storeRecovered === undefined) return 'failed'
    const audio = parseRecoveredAudio(raw)
    if (audio === null) return 'failed'
    return storeRecovered(audio)
  })
}
