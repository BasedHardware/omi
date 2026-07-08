import { Search, ArrowLeft } from 'lucide-react'
import { cn } from '../../lib/utils'
import { SETTINGS_TABS, type SettingsTabId } from './tabs'

const HOVER = 'hover:bg-[var(--nav-sel)]'

export function SettingsTabRail(props: {
  active: SettingsTabId
  onSelect: (id: SettingsTabId) => void
  query: string
  onQuery: (q: string) => void
  onBack: () => void
}): React.JSX.Element {
  const { active, onSelect, query, onQuery, onBack } = props
  return (
    <nav className="flex w-60 shrink-0 flex-col gap-1 border-r border-white/10 px-3 py-6">
      <button
        onClick={onBack}
        className={cn(
          'mb-4 flex items-center gap-2 self-start rounded-lg px-2.5 py-1.5 text-sm font-medium text-white/60 transition-colors hover:text-white/90',
          HOVER
        )}
      >
        <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
        Back
      </button>
      <h2 className="mb-3 px-2.5 font-display text-2xl font-semibold text-text-primary">Settings</h2>
      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search settings…"
          className="glass-subtle w-full rounded-lg py-2 pl-9 pr-3 text-sm text-text-secondary placeholder:text-white/35 focus:outline-none"
        />
      </div>
      {SETTINGS_TABS.map(({ id, label, Icon }) => {
        const isActive = active === id
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            className={cn(
              'flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors duration-150',
              isActive ? 'nav-active text-text-primary' : cn('text-white/50 hover:text-white/80', HOVER)
            )}
          >
            <Icon
              className={cn(
                'h-4 w-4 shrink-0 transition-colors duration-150',
                isActive ? 'text-[color:var(--accent)]' : 'text-white/50'
              )}
              strokeWidth={1.75}
            />
            {label}
          </button>
        )
      })}
    </nav>
  )
}
