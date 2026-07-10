// Pure presentation logic for the system-tray icon. No Electron imports so it is
// trivially unit-testable; tray.ts consumes describeTray() to drive the real
// Tray image, tooltip, and context-menu label.

export type TrayState = 'idle' | 'listening' | 'paused'

/** Which committed .ico under resources/tray/ to show for a state. */
export type TrayIconKey = TrayState

export interface TrayPresentation {
  iconKey: TrayIconKey
  /** Tray tooltip (kept well under Windows' 127-char limit). */
  tooltip: string
  /** Label for the pause/resume context-menu item. */
  toggleLabel: string
  /** What activating the toggle item means in this state. */
  toggleAction: 'pause' | 'resume'
}

export const TRAY_STATES: readonly TrayState[] = ['idle', 'listening', 'paused']

export function isTrayState(value: unknown): value is TrayState {
  return value === 'idle' || value === 'listening' || value === 'paused'
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
  const base: Record<TrayState, Omit<TrayPresentation, 'tooltip'> & { tooltip: string }> = {
    idle: {
      iconKey: 'idle',
      tooltip: 'Omi',
      toggleLabel: 'Resume listening',
      toggleAction: 'resume'
    },
    listening: {
      iconKey: 'listening',
      tooltip: 'Omi — listening',
      toggleLabel: 'Pause listening',
      toggleAction: 'pause'
    },
    paused: {
      iconKey: 'paused',
      tooltip: 'Omi — paused',
      toggleLabel: 'Resume listening',
      toggleAction: 'resume'
    }
  }
  const p = base[state]
  return { ...p, tooltip: opts.updateReady ? `${p.tooltip} · update ready` : p.tooltip }
}
