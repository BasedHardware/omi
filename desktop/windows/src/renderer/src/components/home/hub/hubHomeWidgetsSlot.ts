import type { ComponentType } from 'react'

// The resting Hub's home-widgets slot — the seam between Track 5 (the Hub chrome)
// and Track 3 (the dashboard widgets that live inside it, e.g. the focused-goals
// chip row).
//
// WHY A REGISTRY, not a prop: HomeHub is rendered deep inside the Home page, far
// from where Track 3's code lives. A module-level registration point lets Track 3
// drop its widgets in from its own startup code without threading a prop through
// the whole tree or editing HomeHub for every widget. Registration happens once at
// import/startup, before the Hub is ever shown, so there is no re-render timing
// issue. This mirrors `hubConnectSlot.ts` (the Connect-stage seam) exactly.
//
// ── CONTRACT for Track 3 ────────────────────────────────────────────────────────
// Register your widget(s) once at app startup:
//
//     import { registerHubHomeWidgets } from '.../home/hub/hubHomeWidgetsSlot'
//     registerHubHomeWidgets(HomeGoalsChips)
//
// Your component receives `HubHomeWidgetsProps` (nav callbacks only) and must:
//   • BE COMPACT — you mount inside the resting hub cluster, ABOVE the stat ribbon,
//     in a no-scroll flexbox. Render a single line (`shrink-0`); never a panel that
//     grows the stage or forces it to scroll.
//   • SELF-NAVIGATE by default — the callbacks are optional overrides. HomeHub
//     passes none, so fall back to your own routing when a prop is absent. This
//     keeps HomeHub decoupled from Track 3's routes.
//   • RESTING STATE — register nothing and the Hub renders no widget row (the
//     cluster is unchanged), so a partial rollout degrades cleanly.

export interface HubHomeWidgetsProps {
  /** Open the full goals surface. Optional — the widget self-navigates if unset. */
  onShowAll?: () => void
  /** Open a single goal by id. Optional — the widget self-navigates if unset. */
  onOpenGoal?: (id: string) => void
}

let registered: ComponentType<HubHomeWidgetsProps> | null = null

/** Track 3: register the resting-hub widget row. Call once at startup. */
export function registerHubHomeWidgets(component: ComponentType<HubHomeWidgetsProps>): void {
  registered = component
}

/** Read the registered widget row (or null → the Hub renders no widgets). */
export function getHubHomeWidgets(): ComponentType<HubHomeWidgetsProps> | null {
  return registered
}
