import type { SettingsTabId } from '../components/settings/tabs'
import { createSignal } from './signal'

// One-shot channel for deep-linking into a specific Settings tab. A caller (e.g.
// the usage-limit popup's "Upgrade" button) navigates to /settings and requests
// a tab; the Settings view consumes the request once on mount / when it changes.
// Pub/sub rather than a route param so it survives the existing local tab state
// without reworking the router.

const signal = createSignal<SettingsTabId | null>(null)

/** Ask Settings to open a specific tab. Delivered immediately if a consumer is
 *  listening, otherwise buffered until one subscribes. */
export function requestSettingsTab(tab: SettingsTabId): void {
  signal.set(tab)
}

/** Subscribe to tab requests. Replays a buffered request on subscribe so a
 *  navigate-then-mount ordering still delivers. Returns an unsubscribe fn. A
 *  null current value (nothing pending) is never delivered to `cb`. */
export function onSettingsTabRequest(cb: (tab: SettingsTabId) => void): () => void {
  return signal.subscribe((tab) => {
    if (tab != null) cb(tab)
  })
}

/** Clear a consumed request so it isn't replayed to the next subscriber. */
export function consumeSettingsTabRequest(): void {
  signal.set(null)
}
