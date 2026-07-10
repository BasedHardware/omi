// Pure presentation logic for the system-tray icon. No Electron imports so it is
// trivially unit-testable; tray.ts consumes describeTray() to drive the real
// Tray tooltip and context-menu label (the icon is chosen from the state directly
// in tray.ts).
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
