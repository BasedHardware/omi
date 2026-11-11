import { useEffect, useState } from 'react'
import { cn } from '../../lib/utils'
import { TabIdContext, useSettingsSearch } from './searchContext'
import type { SettingsTabId } from './tabs'

/**
 * Wraps one tab's content. Always mounted (so its rows register for search);
 * shown when it's the active tab, or — while searching — when any of its rows
 * match. The tab label doubles as the page title (single active tab) and as a
 * group header when several tabs are shown during a search.
 */
export function SettingsTabPanel(props: {
  id: SettingsTabId
  label: string
  active: boolean
  children: React.ReactNode
}): React.JSX.Element {
  const { id, label, active, children } = props
  const { isSearching, tabHasMatch } = useSettingsSearch()
  const show = isSearching ? tabHasMatch(id) : active

  // Panel enter motion. Panels stay mounted (display:none) for search, so a
  // plain CSS animation can't retrigger on tab switch — instead the start
  // state is applied on the first visible frame and transitions in (macOS
  // settings-pane feel: quick fade + small rise). Honors the global
  // reduce-motion kill-switch via transition-duration.
  const [entered, setEntered] = useState(false)
  useEffect(() => {
    if (!show) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional two-frame enter transition (start state, then rAF to the end state); not a self-retriggering loop
    setEntered(false)
    const id = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(id)
  }, [show])

  return (
    <TabIdContext.Provider value={id}>
      <section
        className={cn(
          'mb-10 transition-[opacity,transform] duration-200 ease-out',
          !show && 'hidden',
          show && (entered ? 'translate-y-0 opacity-100' : 'translate-y-[6px] opacity-0')
        )}
      >
        <h1 className="mb-2 font-display text-3xl font-semibold text-text-primary">{label}</h1>
        <div>{children}</div>
      </section>
    </TabIdContext.Provider>
  )
}
