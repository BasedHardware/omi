import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SettingsSearchProvider, useSettingsSearch } from '../components/settings/searchContext'
import { SettingsTabRail } from '../components/settings/SettingsTabRail'
import { SettingsTabPanel } from '../components/settings/SettingsTabPanel'
import { SETTINGS_TABS, type SettingsTabId } from '../components/settings/tabs'
import { GeneralTab } from '../components/settings/tabs/GeneralTab'
import { RewindTab } from '../components/settings/tabs/RewindTab'
import { PrivacyTab } from '../components/settings/tabs/PrivacyTab'
import { AccountTab } from '../components/settings/tabs/AccountTab'
import { AdvancedTab } from '../components/settings/tabs/AdvancedTab'
import { Memories } from './Memories'

// The Memories tab renders the full Memories page (its own layout, brain map and
// management UI), so it isn't a simple searchable settings panel — it's handled
// separately below and is intentionally absent from this map.
const TAB_COMPONENTS: Partial<Record<SettingsTabId, () => React.JSX.Element>> = {
  general: GeneralTab,
  rewind: RewindTab,
  privacy: PrivacyTab,
  account: AccountTab,
  advanced: AdvancedTab
}

function SettingsInner(): React.JSX.Element {
  const [active, setActive] = useState<SettingsTabId>('general')
  const { query, setQuery } = useSettingsSearch()
  const navigate = useNavigate()

  return (
    <div className="flex h-full min-h-0">
      <SettingsTabRail
        active={active}
        onSelect={(id) => {
          setActive(id)
          setQuery('') // selecting a tab exits search
        }}
        query={query}
        onQuery={setQuery}
        onBack={() => navigate('/home')}
      />
      {active === 'memories' ? (
        // Full page: owns its own header, scroll and width (the brain map needs the
        // room). Mounted only while active so its memory fetch + WebGL map don't run
        // behind the other tabs.
        <div className="min-h-0 flex-1">
          <Memories />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-8 py-8 lg:px-12">
          <div className="mx-auto max-w-2xl">
            {/* All panels stay mounted (so search can see every row); each shows when
                it's the active tab, or when a search matches one of its rows. */}
            {SETTINGS_TABS.map(({ id, label }) => {
              const Comp = TAB_COMPONENTS[id]
              if (!Comp) return null // memories has no panel — rendered full-page above
              return (
                <SettingsTabPanel key={id} id={id} label={label} active={active === id}>
                  <Comp />
                </SettingsTabPanel>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export function Settings(): React.JSX.Element {
  return (
    <SettingsSearchProvider>
      <SettingsInner />
    </SettingsSearchProvider>
  )
}
