// The Hub's stage machine, kept as a pure reducer so the transitions can be
// tested without mounting the React tree.
//
// Mac (DashboardPage) animates mode changes with a spring(response 0.46,
// dampingFraction 0.86). CSS has no spring, so the components translate that to a
// 460ms transition on --ease-out. That is an approximation, not a port — chosen
// over pulling in a runtime animation library for one transition.

export type HomeStageMode = 'hub' | 'chat' | 'connect'

export type HomeStageEvent =
  // The ask bar took focus, or was tapped.
  | { type: 'askFocused' }
  // A message was submitted (typed, or a suggestion tapped).
  | { type: 'submitted' }
  // The Connect button was pressed — it TOGGLES, so it is the one event whose
  // result depends on the current mode.
  | { type: 'connectToggled' }
  // Esc, or a click outside the active panel.
  | { type: 'dismissed' }

export function nextStage(mode: HomeStageMode, event: HomeStageEvent): HomeStageMode {
  switch (event.type) {
    case 'askFocused':
    case 'submitted':
      return 'chat'
    case 'connectToggled':
      return mode === 'connect' ? 'hub' : 'connect'
    case 'dismissed':
      return 'hub'
  }
}

// A panel (chat / connect) is on stage in every mode except the resting hub.
export function isPanelMode(mode: HomeStageMode): boolean {
  return mode !== 'hub'
}
