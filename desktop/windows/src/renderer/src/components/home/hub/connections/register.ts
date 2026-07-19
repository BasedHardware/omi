import { lazy } from 'react'
import { registerHubConnectContent } from '../hubConnectSlot'

// Register the Connections panel as the Hub's Connect-stage content — LAZILY. This
// module is tiny: importing it (from main.tsx) does NOT pull in the connections
// component graph. React.lazy defers the dynamic import until HubConnectPanel first
// renders the component, i.e. the first time the MAIN window opens the Connect
// stage. Secondary windows (bar/insight-toast/capture/glow) share the bundle but
// never render that panel, so they never evaluate the connections graph.
// The dynamic import, named once so the lazy render path and the eager preload share
// the exact same chunk. import() is memoized by the module system, so preloading warms
// precisely the chunk React.lazy will later resolve — no double fetch.
const loadConnectionsPanel = (): Promise<{
  default: typeof import('./ConnectionsPanel').ConnectionsPanel
}> => import('./ConnectionsPanel').then((m) => ({ default: m.ConnectionsPanel }))

registerHubConnectContent(lazy(loadConnectionsPanel), () => {
  void loadConnectionsPanel()
})
