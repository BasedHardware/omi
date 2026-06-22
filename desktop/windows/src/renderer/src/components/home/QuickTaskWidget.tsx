import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ListChecks, ChevronRight } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { auth, onAuthStateChanged } from '../../lib/firebase'

// Compact dashboard surface for the idle Home screen: a preview of the next
// couple of open tasks (soonest due first), mirroring the Goals widget. Reads
// the same /v1/action-items feed the Tasks page uses; tapping opens that page.
type ActionItem = {
  id: string
  description: string
  completed: boolean
  due_at?: string | null
}

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// Right-side due chip, mirroring the Goals widget's progress label. Returns null
// for tasks with no due date (no chip shown). Overdue gets a rose tint.
function dueChip(t: ActionItem): { label: string; overdue: boolean } | null {
  if (!t.due_at) return null
  const due = startOfDay(new Date(t.due_at).getTime())
  const today = startOfDay(Date.now())
  const days = Math.round((due - today) / 86_400_000)
  if (days < 0) return { label: 'Overdue', overdue: true }
  if (days === 0) return { label: 'Today', overdue: false }
  if (days === 1) return { label: 'Tomorrow', overdue: false }
  return {
    label: new Date(t.due_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    overdue: false
  }
}

// Sort by soonest due date; tasks with no due date sink to the bottom.
function byDueDate(a: ActionItem, b: ActionItem): number {
  const av = a.due_at ? new Date(a.due_at).getTime() : Infinity
  const bv = b.due_at ? new Date(b.due_at).getTime() : Infinity
  return av - bv
}

const MAX_SHOWN = 2

export function QuickTaskWidget({ onReady }: { onReady?: () => void }): React.JSX.Element | null {
  const [items, setItems] = useState<ActionItem[] | null>(null)
  const { pathname } = useLocation()
  // Tell the parent once our data has loaded (whether or not we have tasks), so
  // it can reveal both widgets together instead of letting them pop in / reshuffle.
  const readyFired = useRef(false)
  useEffect(() => {
    if (items !== null && !readyFired.current) {
      readyFired.current = true
      onReady?.()
    }
  }, [items, onReady])
  // Track auth so the fetch waits for (and re-runs on) a restored user. On a
  // cold start the Home panel mounts already at /home and fetches before
  // Firebase restores the user; without this the request goes out
  // unauthenticated, fails, and never retries (pathname doesn't change), so the
  // widget stays hidden even though there are tasks.
  const [userId, setUserId] = useState<string | null>(auth.currentUser?.uid ?? null)
  useEffect(() => onAuthStateChanged(auth, (u) => setUserId(u?.uid ?? null)), [])

  const fetchItems = useCallback((): (() => void) => {
    let cancelled = false
    omiApi
      .get('/v1/action-items', { params: { limit: 300, offset: 0 } })
      .then((res) => {
        const data = res.data as ActionItem[] | { action_items?: ActionItem[] }
        const list = Array.isArray(data) ? data : (data.action_items ?? [])
        if (!cancelled) setItems(list.filter((t) => !t.completed))
      })
      .catch(() => {
        // Keep previously-loaded items on a transient failure rather than
        // hiding the widget; only show empty if we have never loaded.
        if (!cancelled) setItems((prev) => prev ?? [])
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Primary fetch: as soon as auth is ready (and again if the user changes).
  // The Home panel is always mounted, so this preloads independent of the
  // current route — gating the only fetch on a pathname *change* to /home was
  // what left the widget hidden after a failed/early initial load.
  useEffect(() => {
    if (!userId) return
    return fetchItems()
  }, [userId, fetchItems])

  // Refetch when returning to Home (pick up tasks changed on the Tasks page).
  useEffect(() => {
    if (pathname !== '/home') return
    return fetchItems()
  }, [pathname, fetchItems])

  // Refetch on window focus so tasks changed elsewhere show up.
  useEffect(() => {
    const onFocus = (): void => {
      if (auth.currentUser) fetchItems()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [fetchItems])

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
                <span className={chip.overdue ? 'shrink-0 text-rose-300/80' : 'shrink-0 text-white/35'}>
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
