// src/main/insight/toastWindow.ts
// Acrylic insight toast ("Omi notification"): frameless, transparent:false +
// setBackgroundMaterial('acrylic'→'mica'→none) — same DWM-backdrop approach as
// the overlay. Anchored bottom-right, shown WITHOUT stealing focus, auto-dismissed
// after a timeout (paused while hovered).
import { BrowserWindow, screen } from 'electron'
import { join } from 'path'
import { loadRenderer } from '../render/renderServer'
import type { InsightPayload } from '../../shared/types'

const WIDTH = 360
const HEIGHT = 168
const MARGIN = 16
const AUTO_DISMISS_MS = 8000

let toastWindow: BrowserWindow | null = null
let dismissTimer: ReturnType<typeof setTimeout> | null = null

function applyMaterial(win: BrowserWindow): void {
  const w = win as BrowserWindow & { setBackgroundMaterial?: (m: string) => void }
  if (process.platform !== 'win32' || typeof w.setBackgroundMaterial !== 'function') return
  try {
    w.setBackgroundMaterial('acrylic')
  } catch {
    try {
      w.setBackgroundMaterial('mica')
    } catch {
      /* CSS-glass fallback in the renderer */
    }
  }
}

function ensureWindow(): BrowserWindow {
  if (toastWindow && !toastWindow.isDestroyed()) return toastWindow
  const win = new BrowserWindow({
    width: WIDTH,
    height: HEIGHT,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    // Must be focusable or Chromium won't route mouse input to it (the ✕ and
    // hover-to-pause silently stop working). It still never steals focus when it
    // appears because we show it via showInactive().
    focusable: true,
    hasShadow: true,
    backgroundColor: '#000000',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      webSecurity: false,
      backgroundThrottling: false
    }
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  win.on('closed', () => {
    toastWindow = null
  })
  loadRenderer(win, 'insight-toast')
  applyMaterial(win)
  toastWindow = win
  return win
}

function position(win: BrowserWindow): void {
  const wa = screen.getPrimaryDisplay().workArea
  win.setBounds({
    x: wa.x + wa.width - WIDTH - MARGIN,
    y: wa.y + wa.height - HEIGHT - MARGIN,
    width: WIDTH,
    height: HEIGHT
  })
}

export function showInsightToast(payload: InsightPayload): void {
  const win = ensureWindow()
  position(win)
  // showInactive: appear on top without taking focus from the user's current app.
  win.showInactive()
  const send = (): void => {
    if (!win.isDestroyed()) win.webContents.send('insight:payload', payload)
  }
  if (win.webContents.isLoading()) win.webContents.once('did-finish-load', send)
  else send()
  if (dismissTimer) clearTimeout(dismissTimer)
  dismissTimer = setTimeout(hideInsightToast, AUTO_DISMISS_MS)
}

export function hideInsightToast(): void {
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
  if (toastWindow && !toastWindow.isDestroyed() && toastWindow.isVisible()) toastWindow.hide()
}

/** Pause the auto-dismiss while the pointer is over the toast. */
export function pauseInsightDismiss(): void {
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
}

/** Resume the auto-dismiss when the pointer leaves. No-op if already hidden. */
export function resumeInsightDismiss(): void {
  if (!toastWindow || toastWindow.isDestroyed() || !toastWindow.isVisible()) return
  if (dismissTimer) clearTimeout(dismissTimer)
  dismissTimer = setTimeout(hideInsightToast, AUTO_DISMISS_MS)
}

/** Pre-create the (hidden) toast window so the first insight shows instantly. */
export function createInsightToastWindow(): void {
  ensureWindow()
}
