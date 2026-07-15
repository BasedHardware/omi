import { useNavigate } from 'react-router-dom'
import { Brain, GanttChartSquare, History, ListChecks } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../../../lib/utils'

// The Hub's four-cell stat ribbon (macOS DashboardPage). Purely presentational —
// the counts are passed in, so the ribbon has no opinion about where they come
// from and can be rendered in a test without any data layer.
//
// A null count means "not loaded yet" and renders an em-dash rather than a 0: a
// zero is a claim about the user's data, and we only make it once we know.

export type HubStatCounts = {
  conversations: number | null
  /** The conversations source is capped at one page, so a full page means "at least
   *  this many" — rendered "100+". See useHubStats. */
  conversationsAtLeast: boolean
  tasks: number | null
  memories: number | null
  screenshots: number | null
}

type Cell = {
  key: keyof HubStatCounts
  label: string
  Icon: LucideIcon
  to: string
}

const CELLS: Cell[] = [
  { key: 'conversations', label: 'Conversations', Icon: GanttChartSquare, to: '/conversations' },
  { key: 'tasks', label: 'Tasks', Icon: ListChecks, to: '/tasks' },
  { key: 'memories', label: 'Memories', Icon: Brain, to: '/memories' },
  { key: 'screenshots', label: 'Screenshots', Icon: History, to: '/rewind' }
]

export function HubStatRibbon({ counts }: { counts: HubStatCounts }): React.JSX.Element {
  const navigate = useNavigate()

  return (
    <div
      className={cn(
        'flex h-[76px] w-full overflow-hidden rounded-2xl border border-home-hairline/80',
        'bg-home-tile/[0.88] shadow-[0_8px_10px_rgba(0,0,0,0.16)]'
      )}
    >
      {CELLS.map(({ key, label, Icon, to }, i) => {
        const count = counts[key]
        // "—" = unknown. "100+" = a capped source that can only prove a floor.
        const display =
          count === null
            ? '—'
            : key === 'conversations' && counts.conversationsAtLeast
              ? `${count}+`
              : `${count}`
        return (
          <button
            key={key}
            type="button"
            onClick={() => navigate(to)}
            className={cn(
              'focus-ring flex flex-1 flex-col items-center justify-center border-home-hairline/70',
              'px-[10px] py-[13px] text-home-secondary transition-colors duration-150',
              'hover:bg-home-tileHover hover:text-home-ink',
              i > 0 && 'border-l'
            )}
          >
            <span className="flex items-center gap-1.5">
              <Icon className="h-[11px] w-[11px] shrink-0" strokeWidth={2.5} />
              {/* Serif numeral — the ribbon's one typographic accent. tabular-nums
                  so the four cells don't jitter as counts land. */}
              <span className="font-serif text-[22px] font-medium leading-none tabular-nums">
                {display}
              </span>
            </span>
            <span className="mt-1.5 text-[11px] font-medium leading-none">{label}</span>
          </button>
        )
      })}
    </div>
  )
}
