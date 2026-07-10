// src/main/insight/toastWindow.ts
// Acrylic insight toast ("Omi notification"): frameless, transparent:false +
// setBackgroundMaterial('acrylic'→'mica'→none) — same DWM-backdrop approach as
// the overlay. Anchored bottom-right, shown WITHOUT stealing focus, auto-dismissed
// after a timeout (paused while hovered).
//
// The MEETING toast (Phase 5) reuses this same window + renderer route rather
// than spawning a second toast surface: one acrylic notification window, two
// payload channels ('insight:payload' / 'meeting:toast'), last-writer-wins on
// visibility. Meeting toasts are rare and insights fire at most every 15 min,
// so a clobber is a non-issue and we avoid ~100 lines of duplicated window
// lifecycle + a second always-alive BrowserWindow.
import { BrowserWindow, screen } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import type { InsightPayload, MeetingToastPayload } from '../../shared/types'
import { rendererBaseUrl } from '../rendererServer'

const WIDTH = 360
const HEIGHT = 168
const MARGIN = 16
const AUTO_DISMISS_MS = 8000
// The ask-toast is a decision prompt — give it longer before it slips away.
const MEETING_ASK_DISMISS_MS = 30_000

let toastWindow: BrowserWindow | null = null
let dismissTimer: ReturnType<typeof setTimeout> | null = null
// Dismiss duration of the toast currently shown — hover-resume must re-arm
// with the SAME budget (an ask-toast paused at 30s must not resume at 8s).
let currentDismissMs = AUTO_DISMISS_MS

function armDismiss(ms: number): void {
  currentDismissMs = ms
  if (dismissTimer) clearTimeout(dismissTimer)
  dismissTimer = setTimeout(hideInsightToast, ms)
}
// The meeting payload currently on screen. Kept so the toast renderer can PULL
// it on mount ('meeting:getToast'): a push sent between the window's
// did-finish-load and React's effect subscription would otherwise vanish — a
// real race when a meeting activates within seconds of startup (E2E, or a
// meeting already running when Omi launches).
let currentMeetingToast: MeetingToastPayload | null = null

export function getCurrentMeetingToast(): MeetingToastPayload | null {
  return currentMeetingToast
}

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
      // webSecurity ON (matches the main window). CORS is handled by the
      // main-process webRequest header injection, not by weakening this.
      backgroundThrottling: false
    }
  })
  win.setAlwaysOnTop(true, 'screen-saver')
  win.on('closed', () => {
    toastWindow = null
  })
  // Same-origin as the main window (see overlay/window.ts) so the toast sees
  // the signed-in auth state.
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    win.loadURL(`${process.env['ELECTRON_RENDERER_URL']}#/insight-toast`)
  } else if (rendererBaseUrl()) {
    win.loadURL(`${rendererBaseUrl()}/index.html#/insight-toast`)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'), { hash: 'insight-toast' })
  }
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
  // An insight replaces whatever is on the shared toast — clear any meeting
  // payload so a later toast-window reload can't resurface a stale meeting card
  // via meeting:getToast.
  currentMeetingToast = null
  // showInactive: appear on top without taking focus from the user's current app.
  win.showInactive()
  const send = (): void => {
    if (!win.isDestroyed()) win.webContents.send('insight:payload', payload)
  }
  if (win.webContents.isLoading()) win.webContents.once('did-finish-load', send)
  else send()
  armDismiss(AUTO_DISMISS_MS)
}

/** Show (or update) the meeting toast in the shared toast window. Ask-toasts
 *  linger longer (a decision prompt); capture notices use the standard timeout.
 *  Never silent capture: every auto-start goes through here. */
export function showMeetingToast(payload: MeetingToastPayload): void {
  const win = ensureWindow()
  position(win)
  win.showInactive()
  currentMeetingToast = payload
  const send = (): void => {
    if (!win.isDestroyed()) win.webContents.send('meeting:toast', payload)
  }
  if (win.webContents.isLoading()) win.webContents.once('did-finish-load', send)
  else send()
  armDismiss(payload.kind === 'ask' ? MEETING_ASK_DISMISS_MS : AUTO_DISMISS_MS)
}

/** Hide the shared toast window (same surface as the insight toast). */
export function hideMeetingToast(): void {
  hideInsightToast()
}

export function hideInsightToast(): void {
  currentMeetingToast = null
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

/** Resume the auto-dismiss when the pointer leaves. No-op if already hidden.
 *  Re-arms with the CURRENT toast's duration (ask-toasts keep their 30s). */
export function resumeInsightDismiss(): void {
  if (!toastWindow || toastWindow.isDestroyed() || !toastWindow.isVisible()) return
  armDismiss(currentDismissMs)
}

/** Pre-create the (hidden) toast window so the first insight shows instantly. */
export function createInsightToastWindow(): void {
  ensureWindow()
}
