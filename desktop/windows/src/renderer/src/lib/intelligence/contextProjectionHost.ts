/**
 * Context-projection host — the renderer side of the director seam: relays the
 * stable device-id hash to main (so main's snapshot calls share this
 * renderer's device scope), and feeds director/TCRS-evaluated What-Matters-Now
 * projections into the dashboard store through `applyContextProjection`.
 *
 * Projections apply only after a normal `load()` has established the account
 * generation and control mode (`hasLoadedOnce`) — the seam re-projects rows,
 * never bootstraps the surface.
 */

import { getWindowsDeviceIdHash } from '../clientDevice'
import { dashboardIntelligence } from './dashboardStore'
import { readWmnProjection } from './wireTypes'

let started = false

export function startContextProjectionHost(): void {
  if (started) return
  started = true
  void getWindowsDeviceIdHash()
    .then((hash) => window.omi?.directorSetDeviceId?.(hash))
    .catch(() => undefined)
  window.omi?.onContextProjection?.((raw) => {
    const projection = readWmnProjection(raw)
    if (projection === null) return
    // Apply only after a load established the rollout state, and only while
    // the account is in-rollout (generation present): a projection must never
    // repopulate a surface the control gate has cleared.
    const state = dashboardIntelligence.getState()
    if (!state.hasLoadedOnce || state.accountGeneration === null) return
    dashboardIntelligence.applyContextProjection(projection)
  })
}

/** Test seam: reset the once-guard. */
export function _resetContextProjectionHostForTests(): void {
  started = false
}
