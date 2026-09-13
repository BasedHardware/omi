import { useCallback, useEffect } from 'react'
import { useSyncExternalStore } from 'react'
import {
  dashboardIntelligence,
  type DashboardIntelligenceState,
  type DashboardIntelligenceStore
} from '../lib/intelligence/dashboardStore'

/** Bind a component to the dashboard intelligence store (What Matters Now +
 *  canonical goals). With autoLoad (the default) it loads on mount and again
 *  when the window regains focus, mirroring mac's onAppear + didBecomeActive
 *  pair; passive consumers (the goal detail sheet) subscribe without loading so
 *  a mount cannot clear a detail-scoped error mid-flight. */
export function useDashboardIntelligence(
  store: DashboardIntelligenceStore = dashboardIntelligence,
  options: { autoLoad?: boolean } = {}
): DashboardIntelligenceState {
  const autoLoad = options.autoLoad !== false
  const subscribe = useCallback((listener: () => void) => store.subscribe(listener), [store])
  const getSnapshot = useCallback(() => store.getState(), [store])
  const state = useSyncExternalStore(subscribe, getSnapshot)

  useEffect(() => {
    if (!autoLoad) return
    void store.load()
    const onFocus = (): void => {
      void store.load()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [store, autoLoad])

  return state
}
