import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { SettingsSearchProvider, useSettingsSearch } from '../components/settings/searchContext'
import { SettingsTabRail } from '../components/settings/SettingsTabRail'
import { SettingsTabPanel } from '../components/settings/SettingsTabPanel'
import { SETTINGS_TABS, type SettingsTabId } from '../components/settings/tabs'
import { AIChatTab } from '../components/settings/tabs/AIChatTab'
import { ShortcutsTab } from '../components/settings/tabs/ShortcutsTab'
import { TranscriptionTab } from '../components/settings/tabs/TranscriptionTab'
import { PlanUsageTab } from '../components/settings/tabs/PlanUsageTab'
import { AboutTab } from '../components/settings/tabs/AboutTab'
import { RewindTab } from '../components/settings/tabs/RewindTab'
import { PrivacyTab } from '../components/settings/tabs/PrivacyTab'
import { AccountTab } from '../components/settings/tabs/AccountTab'
import { AdvancedTab } from '../components/settings/tabs/AdvancedTab'
import { Memories } from './Memories'
import { cn } from '../lib/utils'

// The Memories tab renders the full Memories page (its own layout, brain map and
// management UI), so it isn't a simple searchable settings panel — it's handled
// separately below and is intentionally absent from this map.
const TAB_COMPONENTS: Partial<Record<SettingsTabId, () => React.JSX.Element>> = {
  'ai-chat': AIChatTab,
  shortcuts: ShortcutsTab,
  transcription: TranscriptionTab,
  'plan-usage': PlanUsageTab,
  about: AboutTab,
  rewind: RewindTab,
  privacy: PrivacyTab,
  account: AccountTab,
  advanced: AdvancedTab
}

function SettingsInner(props: { onClose?: () => void }): React.JSX.Element {
  const { query, setQuery } = useSettingsSearch()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [active, setActive] = useState<SettingsTabId>(() => {
    const tab = searchParams.get('tab')
    return tab && SETTINGS_TABS.some((t) => t.id === tab) ? (tab as SettingsTabId) : 'ai-chat'
  })
  const close = props.onClose ?? (() => navigate('/home'))
  const drawerMode = Boolean(props.onClose)

  const rail = (
    <SettingsTabRail
      active={active}
      onSelect={(id) => {
        setActive(id)
        setQuery('') // selecting a tab exits search
        setSearchParams(id === 'ai-chat' ? {} : { tab: id })
      }}
      query={query}
      onQuery={setQuery}
      onBack={close}
      backLabel={drawerMode ? 'Close' : 'Back'}
      side={drawerMode ? 'right' : 'left'}
      showBack={!drawerMode}
    />
  )

  return (
    <div className={cn('flex h-full min-h-0', drawerMode && 'gap-5')}>
      {!drawerMode && rail}
      <section
        className={cn(
          'min-h-0 flex-1 overflow-hidden',
          drawerMode &&
            'rounded-[1.35rem] border border-white/[0.12] bg-black/50 shadow-[0_28px_80px_rgba(0,0,0,0.44)] backdrop-blur-2xl'
        )}
      >
        {active === 'memories' && !query.trim() ? (
          // Full page: owns its own header, scroll and width (the brain map needs the
          // room). Mounted only while active so its memory fetch + WebGL map don't run
          // behind the other tabs.
          <div className="h-full min-h-0">
            <Memories />
          </div>
        ) : (
          <div className="h-full overflow-y-auto px-8 py-8 lg:px-12">
            <div className={cn('mx-auto', drawerMode ? 'max-w-6xl' : 'max-w-2xl')}>
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
      </section>
      {drawerMode && rail}
    </div>
  )
}

export function Settings(props: { onClose?: () => void }): React.JSX.Element {
  return (
    <SettingsSearchProvider>
      <SettingsInner onClose={props.onClose} />
    </SettingsSearchProvider>
  )
}
