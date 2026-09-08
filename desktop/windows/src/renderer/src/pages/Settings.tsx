import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { onSettingsTabRequest, consumeSettingsTabRequest } from '../lib/settingsNav'
import { SettingsSearchProvider } from '../components/settings/SettingsSearchProvider'
import { useSettingsSearch } from '../components/settings/searchContext'
import { SettingsTabRail } from '../components/settings/SettingsTabRail'
import { SettingsTabPanel } from '../components/settings/SettingsTabPanel'
import { SETTINGS_TABS, type SettingsTabId } from '../components/settings/tabs'
import { GeneralTab } from '../components/settings/tabs/GeneralTab'
import { RewindTab } from '../components/settings/tabs/RewindTab'
import { NotificationsTab } from '../components/settings/tabs/NotificationsTab'
import { PrivacyTab } from '../components/settings/tabs/PrivacyTab'
import { AccountTab } from '../components/settings/tabs/AccountTab'
import { AdvancedTab } from '../components/settings/tabs/AdvancedTab'
import { AgentsTab } from '../components/settings/tabs/AgentsTab'
import { TranscriptionTab } from '../components/settings/tabs/TranscriptionTab'
import { PlanUsageTab } from '../components/settings/tabs/PlanUsageTab'
import { ShortcutsTab } from '../components/settings/tabs/ShortcutsTab'
import { AboutTab } from '../components/settings/tabs/AboutTab'
import { Memories } from './Memories'

// The Memories tab renders the full Memories page (its own layout, brain map and
// management UI), so it isn't a simple searchable settings panel — it's handled
// separately below and is intentionally absent from this map.
const TAB_COMPONENTS: Partial<Record<SettingsTabId, () => React.JSX.Element>> = {
  general: GeneralTab,
  agents: AgentsTab,
  transcription: TranscriptionTab,
  rewind: RewindTab,
  notifications: NotificationsTab,
  privacy: PrivacyTab,
  account: AccountTab,
  'plan-usage': PlanUsageTab,
  shortcuts: ShortcutsTab,
  advanced: AdvancedTab,
  about: AboutTab
}

function SettingsInner(): React.JSX.Element {
  const [active, setActive] = useState<SettingsTabId>('general')
  const { query, setQuery } = useSettingsSearch()
  const navigate = useNavigate()
  const { key } = useLocation()

  // macOS semantics: this returns to the page you came FROM, not to Home — it reads
  // `previousIndexBeforeSettings` and only falls back to the dashboard when there is
  // no previous page (DesktopHomeView.swift:855-862). The Home pill in the chrome bar
  // is the control that goes Home; these are deliberately different destinations.
  //
  // location.key is the router's own "is there anything behind me" signal: the initial
  // history entry is always keyed 'default'. So key === 'default' means Settings was
  // the first page (deep-linked, or opened straight from Ctrl+, at launch) and there is
  // nothing to pop — take Mac's Home fallback instead of navigating out of the app's
  // history. Using the router's key rather than window.history.state also keeps this
  // correct under HashRouter (which the app uses) and MemoryRouter (which tests use).
  const goBack = (): void => {
    if (key === 'default') navigate('/home')
    else navigate(-1)
  }

  // Deep-link consumer: callers elsewhere (e.g. the usage-limit popup's Upgrade
  // button) request a tab via settingsNav before/after this view mounts; the
  // buffered replay in onSettingsTabRequest covers the navigate-then-mount race.
  useEffect(
    () =>
      onSettingsTabRequest((tab) => {
        setActive(tab)
        consumeSettingsTabRequest()
      }),
    []
  )

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
        onBack={goBack}
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
