import type { SettingsTabId } from '../components/settings/tabs'

// One-shot channel for deep-linking into a specific Settings tab. A caller (e.g.
// the usage-limit popup's "Upgrade" button) navigates to /settings and requests
// a tab; the Settings view consumes the request once on mount / when it changes.
// Pub/sub rather than a route param so it survives the existing local tab state
// without reworking the router.

let pending: SettingsTabId | null = null
const listeners = new Set<(tab: SettingsTabId) => void>()

/** Ask Settings to open a specific tab. Delivered immediately if a consumer is
 *  listening, otherwise buffered until one subscribes. */
export function requestSettingsTab(tab: SettingsTabId): void {
  pending = tab
  listeners.forEach((cb) => cb(tab))
}

/** Subscribe to tab requests. Replays a buffered request on subscribe so a
 *  navigate-then-mount ordering still delivers. Returns an unsubscribe fn. */
export function onSettingsTabRequest(cb: (tab: SettingsTabId) => void): () => void {
  listeners.add(cb)
  if (pending) cb(pending)
  return () => listeners.delete(cb)
}

/** Clear a consumed request so it isn't replayed to the next subscriber. */
export function consumeSettingsTabRequest(): void {
  pending = null
}
