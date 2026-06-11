import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Target, ChevronRight } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { toast } from '../../lib/toast'
import { GenerateGoalsButton } from '../ui/GenerateGoalsButton'

// Compact dashboard surface for the idle Home screen: the active goals with
// their progress, mirroring the macOS dashboard Goals widget. Reads the same
// /v1/goals/all feed the Goals page uses; tapping opens the Goals page.
type Goal = {
  id: string
  title: string
  target_value?: number | null
  current_value?: number | null
  // Done when is_active === false (matches the live backend Goal model).
  is_active?: boolean
}

// Complete when server-archived (is_active === false) or progress reached the
// target. Mirrors pages/Goals.tsx (the backend has no is_active write path).
function isCompleted(g: Goal): boolean {
  if (g.is_active === false) return true
  const target = g.target_value ?? 0
  return target > 0 && (g.current_value ?? 0) >= target
}

function progressPct(g: Goal): number {
  if (isCompleted(g)) return 100
  const target = g.target_value ?? 0
  const current = g.current_value ?? 0
  if (target > 0) return Math.max(0, Math.min(100, Math.round((current / target) * 100)))
  return 0
}

const MAX_SHOWN = 2

export function QuickGoalsWidget({ onReady }: { onReady?: () => void }): React.JSX.Element | null {
  const [goals, setGoals] = useState<Goal[] | null>(null)
  const { pathname } = useLocation()
  // Tell the parent once our data has loaded, so it can reveal both widgets
  // together rather than letting them pop in / reshuffle.
  const readyFired = useRef(false)
  useEffect(() => {
    if (goals !== null && !readyFired.current) {
      readyFired.current = true
      onReady?.()
    }
  }, [goals, onReady])
  // Track the signed-in user so the fetch waits for (and re-runs on) auth being
  // ready. On a cold start the Home panel mounts already at /home and fires its
  // fetch immediately — before Firebase has restored the user — so without this
  // the request goes out unauthenticated, fails, and (since pathname never
  // changes) never retries, leaving the widget permanently hidden.
  const [userId, setUserId] = useState<string | null>(auth.currentUser?.uid ?? null)
  const [generating, setGenerating] = useState(false)
  useEffect(() => onAuthStateChanged(auth, (u) => setUserId(u?.uid ?? null)), [])

  const fetchGoals = useCallback((): (() => void) => {
    let cancelled = false
    omiApi
      .get('/v1/goals/all')
      .then((res) => {
        const data = res.data as Goal[] | { goals?: Goal[] }
        const list = Array.isArray(data) ? data : (data.goals ?? [])
        if (!cancelled) setGoals(list.filter((g) => !isCompleted(g)))
      })
      .catch(() => {
        // Keep any previously-loaded goals on a transient failure rather than
        // hiding the widget; only show empty if we have never loaded.
        if (!cancelled) setGoals((prev) => prev ?? [])
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Primary fetch: as soon as auth is ready (and again if the user changes).
  // The Home panel is always mounted, so this preloads the widget's data
  // independent of the current route — the cause of the "disappeared widget"
  // bug was gating the only fetch on a pathname *change* to /home, which never
  // re-fires while you sit on Home after a failed/early initial load.
  useEffect(() => {
    if (!userId) return
    return fetchGoals()
  }, [userId, fetchGoals])

  // Refetch when returning to Home (pick up goals added/completed elsewhere).
  useEffect(() => {
    if (pathname !== '/home') return
    return fetchGoals()
  }, [pathname, fetchGoals])

  // Refetch when the window regains focus, so a goal added or completed in
  // another window/sandbox shows up without navigating away.
  useEffect(() => {
    const onFocus = (): void => {
      if (auth.currentUser) fetchGoals()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [fetchGoals])

  // One-tap AI goal generation: ask the backend to suggest a goal from the
  // user's memories, create it, then refetch so the widget shows it.
  const generate = useCallback(async (): Promise<void> => {
    setGenerating(true)
    try {
      const res = await omiApi.get('/v1/goals/suggest')
      const s = res.data as { suggested_title?: string; suggested_target?: number | null }
      if (!s?.suggested_title) {
        toast('No suggestion right now', { tone: 'info', body: 'Omi needs a few memories first.' })
        return
      }
      const target =
        typeof s.suggested_target === 'number' && s.suggested_target > 0 ? s.suggested_target : 1
      await omiApi.post('/v1/goals', { title: s.suggested_title, target_value: target })
      fetchGoals()
    } catch {
      toast('Could not generate a goal', { tone: 'error' })
    } finally {
      setGenerating(false)
    }
  }, [fetchGoals])

  // Still loading — render nothing.
  if (!goals) return null

  // No goals yet: keep the card frame, with a one-tap AI generation button
  // (same /v1/goals/suggest feature as the Goals tab) centered inside it.
  if (goals.length === 0) {
    return (
      <div className="widget-card items-center justify-center">
        <GenerateGoalsButton onClick={generate} loading={generating} />
      </div>
    )
  }

  const shown = goals.slice(0, MAX_SHOWN)

  return (
    <Link to="/goals" className="widget-card group">
      <div className="flex items-center gap-3">
        <div className="glass-subtle flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
          <Target className="h-4 w-4 text-white/70" />
        </div>
        <div className="flex flex-1 items-center gap-1.5 text-sm font-medium text-white/85">
          Goals
          <span className="text-white/35">{goals.length}</span>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-white/25 transition-colors group-hover:text-white/50" />
      </div>
      <div className="mt-3 space-y-2">
        {shown.map((g) => {
          const pct = progressPct(g)
          return (
            <div key={g.id}>
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <span className="truncate text-white/65">{g.title}</span>
                <span className="shrink-0 text-white/35">{pct}%</span>
              </div>
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-white/45 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
        {goals.length > MAX_SHOWN && (
          <p className="text-[11px] text-white/35">+{goals.length - MAX_SHOWN} more</p>
        )}
      </div>
    </Link>
  )
}
