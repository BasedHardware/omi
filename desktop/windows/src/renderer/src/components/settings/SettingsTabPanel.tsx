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

  return (
    <TabIdContext.Provider value={id}>
      <section className={cn('mb-10', !show && 'hidden')}>
        <h1 className="mb-2 font-display text-3xl font-semibold text-text-primary">{label}</h1>
        <div>{children}</div>
      </section>
    </TabIdContext.Provider>
  )
}
