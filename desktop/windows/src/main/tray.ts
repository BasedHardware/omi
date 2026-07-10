// System-tray presence + close-to-tray control surface. The tray is the app's
// anchor while every window is hidden: it shows listening state, toggles the
// main window, and owns the only real Quit affordance. Pure presentation logic
// (icon/tooltip/menu label per state) lives in trayState.ts; this file is the
// Electron wiring.
import { Tray, Menu, nativeImage, type NativeImage } from 'electron'
import idleIconPath from '../../resources/tray/idle.ico?asset'
import listeningIconPath from '../../resources/tray/listening.ico?asset'
import pausedIconPath from '../../resources/tray/paused.ico?asset'
import { describeTray, isTrayState, type TrayState } from './trayState'

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
  /** Quit for real. */
  quit: () => void
}

let tray: Tray | null = null
let deps: TrayDeps | null = null
let currentState: TrayState = 'idle'
let updateReady = false

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
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Open Omi', click: () => d.showMainWindow() },
      { label: p.toggleLabel, click: () => d.toggleListening() },
      { type: 'separator' },
      { label: 'Settings', click: () => d.openSettings() },
      { type: 'separator' },
      { label: 'Quit Omi', click: () => d.quit() }
    ])
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

export function destroyTray(): void {
  if (tray && !tray.isDestroyed()) tray.destroy()
  tray = null
  deps = null
}
