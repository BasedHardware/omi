import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ListChecks, ChevronRight } from 'lucide-react'
import type { ActionItemRecord } from '../../../../shared/types'

// Compact dashboard surface for the idle Home screen: a preview of the next
// couple of open tasks (soonest due first), mirroring the Goals widget. Reads the
// same local-first task store the Tasks page uses (incomplete rows, instant); the
// store re-fires `onTasksChanged` so the preview stays current. Tapping opens Tasks.

// Match the old preview cap so the "Tasks N" count stays a faithful open-task total.
const OPEN_TASKS_LIMIT = 300

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// Right-side due chip, mirroring the Goals widget's progress label. Returns null
// for tasks with no due date (no chip shown). Overdue gets a rose tint.
function dueChip(t: ActionItemRecord): { label: string; overdue: boolean } | null {
  if (t.dueAt == null) return null
  const due = startOfDay(t.dueAt)
  const today = startOfDay(Date.now())
  const days = Math.round((due - today) / 86_400_000)
  if (days < 0) return { label: 'Overdue', overdue: true }
  if (days === 0) return { label: 'Today', overdue: false }
  if (days === 1) return { label: 'Tomorrow', overdue: false }
  return {
    label: new Date(t.dueAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    overdue: false
  }
}

// Sort by soonest due date; tasks with no due date sink to the bottom.
function byDueDate(a: ActionItemRecord, b: ActionItemRecord): number {
  const av = a.dueAt ?? Infinity
  const bv = b.dueAt ?? Infinity
  return av - bv
}

const MAX_SHOWN = 2

export function QuickTaskWidget({ onReady }: { onReady?: () => void }): React.JSX.Element | null {
  const [items, setItems] = useState<ActionItemRecord[] | null>(null)
  // Tell the parent once our data has loaded (whether or not we have tasks), so
  // it can reveal both widgets together instead of letting them pop in / reshuffle.
  const readyFired = useRef(false)
  useEffect(() => {
    if (items !== null && !readyFired.current) {
      readyFired.current = true
      onReady?.()
    }
  }, [items, onReady])

  // Local-first read: the store returns incomplete rows instantly (no auth / network
  // gate needed) and kicks a background hydrate. `onTasksChanged` re-reads on every
  // optimistic write and when a background sync lands — this replaces the old
  // mount/pathname/focus refetch trio the backend fetch needed.
  useEffect(() => {
    let cancelled = false
    const read = (): void => {
      window.omi
        .tasksListIncomplete({ limit: OPEN_TASKS_LIMIT })
        .then((list) => {
          if (!cancelled) setItems(list)
        })
        .catch(() => {
          // Keep previously-loaded items on a transient failure rather than hiding
          // the widget; only show empty if we have never loaded.
          if (!cancelled) setItems((prev) => prev ?? [])
        })
    }
    read()
    const unsub = window.omi.onTasksChanged(read)
    return () => {
      cancelled = true
      unsub()
    }
  }, [])

  // Hide entirely until loaded or when there's nothing actionable — the idle
  // screen stays clean for new users.
  if (!items || items.length === 0) return null

  const shown = [...items].sort(byDueDate).slice(0, MAX_SHOWN)

  return (
    <Link to="/tasks" className="widget-card group">
      <div className="flex items-center gap-3">
        <div className="glass-subtle flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
          <ListChecks className="h-4 w-4 text-white/70" />
        </div>
        <div className="flex flex-1 items-center gap-1.5 text-sm font-medium text-white/85">
          Tasks
          <span className="text-white/35">{items.length}</span>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-white/25 transition-colors group-hover:text-white/50" />
      </div>
      <div className="mt-3 space-y-2">
        {shown.map((t) => {
          const chip = dueChip(t)
          return (
            <div key={t.id} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="truncate text-white/65">{t.description}</span>
              {chip && (
                <span
                  className={chip.overdue ? 'shrink-0 text-rose-300/80' : 'shrink-0 text-white/35'}
                >
                  {chip.label}
                </span>
              )}
            </div>
          )
        })}
        {items.length > MAX_SHOWN && (
          <p className="text-[11px] text-white/35">+{items.length - MAX_SHOWN} more</p>
        )}
      </div>
    </Link>
  )
}
