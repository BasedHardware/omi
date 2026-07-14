import type { ComponentType } from 'react'

// The Connect stage's content slot — the seam between Track 5 (chrome) and Track 3
// (connector tray content).
//
// WHY A REGISTRY, not a prop: HomeHub is rendered deep inside the Home page, far from
// where Track 3's code lives. A module-level registration point lets Track 3 drop its
// tray in from its own startup code without threading a prop through the whole tree or
// editing HubConnectPanel/HomeHub. Registration happens once at import/startup, before
// the Hub is ever opened to the Connect stage, so there is no re-render timing issue.
//
// ── CONTRACT for Track 3 (P7 connectors) ──────────────────────────────────────────
// Register your tray once at app startup:
//
//     import { registerHubConnectContent } from '.../home/hub/hubConnectSlot'
//     registerHubConnectContent(ConnectTray)
//
// Your component receives `HubConnectSlotProps` and must honour:
//   • SIZING — you mount at width:100% / height:100% inside a panel the Hub caps at
//     maxWidth 1280px / maxHeight 640px. The panel flexes to fill the stage and
//     shrinks on short windows (down to the app's 600px min height). Fill your parent;
//     do NOT set your own outer width/height or the panel will not size you.
//   • SCROLLING — the panel itself does NOT scroll (overflow-hidden, so it can't push
//     the stage around). If your tray can overflow, own an internal overflow-y-auto
//     region — mirror HubChatPanel's scroll box.
//   • DISMISS — `onDismiss()` closes the Connect stage and returns to the resting hub.
//     Wire it to your tray's close button if it has one. Esc and click-outside already
//     call it, so handling it yourself is optional.
//   • RESTING STATE — register nothing and the Hub shows "Connections are coming soon."
//     so a partial rollout degrades cleanly.
//
// Match Mac's Connect panel (DashboardPage source→destination tray) for look and
// behaviour — that visual parity is Track 3's to verify against a real macOS capture;
// Track 5 owns only the container it renders into.

export interface HubConnectSlotProps {
  /** Close the Connect stage, returning to the resting hub. */
  onDismiss: () => void
}

let registered: ComponentType<HubConnectSlotProps> | null = null

/** Track 3: register the connector tray. Call once at startup. */
export function registerHubConnectContent(component: ComponentType<HubConnectSlotProps>): void {
  registered = component
}

/** Read the registered tray (or null → the Hub renders the resting "coming soon"). */
export function getHubConnectContent(): ComponentType<HubConnectSlotProps> | null {
  return registered
}
