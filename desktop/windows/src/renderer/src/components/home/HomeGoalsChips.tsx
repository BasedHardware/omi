import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { omiApi } from '../../lib/apiClient'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { goalEmoji, DEFAULT_GOAL_EMOJI } from '../../lib/goalEmoji'
import { isCompleted, progressColor, progressPct } from '../../lib/goalVisuals'
import { cache as goalsCache, hydrateGoalsFromDisk, writeCache } from '../../lib/goalsCache'
import { getCacheUid } from '../../lib/persistentCache'
import type { GoalResponse as Goal } from '../../lib/omiApi.generated'
import type { HubHomeWidgetsProps } from './hub/hubHomeWidgetsSlot'

// The resting Hub's focused-goals chip row — the compact, single-line surface
// ported from macOS `FocusedGoalsSection` (WhatMattersNowSection.swift): a row of
// capsule chips (one per goal) with a trailing "All goals" button.
//
// DELIBERATE DEVIATION FROM MAC: Mac's chips are the "focused goals" subset from
// its DashboardIntelligenceStore, a feed the backend does not expose. Windows has
// no focused subset, so we show the user's ACTIVE goals from the same /v1/goals/all
// feed the Goals page and QuickGoalsWidget already read — and add a tiny progress
// bar per chip (Mac shows only the title) so the row carries progress at a glance.
//
// This mounts inside the hub cluster above the stat ribbon and MUST stay one line
// (`shrink-0`) so it never breaks the Hub's no-scroll centering. States are all
// single-line and roughly the same height, so the row never reflows the cluster.
//
// The list comes from the SAME module cache the Goals page fills (goalsCache), not
// a private copy: the Hub's resting cluster — this row with it — unmounts whenever
// the chat or connect panel opens, so a per-mount fetch meant every return to the
// home screen re-flashed the skeleton and re-issued GET /v1/goals/all (#10893).

// Mac caps the row at `.prefix(5)` (WhatMattersNowSection.swift:156).
const MAX_CHIPS = 5

// What the row displays: the active slice of the cached list. `null` (nothing
// cached yet) stays null so the skeleton is shown only when there is genuinely
// nothing to paint — never an "empty" claim we can't back.
function activeGoals(list: Goal[] | null): Goal[] | null {
  return list ? list.filter((g) => !isCompleted(g)) : null
}

export function HomeGoalsChips({ onShowAll, onOpenGoal }: HubHomeWidgetsProps): React.JSX.Element {
  // Seed from the per-uid cold-start snapshot before the initial state is read,
  // exactly as the Goals page does, so a fresh launch paints the last-known chips
  // instead of the skeleton. The revalidating fetch below still runs.
  hydrateGoalsFromDisk()
  const [goals, setGoals] = useState<Goal[] | null>(() => activeGoals(goalsCache.goals))
  const { pathname } = useLocation()
  const navigate = useNavigate()

  // Nav defaults: the widget self-navigates to the Goals page unless the host
  // overrides. There is no per-goal deep link on Windows, so opening a goal lands
  // on the Goals page too — same destination the QuickGoalsWidget card uses.
  const showAll = useCallback(() => {
    if (onShowAll) onShowAll()
    else navigate('/goals')
  }, [onShowAll, navigate])
  const openGoal = useCallback(
    (id: string) => {
      if (onOpenGoal) onOpenGoal(id)
      else navigate('/goals')
    },
    [onOpenGoal, navigate]
  )

  // Track the signed-in user so the fetch waits for (and re-runs on) auth being
  // ready. On a cold start the hub mounts already at /home and fires its fetch
  // immediately — before Firebase has restored the user — so without this the
  // request goes out unauthenticated, fails, and never retries (see the same
  // cold-start note in QuickGoalsWidget).
  const [userId, setUserId] = useState<string | null>(auth.currentUser?.uid ?? null)
  useEffect(() => onAuthStateChanged(auth, (u) => setUserId(u?.uid ?? null)), [])

  const fetchGoals = useCallback((): (() => void) => {
    let cancelled = false
    const originUid = getCacheUid()
    omiApi
      .get('/v1/goals/all')
      .then((res) => {
        const data = res.data as Goal[] | { goals?: Goal[] }
        const list = Array.isArray(data) ? data : (data.goals ?? [])
        // Account-switch guard, same as the Goals page's fetchAll: a fetch that
        // outlived the account must not land under the new uid.
        if (getCacheUid() === originUid) {
          writeCache(list)
          goalsCache.loaded = true
        }
        if (!cancelled) setGoals(activeGoals(list))
      })
      .catch(() => {
        // Keep any previously-loaded goals on a transient failure rather than
        // flashing empty; only fall to empty if we have never loaded.
        if (!cancelled) setGoals((prev) => prev ?? [])
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Primary fetch: as soon as auth is ready (and again if the user changes).
  // Skipped when the cache already holds an authoritative list — that is what
  // makes closing the chat panel repaint the row instead of reloading it.
  useEffect(() => {
    if (!userId || goalsCache.loaded) return
    return fetchGoals()
  }, [userId, fetchGoals])

  // Refetch when returning to Home (pick up goals added/completed elsewhere).
  // Home stays MOUNTED while the user is on another tab (MainViews hides it), so
  // coming back is a navigation, not a remount. Its first run IS the mount, where
  // the effect above already fetched — firing both asked for the same list twice.
  const navigated = useRef(false)
  useEffect(() => {
    if (!navigated.current) {
      navigated.current = true
      return
    }
    if (pathname !== '/home') return
    return fetchGoals()
  }, [pathname, fetchGoals])

  // Refetch on window focus, so a goal added/completed in another window shows up.
  useEffect(() => {
    const onFocus = (): void => {
      if (auth.currentUser) fetchGoals()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [fetchGoals])

  // Loading — a height-stable skeleton so the cluster never jumps when data lands.
  if (goals === null) {
    return (
      <div
        className="flex w-full shrink-0 items-center gap-2"
        aria-hidden
        data-testid="home-goals-chips-loading"
      >
        <span className="h-6 w-24 animate-pulse rounded-full bg-home-tile/[0.6]" />
        <span className="h-6 w-20 animate-pulse rounded-full bg-home-tile/[0.6]" />
      </div>
    )
  }

  // No active goals: a single subtle chip that opens the goals surface to add one.
  if (goals.length === 0) {
    return (
      <div className="flex w-full shrink-0 items-center" data-testid="home-goals-chips">
        <button
          type="button"
          onClick={showAll}
          className="focus-ring group flex items-center gap-1.5 rounded-full border border-home-hairline bg-home-tile/[0.4] px-2.5 py-1 text-[11px] font-medium text-home-muted transition-colors duration-150 hover:bg-home-tileHover hover:text-home-ink"
        >
          <span aria-hidden className="shrink-0 text-[12px] leading-none">
            {DEFAULT_GOAL_EMOJI}
          </span>
          Set a goal
        </button>
      </div>
    )
  }

  return (
    <div
      className="flex w-full shrink-0 items-center gap-2 overflow-hidden"
      data-testid="home-goals-chips"
    >
      {goals.slice(0, MAX_CHIPS).map((g) => {
        const pct = progressPct(g)
        return (
          <button
            key={g.id}
            type="button"
            onClick={() => openGoal(g.id)}
            title={g.title}
            className="focus-ring group flex min-w-0 max-w-[150px] shrink items-center gap-1.5 rounded-full border border-home-hairline bg-home-tile/[0.6] px-2.5 py-1 transition-colors duration-150 hover:bg-home-tileHover"
          >
            <span aria-hidden className="shrink-0 text-[12px] leading-none">
              {goalEmoji(g.title)}
            </span>
            <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-home-secondary transition-colors duration-150 group-hover:text-home-ink">
              {g.title}
            </span>
            {/* Tiny progress bar — same fill grammar as QuickGoalsWidget, colored by
                the shared discrete progressColor ramp. */}
            <span className="h-1 w-4 shrink-0 overflow-hidden rounded-full bg-home-hairline">
              <span
                className="block h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: progressColor(pct / 100) }}
                data-testid={`goal-progress-${g.id}`}
              />
            </span>
          </button>
        )
      })}
      <button
        type="button"
        onClick={showAll}
        className="focus-ring ml-auto shrink-0 rounded-full px-2 py-1 text-[11px] font-medium text-home-muted transition-colors duration-150 hover:text-home-ink"
      >
        All goals
      </button>
    </div>
  )
}
