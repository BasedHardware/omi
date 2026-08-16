import { useEffect, useSyncExternalStore } from 'react'
import {
  dashboardIntelligence,
  type DashboardIntelligenceState,
  type DashboardIntelligenceStore
} from '../lib/intelligence/dashboardStore'

/** Bind a component to the dashboard intelligence store (What Matters Now +
 *  canonical goals). Loads on mount and again when the window regains focus,
 *  mirroring mac's onAppear + didBecomeActive pair; there is no timer-based
 *  refetch on either platform. */
export function useDashboardIntelligence(
  store: DashboardIntelligenceStore = dashboardIntelligence
): DashboardIntelligenceState {
  const state = useSyncExternalStore(
    (listener) => store.subscribe(listener),
    () => store.getState()
  )

  useEffect(() => {
    void store.load()
    const onFocus = (): void => {
      void store.load()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [store])

  return state
}
