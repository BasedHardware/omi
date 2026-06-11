import { useCallback, useEffect, useMemo, useState } from 'react'
import { Target, Check, RefreshCw, Plus, Trash2, Loader2, Trophy, Sparkles, X } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { GenerateGoalsButton } from '../components/ui/GenerateGoalsButton'
import { toast } from '../lib/toast'

// A goal as returned by the goals endpoints. The backend uses a target/current
// value model (the progress endpoint is PATCH .../progress?current_value=), so
// progress is derived from current_value / target_value. Fields beyond id/title
// are optional and read defensively — the macOS Goal model carries unit,
// description, status and timestamps, not all of which every goal sets.
type Goal = {
  id: string
  title: string
  // Backend completion model (verified against the live API): a goal is done
  // when is_active === false. There is no status / completed_at field, and
  // there is no GET /v1/goals/completed route (it 405s — "completed" parses as
  // a goal id). Completed history is derived from /v1/goals/all by is_active.
  is_active?: boolean
  goal_type?: string | null // 'scale' | 'boolean'
  target_value?: number | null
  current_value?: number | null
  min_value?: number | null
  max_value?: number | null
  unit?: string | null
  created_at?: string | null
  updated_at?: string | null
}

type GoalPatch = Partial<Pick<Goal, 'title' | 'target_value' | 'unit'>>

// Shape returned by GET /v1/goals/suggest — the backend's `'goals'` LLM reads
// the user's recent memories and proposes one goal (verified live against
// api.omi.me). It does not create anything; we preview it and let the user add
// it via the normal POST /v1/goals path. (The macOS desktop instead runs a
// richer Gemini-direct generation; this server-side suggestion is the
// no-AI-key parity we can offer on Windows today.)
type GoalSuggestion = {
  suggested_title: string
  suggested_type?: string | null
  suggested_target?: number | null
  suggested_min?: number | null
  suggested_max?: number | null
  reasoning?: string | null
}

// Module-level cache so navigating away and back is instant; refresh re-fetches.
const cache = {
  goals: null as Goal[] | null,
  loaded: false
}

function writeCache(list: Goal[]): void {
  cache.goals = list
}

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
  cache.goals = list
  cache.loaded = true
  return list
}

// A goal is complete when the server has archived it (is_active === false) or
// its progress has reached the target. The backend exposes no write path for
// is_active/status (verified: PATCH 400s, no /complete route), so progress is
// the only completion signal we can both read and drive.
function isCompleted(g: Goal): boolean {
  if (g.is_active === false) return true
  const target = g.target_value ?? 0
  return target > 0 && (g.current_value ?? 0) >= target
}

// 0–100 progress percentage. With a target, it's current/target clamped; with
// no target, a goal is either done (100) or not started (0).
function progressPct(g: Goal): number {
  if (isCompleted(g)) return 100
  const target = g.target_value ?? 0
  const current = g.current_value ?? 0
  if (target > 0) return Math.max(0, Math.min(100, Math.round((current / target) * 100)))
  return 0
}

function progressLabel(g: Goal): string {
  const target = g.target_value ?? 0
  const current = g.current_value ?? 0
  const unit = g.unit ? ` ${g.unit}` : ''
  if (target > 0) return `${current} / ${target}${unit}`
  return `${progressPct(g)}%`
}

export function Goals(): React.JSX.Element {
  const [goals, setGoals] = useState<Goal[]>(cache.goals ?? [])
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<'active' | 'completed' | 'all'>('active')

  const [composing, setComposing] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftTarget, setDraftTarget] = useState('')
  const [draftUnit, setDraftUnit] = useState('')
  const [saving, setSaving] = useState(false)

  const [suggesting, setSuggesting] = useState(false)
  const [suggestion, setSuggestion] = useState<GoalSuggestion | null>(null)
  const [addingSuggestion, setAddingSuggestion] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [progressId, setProgressId] = useState<string | null>(null)
  const [progressDraft, setProgressDraft] = useState('')
  const [busy, setBusy] = useState<Set<string>>(new Set())

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
  // toggleComplete) and fires a celebration toast.
  const updateProgress = async (g: Goal, value: number): Promise<void> => {
    const prev = goals
    const reachedTarget = (g.target_value ?? 0) > 0 && value >= (g.target_value as number)
    const next = prev.map((x) => (x.id === g.id ? { ...x, current_value: value } : x))
    setGoals(next)
    writeCache(next)
    markBusy(g.id, true)
    try {
      await omiApi.patch(`/v1/goals/${g.id}/progress`, null, { params: { current_value: value } })
      if (reachedTarget) toast('Goal complete 🎉', { tone: 'success', body: g.title })
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

  // GET /v1/goals/suggest — ask the backend's goals LLM for one goal based on
  // the user's memories, then preview it (no goal is created until they accept).
  const getSuggestion = async (): Promise<void> => {
    if (suggesting) return
    setSuggesting(true)
    try {
      const res = await omiApi.get('/v1/goals/suggest')
      const s = res.data as GoalSuggestion
      if (!s?.suggested_title) {
        toast('No suggestion right now', {
          tone: 'info',
          body: 'Omi needs a few memories before it can suggest a goal.'
        })
        return
      }
      setSuggestion(s)
    } catch (e) {
      toast('Could not get a suggestion', { tone: 'error', body: apiError(e) })
    } finally {
      setSuggesting(false)
    }
  }

  // Accept the suggested goal via the normal create path. POST requires
  // target_value (verified); the suggestion supplies one, default 1 otherwise.
  const acceptSuggestion = async (): Promise<void> => {
    if (!suggestion || addingSuggestion) return
    setAddingSuggestion(true)
    try {
      const target =
        typeof suggestion.suggested_target === 'number' && suggestion.suggested_target > 0
          ? suggestion.suggested_target
          : 1
      const body: GoalPatch = { title: suggestion.suggested_title, target_value: target }
      await omiApi.post('/v1/goals', body)
      await load()
      setSuggestion(null)
      setFilter('active')
      toast('Goal added ✨', { tone: 'success', body: suggestion.suggested_title })
    } catch (e) {
      toast('Could not add goal', { tone: 'error', body: apiError(e) })
    } finally {
      setAddingSuggestion(false)
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
              done ? 'border-white/30 bg-white/15 text-white' : 'border-white/20 hover:border-white/45'
            } ${isBusy ? 'opacity-50' : ''}`}
          >
            {done && <Check className="h-3.5 w-3.5" />}
          </button>

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
                  className={`h-full rounded-full transition-all duration-500 ${
                    done ? 'bg-emerald-400/70' : 'bg-white/45'
                  }`}
                  style={{ width: `${pct}%` }}
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

          <button
            onClick={() => void deleteGoal(g.id)}
            className="mt-0.5 shrink-0 rounded-md p-1 text-white/30 opacity-0 transition-all hover:bg-white/5 hover:text-rose-300/80 group-hover:opacity-100"
            title="Delete goal"
            aria-label="Delete goal"
          >
            <Trash2 className="h-4 w-4" />
          </button>
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
            <GenerateGoalsButton onClick={getSuggestion} loading={suggesting} label="Suggest" />
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
        {suggestion && (
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
                    {suggestion.suggested_title}
                  </p>
                  {typeof suggestion.suggested_target === 'number' &&
                    suggestion.suggested_target > 0 && (
                      <p className="mt-1 flex items-center gap-1.5 text-xs text-white/45">
                        <Target className="h-3.5 w-3.5" />
                        Target {suggestion.suggested_target}
                      </p>
                    )}
                  {suggestion.reasoning && (
                    <p className="mt-2 text-xs leading-relaxed text-white/55">
                      {suggestion.reasoning}
                    </p>
                  )}
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={acceptSuggestion}
                      disabled={addingSuggestion}
                      className="btn-primary px-4 py-2 disabled:opacity-40"
                    >
                      {addingSuggestion ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Plus className="h-4 w-4" />
                      )}
                      Add this goal
                    </button>
                    <button
                      onClick={getSuggestion}
                      disabled={suggesting || addingSuggestion}
                      className="btn-ghost px-3 py-2 disabled:opacity-50"
                      title="Suggest another"
                    >
                      <RefreshCw className={`h-4 w-4 ${suggesting ? 'animate-spin' : ''}`} />
                      Another
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => setSuggestion(null)}
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

        {error && <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">{error}</div>}

        {!loading && goals.length === 0 && !composing && (
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
    </div>
  )
}
