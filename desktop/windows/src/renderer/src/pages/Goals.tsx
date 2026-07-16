import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Target,
  Check,
  RefreshCw,
  Plus,
  Trash2,
  Loader2,
  Trophy,
  Lightbulb,
  Sparkles,
  X
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import type { GoalCandidate } from '../../../shared/types'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { GenerateGoalsButton } from '../components/ui/GenerateGoalsButton'
import { toast } from '../lib/toast'
import { goalEmoji } from '../lib/goalEmoji'
import { isCompleted, progressColor, progressLabel, progressPct } from '../lib/goalVisuals'
import { GoalCelebration } from '../components/goals/GoalCelebration'
import { GoalInsightPanel } from '../components/goals/GoalInsightPanel'
import type { GoalResponse as Goal } from '../lib/omiApi.generated'
import { cache, writeCache, hydrateGoalsFromDisk } from '../lib/goalsCache'

type GoalPatch = Partial<Pick<Goal, 'title' | 'target_value' | 'unit'>>

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

function asList(data: unknown): Goal[] {
  if (Array.isArray(data)) return data as Goal[]
  const obj = data as { goals?: Goal[] } | null
  return obj?.goals ?? []
}

// /v1/goals/all returns both active and completed goals; we split them by
// is_active locally. (There is no /v1/goals/completed GET endpoint.)
async function fetchAll(): Promise<Goal[]> {
  const res = await omiApi.get('/v1/goals/all')
  const list = asList(res.data)
  // writeCache mirrors the list to the per-uid cold-start snapshot; loaded is set
  // here (only a successful fetch is authoritative, not an optimistic writeCache).
  writeCache(list)
  cache.loaded = true
  return list
}

// Completion + progress math (isCompleted / progressPct / progressLabel) and the
// progress-bar color ramp now live in ../lib/goalVisuals so the Home goals widget
// shares one source. The is_active/progress completion model is documented there:
// the backend has no write path for is_active/status (PATCH 400s, no /complete
// route), so progress reaching the target is the only completion signal.

export function Goals(): React.JSX.Element {
  // Seed the cache from the per-uid cold-start snapshot before the initial state is
  // read, so the list paints last-known goals immediately on app restart instead of
  // a spinner. The revalidating fetch still runs (gated on cache.loaded) below.
  hydrateGoalsFromDisk()
  const [goals, setGoals] = useState<Goal[]>(cache.goals ?? [])
  // Show the loading state only when there is genuinely nothing to paint.
  const [loading, setLoading] = useState(!cache.loaded && (cache.goals?.length ?? 0) === 0)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<'active' | 'completed' | 'all'>('active')

  const [composing, setComposing] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftTarget, setDraftTarget] = useState('')
  const [draftUnit, setDraftUnit] = useState('')
  const [saving, setSaving] = useState(false)

  // Client-side goal generation (Wave C): the Suggest button runs the same
  // on-device generation as the background auto-gen (main-process
  // goals:generateCandidate), but — unlike the auto job and unlike Mac — it
  // PREVIEWS the candidate so the user reviews before an AI goal joins the list.
  const [generating, setGenerating] = useState(false)
  const [candidate, setCandidate] = useState<GoalCandidate | null>(null)
  const [accepting, setAccepting] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [progressId, setProgressId] = useState<string | null>(null)
  const [progressDraft, setProgressDraft] = useState('')
  const [busy, setBusy] = useState<Set<string>>(new Set())
  // The goal whose completion is currently being celebrated (full-screen
  // confetti overlay). Set when progress reaches the target; cleared when the
  // celebration finishes.
  const [celebrating, setCelebrating] = useState<Goal | null>(null)
  // The goal whose "Goal Insight" panel is open (per-card lightbulb button).
  const [insightGoal, setInsightGoal] = useState<Goal | null>(null)

  const load = useCallback(async (): Promise<void> => {
    setError(null)
    try {
      setGoals(await fetchAll())
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (cache.loaded) return
    let cancelled = false
    ;(async () => {
      try {
        const list = await fetchAll()
        if (!cancelled) setGoals(list)
      } catch (e) {
        if (!cancelled) setError(apiError(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  // Re-fetch whenever main reports a goal changed (background auto-gen created one,
  // or the manual button did). Keeps an open Goals page live with the auto job.
  useEffect(() => window.omi?.onGoalsChanged?.(() => void load()), [load])

  const markBusy = (id: string, on: boolean): void =>
    setBusy((s) => {
      const next = new Set(s)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  // Optimistic PATCH /v1/goals/{id}. On failure restore the prior list.
  const updateGoal = async (id: string, patch: GoalPatch): Promise<void> => {
    const prev = goals
    const next = prev.map((g) => (g.id === id ? { ...g, ...patch } : g))
    setGoals(next)
    writeCache(next)
    markBusy(id, true)
    try {
      await omiApi.patch(`/v1/goals/${id}`, patch)
    } catch (e) {
      setGoals(prev)
      writeCache(prev)
      toast('Could not update goal', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(id, false)
    }
  }

  // PATCH /v1/goals/{id}/progress?current_value={n}. Optimistic. Reaching the
  // target marks the goal complete (completion is derived from progress — see
  // toggleComplete) and fires the full-screen celebration overlay. Reopening a
  // goal (value below target) never celebrates.
  const updateProgress = async (g: Goal, value: number): Promise<void> => {
    const prev = goals
    const reachedTarget =
      (g.target_value ?? 0) > 0 && value >= (g.target_value as number) && !isCompleted(g)
    const next = prev.map((x) => (x.id === g.id ? { ...x, current_value: value } : x))
    setGoals(next)
    writeCache(next)
    markBusy(g.id, true)
    try {
      await omiApi.patch(`/v1/goals/${g.id}/progress`, null, { params: { current_value: value } })
      if (reachedTarget) setCelebrating({ ...g, current_value: value })
    } catch (e) {
      setGoals(prev)
      writeCache(prev)
      toast('Could not update progress', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(g.id, false)
    }
  }

  // The live backend has no write path for is_active/status (PATCH rejects them
  // with 400 "No updates provided") and no /complete route, so the checkbox
  // completes a goal by driving its progress to the target and reopens it by
  // resetting progress to 0 — both via the working progress endpoint.
  const toggleComplete = async (g: Goal): Promise<void> => {
    const target = g.target_value ?? 0
    if (target <= 0) {
      toast('Set a target first', {
        tone: 'info',
        body: 'Goals complete when their progress reaches the target.'
      })
      return
    }
    await updateProgress(g, isCompleted(g) ? 0 : target)
  }

  const deleteGoal = async (id: string): Promise<void> => {
    const prev = goals
    const next = prev.filter((g) => g.id !== id)
    setGoals(next)
    writeCache(next)
    try {
      await omiApi.delete(`/v1/goals/${id}`)
    } catch (e) {
      setGoals(prev)
      writeCache(prev)
      toast('Could not delete goal', { tone: 'error', body: apiError(e) })
    }
  }

  const saveNew = async (): Promise<void> => {
    const title = draftTitle.trim()
    if (!title || saving) return
    setSaving(true)
    try {
      // target_value is REQUIRED by the backend (POST 422s without it, even for
      // boolean goals — verified). Default a blank target to 1 so a quick
      // title-only goal still creates (a yes/no-style goal that completes at 1).
      const parsed = Number(draftTarget)
      const target = Number.isFinite(parsed) && parsed > 0 ? parsed : 1
      const body: GoalPatch = {
        title,
        target_value: target,
        ...(draftUnit.trim() ? { unit: draftUnit.trim() } : {})
      }
      await omiApi.post('/v1/goals', body)
      // Re-fetch so we get the server-assigned id/timestamps rather than guess.
      await load()
      setComposing(false)
      setDraftTitle('')
      setDraftTarget('')
      setDraftUnit('')
    } catch (e) {
      toast('Could not create goal', { tone: 'error', body: apiError(e) })
    } finally {
      setSaving(false)
    }
  }

  // Phase 1: main assembles the on-device context bundle and generates ONE
  // candidate goal via the Gemini proxy — without creating it. We preview it below
  // (the Windows review step Mac lacks). Accept → phase 2 (acceptCandidate).
  const generateGoal = async (): Promise<void> => {
    if (generating) return
    setGenerating(true)
    try {
      const res = await window.omi?.goalsGenerateCandidate?.()
      if (!res) {
        toast('Could not suggest a goal', { tone: 'error', body: 'Try again in a moment.' })
        return
      }
      if (res.status === 'candidate') {
        setCandidate(res.candidate)
        return
      }
      if (res.reason === 'insufficient_context') {
        toast('Not enough context yet', {
          tone: 'info',
          body: 'Omi needs a few memories, conversations, or tasks before it can suggest a goal.'
        })
      } else if (res.reason === 'no_session') {
        toast('Sign in to suggest a goal', { tone: 'info' })
      } else {
        toast('Could not suggest a goal', { tone: 'error', body: 'Try again in a moment.' })
      }
    } catch (e) {
      toast('Could not suggest a goal', { tone: 'error', body: apiError(e) })
    } finally {
      setGenerating(false)
    }
  }

  // Phase 2: the user accepted the previewed candidate → main creates it directly
  // (POST /v1/goals + the "New Goal" notification), then we refresh.
  const acceptCandidate = async (): Promise<void> => {
    if (!candidate || accepting) return
    setAccepting(true)
    try {
      const res = await window.omi?.goalsCreateCandidate?.(candidate)
      if (res?.status === 'created') {
        setCandidate(null)
        setFilter('active')
        await load()
        toast('Goal added ✨', { tone: 'success', body: res.title })
      } else {
        toast('Could not add goal', { tone: 'error', body: 'Try again in a moment.' })
      }
    } catch (e) {
      toast('Could not add goal', { tone: 'error', body: apiError(e) })
    } finally {
      setAccepting(false)
    }
  }

  const commitEdit = (id: string): void => {
    const text = editDraft.trim()
    setEditingId(null)
    const original = goals.find((g) => g.id === id)
    if (text && original && text !== original.title) {
      void updateGoal(id, { title: text })
    }
  }

  const commitProgress = (g: Goal): void => {
    const raw = progressDraft.trim()
    setProgressId(null)
    if (raw === '') return
    const value = Number(raw)
    if (!Number.isFinite(value) || value < 0) return
    if (value !== (g.current_value ?? 0)) void updateProgress(g, value)
  }

  const activeCount = useMemo(() => goals.filter((g) => !isCompleted(g)).length, [goals])
  const doneCount = goals.length - activeCount

  const activeGoals = useMemo(() => {
    if (filter === 'completed') return []
    return goals
      .filter((g) => !isCompleted(g))
      .sort(
        (a, b) =>
          (new Date(b.created_at ?? 0).getTime() || 0) -
          (new Date(a.created_at ?? 0).getTime() || 0)
      )
  }, [goals, filter])

  const completedGoals = useMemo(() => {
    if (filter === 'active') return []
    return goals
      .filter(isCompleted)
      .sort(
        (a, b) =>
          (new Date(b.updated_at ?? 0).getTime() || 0) -
          (new Date(a.updated_at ?? 0).getTime() || 0)
      )
  }, [goals, filter])

  const renderCard = (g: Goal): React.JSX.Element => {
    const isBusy = busy.has(g.id)
    const done = isCompleted(g)
    const pct = progressPct(g)
    return (
      <li key={g.id} className="surface-card group p-4 animate-fade-in">
        <div className="flex items-start gap-3">
          <button
            onClick={() => void toggleComplete(g)}
            disabled={isBusy}
            aria-label={done ? 'Reopen goal' : 'Mark as complete'}
            className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all duration-200 ${
              done
                ? 'border-white/30 bg-white/15 text-white'
                : 'border-white/20 hover:border-white/45'
            } ${isBusy ? 'opacity-50' : ''}`}
          >
            {done && <Check className="h-3.5 w-3.5" />}
          </button>

          {/* Category glyph auto-derived from the title (shared with the Home widget). */}
          <div
            className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 text-[18px] leading-none ${
              done ? 'opacity-50' : ''
            }`}
            aria-hidden="true"
          >
            {goalEmoji(g.title)}
          </div>

          <div className="min-w-0 flex-1">
            {editingId === g.id ? (
              <input
                autoFocus
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                onBlur={() => commitEdit(g.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitEdit(g.id)
                  else if (e.key === 'Escape') setEditingId(null)
                }}
                className="w-full border-0 border-b border-white/25 bg-transparent pb-0.5 text-sm text-white focus:border-white/60 focus:outline-none focus:ring-0"
              />
            ) : (
              <button
                onClick={() => {
                  setEditDraft(g.title)
                  setEditingId(g.id)
                }}
                title="Click to edit"
                className={`block w-full text-left text-sm font-medium leading-relaxed ${
                  done ? 'text-white/40 line-through' : 'text-white/90'
                }`}
              >
                {g.title}
              </button>
            )}

            {/* Progress bar + editable current value */}
            <div className="mt-2.5">
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, backgroundColor: progressColor(pct / 100) }}
                />
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-[11px] text-white/45">
                {progressId === g.id ? (
                  <input
                    type="number"
                    autoFocus
                    value={progressDraft}
                    min={0}
                    onChange={(e) => setProgressDraft(e.target.value)}
                    onBlur={() => commitProgress(g)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitProgress(g)
                      else if (e.key === 'Escape') setProgressId(null)
                    }}
                    className="w-20 rounded-md border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                  />
                ) : (
                  <button
                    onClick={() => {
                      setProgressDraft(String(g.current_value ?? 0))
                      setProgressId(g.id)
                    }}
                    className="rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5 hover:text-white/70"
                    title="Update progress"
                  >
                    {progressLabel(g)}
                  </button>
                )}
                {!done && pct > 0 && <span className="text-white/30">{pct}%</span>}
              </div>
            </div>
          </div>

          <div className="mt-0.5 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            {/* Insight is only worthwhile on goals with a real target; a 0-target
                yes/no goal has little for the advice model to reason about. */}
            {(g.target_value ?? 0) > 0 && (
              <button
                onClick={() => setInsightGoal(g)}
                className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
                title="Get goal insight"
                aria-label="Get goal insight"
              >
                <Lightbulb className="h-4 w-4" />
              </button>
            )}
            <button
              onClick={() => void deleteGoal(g.id)}
              className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-rose-300/80"
              title="Delete goal"
              aria-label="Delete goal"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      </li>
    )
  }

  const visibleCount = activeGoals.length + completedGoals.length

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Goals"
        titleSlot={<TasksGoalsToggle />}
        subtitle={loading ? 'Loading…' : `${activeCount} active · ${doneCount} completed`}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
              {(['active', 'completed', 'all'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`rounded-xl px-3 py-1.5 text-xs font-medium capitalize transition-all duration-200 ${
                    filter === f
                      ? 'bg-white/15 text-white'
                      : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
            <GenerateGoalsButton onClick={generateGoal} loading={generating} label="Suggest" />
            <button
              onClick={() => setComposing((c) => !c)}
              className="btn-primary px-3 py-2"
              title="Add a goal"
            >
              <Plus className="h-4 w-4" />
              New
            </button>
            <button
              onClick={onRefresh}
              disabled={refreshing || loading}
              className="btn-ghost px-3 py-2 disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {candidate && (
          <div className="mx-auto mb-5 max-w-3xl">
            <div className="surface-card animate-fade-in border border-white/10 p-4">
              <div className="flex items-start gap-3">
                <div className="glass-subtle mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl">
                  <Sparkles className="h-4 w-4 text-white/70" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
                    Suggested goal
                  </p>
                  <p className="mt-1 text-sm font-medium text-white/90">
                    {candidate.suggestion.title}
                  </p>
                  {candidate.suggestion.target > 0 && (
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-white/45">
                      <Target className="h-3.5 w-3.5" />
                      Target {candidate.suggestion.target}
                    </p>
                  )}
                  {candidate.suggestion.reasoning && (
                    <p className="mt-2 text-xs leading-relaxed text-white/55">
                      {candidate.suggestion.reasoning}
                    </p>
                  )}
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={acceptCandidate}
                      disabled={accepting}
                      className="btn-primary px-4 py-2 disabled:opacity-40"
                    >
                      {accepting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Plus className="h-4 w-4" />
                      )}
                      Add this goal
                    </button>
                    <button
                      onClick={generateGoal}
                      disabled={generating || accepting}
                      className="btn-ghost px-3 py-2 disabled:opacity-50"
                      title="Suggest another"
                    >
                      <RefreshCw className={`h-4 w-4 ${generating ? 'animate-spin' : ''}`} />
                      Another
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => setCandidate(null)}
                  className="shrink-0 rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
                  title="Dismiss"
                  aria-label="Dismiss suggestion"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}
        {composing && (
          <div className="mx-auto mb-5 max-w-3xl">
            <div className="surface-card animate-fade-in p-4">
              <input
                autoFocus
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void saveNew()
                  } else if (e.key === 'Escape') {
                    setComposing(false)
                    setDraftTitle('')
                    setDraftTarget('')
                    setDraftUnit('')
                  }
                }}
                placeholder="What do you want to achieve?"
                className="input-field"
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-xs text-white/45">
                  <Target className="h-3.5 w-3.5" />
                  <input
                    type="number"
                    min={0}
                    value={draftTarget}
                    onChange={(e) => setDraftTarget(e.target.value)}
                    placeholder="Target (1)"
                    className="w-28 rounded-md border border-white/20 bg-black/30 px-2 py-1 text-xs text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                  />
                </label>
                <input
                  value={draftUnit}
                  onChange={(e) => setDraftUnit(e.target.value)}
                  placeholder="Unit (e.g. books)"
                  className="w-36 rounded-md border border-white/20 bg-black/30 px-2 py-1 text-xs text-white focus:border-white/50 focus:outline-none"
                />
                <button
                  onClick={() => {
                    setComposing(false)
                    setDraftTitle('')
                    setDraftTarget('')
                    setDraftUnit('')
                  }}
                  className="btn-ghost ml-auto px-3 py-2"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  onClick={saveNew}
                  disabled={saving || !draftTitle.trim()}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Add goal'}
                </button>
              </div>
            </div>
          </div>
        )}

        {loading && (
          <ul className="mx-auto max-w-3xl space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <li key={i} className="surface-card p-4">
                <div className="flex items-start gap-3">
                  <div className="skeleton mt-0.5 h-5 w-5 shrink-0 rounded-md" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-4 w-2/3" />
                    <div className="skeleton h-1.5 w-full rounded-full" />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Only alarm when there's genuinely nothing to show. A failed revalidation
            over cached goals (offline cold start) stays silent — the last-known
            list is on screen and the next successful fetch updates it. */}
        {error && goals.length === 0 && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">
            <p className="text-white/80">Couldn’t load your goals.</p>
            <div className="mt-2 flex items-center gap-3">
              <button
                onClick={() => {
                  setLoading(true)
                  void load()
                }}
                className="btn-ghost px-3 py-1.5 text-xs"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Try again
              </button>
              <span className="text-xs text-white/35">{error}</span>
            </div>
          </div>
        )}

        {!loading && !error && goals.length === 0 && !composing && (
          <EmptyState
            icon={Target}
            title="No goals yet"
            description="Set a goal to track progress over time. Click New to create one."
          />
        )}

        {!loading && goals.length > 0 && visibleCount === 0 && (
          <div className="flex flex-col items-center justify-center pt-16 text-center text-white/55">
            <Trophy className="mb-3 h-10 w-10 opacity-40" />
            <p className="text-sm">Nothing here yet.</p>
          </div>
        )}

        {!loading && visibleCount > 0 && (
          <div className="mx-auto max-w-3xl space-y-6">
            {activeGoals.length > 0 && (
              <section>
                <h2 className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40">
                  Active
                  <span className="text-white/25">{activeGoals.length}</span>
                </h2>
                <ul className="space-y-2">{activeGoals.map(renderCard)}</ul>
              </section>
            )}
            {completedGoals.length > 0 && (
              <section>
                <h2 className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40">
                  Completed
                  <span className="text-white/25">{completedGoals.length}</span>
                </h2>
                <ul className="space-y-2">{completedGoals.map(renderCard)}</ul>
              </section>
            )}
          </div>
        )}
      </div>

      {celebrating && <GoalCelebration goal={celebrating} onDone={() => setCelebrating(null)} />}
      {insightGoal && <GoalInsightPanel goal={insightGoal} onClose={() => setInsightGoal(null)} />}
    </div>
  )
}
