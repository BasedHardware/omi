// System-tray presence + close-to-tray control surface. The tray is the app's
// anchor while every window is hidden: it shows listening state, toggles the
// main window, and owns the only real Quit affordance. Pure presentation logic
// (icon/tooltip/menu label per state) lives in trayState.ts; this file is the
// Electron wiring.
import { Tray, Menu, nativeImage, type NativeImage } from 'electron'
import idleIconPath from '../../resources/tray/idle.ico?asset'
import listeningIconPath from '../../resources/tray/listening.ico?asset'
import pausedIconPath from '../../resources/tray/paused.ico?asset'
import { buildTrayMenuTemplate, describeTray, isTrayState, type TrayState } from './trayState'

export interface TrayDeps {
  /** Surface + focus the main window (used by Open Omi / Settings / left-click). */
  showMainWindow: () => void
  /** Hide the main window (left-click when it is already visible). */
  hideMainWindow: () => void
  /** Whether the main window is currently visible (drives left-click toggle). */
  isMainWindowVisible: () => boolean
  /** Tray Pause/Resume clicked — the renderer flips its pref and reports back. */
  toggleListening: () => void
  /** Settings menu item — show the window and route to Settings. */
  openSettings: () => void
  /** "Check for Updates" — run a manual update check (see updater.ts). */
  checkForUpdates: () => void
  /** "Screen Capture" checkbox — flip the screenAnalysisEnabled master. The tray
   *  checkbox is refreshed from the persisted value via setTrayScreenCapture, so
   *  this only writes the setting (the coordinator re-syncs off that write). */
  toggleScreenCapture: () => void
  /** Quit for real. */
  quit: () => void
}

let tray: Tray | null = null
let deps: TrayDeps | null = null
let currentState: TrayState = 'idle'
let updateReady = false
// Reflects screenAnalysisEnabled for the "Screen Capture" checkbox. Pushed in via
// setTrayScreenCapture (mirroring updateReady/setTrayUpdateReady) so the tray
// tracks the setting wherever it changes from — the menu toggle, a backend sync,
// or a future Settings switch. Seeded at createTray.
let screenCaptureEnabled = false

const iconPaths: Record<TrayState, string> = {
  idle: idleIconPath,
  listening: listeningIconPath,
  paused: pausedIconPath
}
const iconCache: Partial<Record<TrayState, NativeImage>> = {}

function iconFor(state: TrayState): NativeImage {
  const cached = iconCache[state]
  if (cached) return cached
  const img = nativeImage.createFromPath(iconPaths[state])
  iconCache[state] = img
  return img
}

export function createTray(d: TrayDeps): Tray {
  deps = d
  tray = new Tray(iconFor(currentState))
  // Left-click toggles the main window (standard Windows tray behavior).
  tray.on('click', () => {
    if (!deps) return
    if (deps.isMainWindowVisible()) deps.hideMainWindow()
    else deps.showMainWindow()
  })
  render()
  return tray
}

function render(): void {
  if (!tray || tray.isDestroyed() || !deps) return
  const d = deps
  const p = describeTray(currentState, { updateReady })
  tray.setImage(iconFor(currentState))
  tray.setToolTip(p.tooltip)
  // TrayDeps is a superset of TrayMenuActions, so it satisfies the pure builder's
  // action interface directly.
  tray.setContextMenu(
    Menu.buildFromTemplate(
      buildTrayMenuTemplate({ toggleLabel: p.toggleLabel, screenCaptureEnabled }, d)
    )
  )
}

/** Update the tray to reflect the renderer's reported listening state. */
export function updateTrayState(state: unknown): void {
  if (!isTrayState(state) || state === currentState) return
  currentState = state
  render()
}

/** Reflect a staged auto-update in the tray tooltip. */
export function setTrayUpdateReady(ready: boolean): void {
  if (updateReady === ready) return
  updateReady = ready
  render()
}

/** Reflect the current screenAnalysisEnabled value in the "Screen Capture"
 *  checkbox. Called on startup (seed) and on every settings write, so the tray
 *  stays in sync no matter where the setting changes from. */
export function setTrayScreenCapture(enabled: boolean): void {
  if (screenCaptureEnabled === enabled) return
  screenCaptureEnabled = enabled
  render()
}

/** Whether a live Tray exists (E2E asserts the real thing, not a constant). */
export function isTrayCreated(): boolean {
  return !!tray && !tray.isDestroyed()
}

export function destroyTray(): void {
  if (tray && !tray.isDestroyed()) tray.destroy()
  tray = null
  deps = null
}
