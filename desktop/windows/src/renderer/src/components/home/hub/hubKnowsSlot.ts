import { useSyncExternalStore, type ComponentType } from 'react'

// The resting Hub's knows-list slot — the seam between the Hub chrome and the
// intelligence knows-list that replaces the wordmark when rows exist (mac hides
// the wordmark whenever its recommendations array is non-empty; this is the
// Windows source that finally makes that branch reachable). Mirrors
// hubHomeWidgetsSlot's registry pattern: registration happens once at startup,
// so HomeHub never imports intelligence code directly.
//
// Presence is a tiny external store rather than a prop: HomeHub needs to know
// whether rows exist BEFORE rendering the slot (the wordmark and the list swap
// in the same layout position), and the list itself owns the data. The list
// reports its row count; the Hub subscribes.

export interface HubKnowsProps {
  /** Prefill the ask bar with a question row's text (never auto-send). */
  onAskPrefill?: (text: string) => void
  /** True while a chat send is in flight — rotation pauses (mac parity). */
  chatSending?: boolean
  /** 'stage' (default): the full resting-hub list that swaps with the wordmark
   *  and reports presence. 'rolling': the chat-mode top-three variant mac shows
   *  over an empty thread — compact, no error card, no presence reporting. */
  variant?: 'stage' | 'rolling'
}

let registered: ComponentType<HubKnowsProps> | null = null

export function registerHubKnows(component: ComponentType<HubKnowsProps>): void {
  registered = component
}

export function getHubKnows(): ComponentType<HubKnowsProps> | null {
  return registered
}

let hasRows = false
const presenceListeners = new Set<() => void>()

/** Called by the registered list whenever its composed row count changes.
 *  (Named report*, not set*: this is an external store notification, not React
 *  state, and the set-state-in-effect lint keys off the prefix.) */
export function reportHubKnowsPresence(present: boolean): void {
  if (hasRows === present) return
  hasRows = present
  for (const listener of presenceListeners) listener()
}

function subscribePresence(listener: () => void): () => void {
  presenceListeners.add(listener)
  return () => presenceListeners.delete(listener)
}

/** HomeHub's read: true while the knows list has rows to show (the wordmark
 *  yields the stage centre to the list, exactly like mac). */
export function useHubKnowsPresence(): boolean {
  return useSyncExternalStore(subscribePresence, () => hasRows)
}
