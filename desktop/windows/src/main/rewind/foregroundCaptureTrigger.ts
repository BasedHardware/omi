import { BrowserWindow } from 'electron'
import { subscribeForegroundChange } from '../usage/nativeForeground'

const CAPTURE_NOW_CHANNEL = 'rewind:capture-now'
const MIN_TRIGGER_GAP_MS = 250

let unsubscribeForeground: (() => void) | null = null
let lastTriggerAt = 0

function notifyRewindCaptureNow(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed() && !window.webContents.isDestroyed()) {
      window.webContents.send(CAPTURE_NOW_CHANNEL)
    }
  }
}

export function startRewindForegroundCaptureTrigger(): void {
  if (unsubscribeForeground || process.platform !== 'win32') return

  unsubscribeForeground = subscribeForegroundChange(() => {
    const now = Date.now()
    if (now - lastTriggerAt < MIN_TRIGGER_GAP_MS) return
    lastTriggerAt = now
    notifyRewindCaptureNow()
  })
}

export function stopRewindForegroundCaptureTrigger(): void {
  unsubscribeForeground?.()
  unsubscribeForeground = null
  lastTriggerAt = 0
}
