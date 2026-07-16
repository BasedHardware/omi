// Pure presentation logic for the system-tray icon + context menu. Only TYPE
// imports from electron (erased at compile time), so it stays trivially
// unit-testable without an Electron runtime — same split as contextMenuTemplate.ts
// (pure) vs contextMenu.ts (wiring). tray.ts consumes describeTray() +
// buildTrayMenuTemplate() to drive the real Tray tooltip and context menu.
import type { MenuItemConstructorOptions } from 'electron'
import type { TrayListeningState } from '../shared/types'

// The union lives in shared/types.ts (mirrored to the renderer); alias it here so
// the main process and renderer can never disagree on the set of tray states.
export type TrayState = TrayListeningState

export interface TrayPresentation {
  /** Tray tooltip (kept well under Windows' 127-char limit). */
  tooltip: string
  /** Label for the pause/resume context-menu item. */
  toggleLabel: string
}

export const TRAY_STATES: readonly TrayState[] = ['idle', 'listening', 'paused']

export function isTrayState(value: unknown): value is TrayState {
  return TRAY_STATES.includes(value as TrayState)
}

/**
 * Map a listening state to its tray presentation. Only the actively-listening
 * state offers "Pause listening"; idle (not yet listening) and paused both offer
 * "Resume listening". When an update is staged, the tooltip gets a "· update
 * ready" suffix so the tray hints at it without an extra icon.
 */
export function describeTray(
  state: TrayState,
  opts: { updateReady?: boolean } = {}
): TrayPresentation {
  const base: Record<TrayState, TrayPresentation> = {
    idle: { tooltip: 'Omi', toggleLabel: 'Resume listening' },
    listening: { tooltip: 'Omi — listening', toggleLabel: 'Pause listening' },
    paused: { tooltip: 'Omi — paused', toggleLabel: 'Resume listening' }
  }
  const p = base[state]
  return { ...p, tooltip: opts.updateReady ? `${p.tooltip} · update ready` : p.tooltip }
}

// Electron-touching actions the tray menu triggers. Injected so the template
// builder stays pure/unit-testable; tray.ts binds the real implementations
// (window control, listening, updater, settings) via TrayDeps. Mirrors
// contextMenuTemplate.ts's ContextMenuDeps.
export interface TrayMenuActions {
  /** Surface + focus the main window (Open Omi). */
  showMainWindow: () => void
  /** Pause/Resume listening (the renderer flips its pref and reports back). */
  toggleListening: () => void
  /** Show the window and route to Settings. */
  openSettings: () => void
  /** Run a manual update check (Mac's "Check for Updates…"). */
  checkForUpdates: () => void
  /** Flip the screen-analysis master (Mac's "Screen Capture" menu-bar toggle). */
  toggleScreenCapture: () => void
  /** Quit for real. */
  quit: () => void
}

/**
 * The tray context-menu template. Pure (returns plain descriptors) so it is
 * unit-tested without an Electron runtime; tray.ts feeds the result to
 * Menu.buildFromTemplate. Layout mirrors Mac's menu bar (OmiApp.swift): the
 * Screen Capture toggle sits at the top and Check for Updates sits just before
 * Quit. `screenCaptureEnabled` drives the checkbox; `toggleLabel` is the
 * pause/resume label from describeTray.
 */
export function buildTrayMenuTemplate(
  opts: { toggleLabel: string; screenCaptureEnabled: boolean },
  actions: TrayMenuActions
): MenuItemConstructorOptions[] {
  return [
    {
      type: 'checkbox',
      label: 'Screen Capture',
      checked: opts.screenCaptureEnabled,
      click: () => actions.toggleScreenCapture()
    },
    { type: 'separator' },
    { label: 'Open Omi', click: () => actions.showMainWindow() },
    { label: opts.toggleLabel, click: () => actions.toggleListening() },
    { type: 'separator' },
    { label: 'Settings', click: () => actions.openSettings() },
    { type: 'separator' },
    { label: 'Check for Updates', click: () => actions.checkForUpdates() },
    { type: 'separator' },
    { label: 'Quit Omi', click: () => actions.quit() }
  ]
}
