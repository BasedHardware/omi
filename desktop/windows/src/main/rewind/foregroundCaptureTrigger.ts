import { BrowserWindow } from 'electron'
import { subscribeForegroundChange } from '../usage/nativeForeground'

const MIN_TRIGGER_GAP_MS = 250

let unsubscribeForeground: (() => void) | null = null
let lastTriggerAt = 0

export function notifyRewindCaptureNow(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('rewind:captureNow')
  }
}

export function startRewindForegroundCaptureTrigger(): void {
  if (unsubscribeForeground) return
  if (process.platform !== 'win32') return

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
