import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ListChecks, Check, RefreshCw, Plus, Trash2, Calendar, X, Loader2 } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { toast } from '../lib/toast'

// First-class action item, as returned by GET /v1/action-items. This is the
// same source the Omi webapp reads from — so manually-created tasks and due
// dates show up here too, unlike the old approach of scraping every
// conversation's structured.action_items.
type ActionItem = {
  id: string
  description: string
  completed: boolean
  due_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  conversation_id?: string | null
}

type ConvMeta = { title: string; emoji?: string }

type CloudConversation = {
  id: string
  title?: string | null
  structured?: { title?: string | null; emoji?: string | null } | null
}

// Module-level cache so navigating away and back is instant; refresh re-fetches.
const cache = {
  items: null as ActionItem[] | null,
  convs: {} as Record<string, ConvMeta>,
  loaded: false
}

// Cache writes live in module scope (not component scope) so they don't trip
// the react-hooks immutability rule and so optimistic updates stay in sync.
function writeItemsCache(list: ActionItem[]): void {
  cache.items = list
}

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

// Fetch action items plus a best-effort conversation title/emoji map for the
// per-task source links. A failed conversations call still yields the tasks.
async function fetchAll(): Promise<{ items: ActionItem[]; convs: Record<string, ConvMeta> }> {
  const [aiRes, convRes] = await Promise.allSettled([
    omiApi.get('/v1/action-items', { params: { limit: 300, offset: 0 } }),
    omiApi.get<CloudConversation[]>('/v1/conversations', {
      params: { limit: 200, offset: 0, statuses: 'completed,processing' }
    })
  ])
  if (aiRes.status === 'rejected') throw aiRes.reason
  const data = aiRes.value.data as ActionItem[] | { action_items?: ActionItem[] }
  const list = Array.isArray(data) ? data : (data.action_items ?? [])

  const map: Record<string, ConvMeta> = {}
  if (convRes.status === 'fulfilled' && Array.isArray(convRes.value.data)) {
    for (const c of convRes.value.data) {
      map[c.id] = {
        title: c.structured?.title || c.title || 'Untitled',
        emoji: c.structured?.emoji ?? undefined
      }
    }
  }
  cache.items = list
  cache.convs = map
  cache.loaded = true
  return { items: list, convs: map }
}

const DAY = 86_400_000

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// Native <input type="date"> works in local YYYY-MM-DD; convert both ways while
// pinning the time to local noon so the day never slips across time zones.
function toDateInputValue(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function dateInputToIso(v: string): string | null {
  if (!v) return null
  const d = new Date(`${v}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

function formatDue(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const today = startOfDay(Date.now())
  const due = startOfDay(d.getTime())
  if (due === today) return 'Today'
  if (due === today + DAY) return 'Tomorrow'
  if (due === today - DAY) return 'Yesterday'
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' })
  })
}

type Bucket = 'overdue' | 'today' | 'tomorrow' | 'upcoming' | 'nodate'

function bucketOf(t: ActionItem): Bucket {
  if (!t.due_at) return 'nodate'
  const due = startOfDay(new Date(t.due_at).getTime())
  const today = startOfDay(Date.now())
  if (due < today) return 'overdue'
  if (due === today) return 'today'
  if (due === today + DAY) return 'tomorrow'
  return 'upcoming'
}

const BUCKET_ORDER: Bucket[] = ['overdue', 'today', 'tomorrow', 'upcoming', 'nodate']
const BUCKET_LABEL: Record<Bucket, string> = {
  overdue: 'Overdue',
  today: 'Today',
  tomorrow: 'Tomorrow',
  upcoming: 'Upcoming',
  nodate: 'No due date'
}

export function Tasks(): React.JSX.Element {
  const [items, setItems] = useState<ActionItem[]>(cache.items ?? [])
  const [convs, setConvs] = useState<Record<string, ConvMeta>>(cache.convs)
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<'all' | 'open' | 'done'>('open')

  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [draftDue, setDraftDue] = useState('')
  const [saving, setSaving] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [dueEditingId, setDueEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState<Set<string>>(new Set())

  const load = useCallback(async (): Promise<void> => {
    setError(null)
    try {
      const r = await fetchAll()
      setItems(r.items)
      setConvs(r.convs)
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
        const r = await fetchAll()
        if (!cancelled) {
          setItems(r.items)
          setConvs(r.convs)
        }
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

  // Optimistic PATCH /v1/action-items/{id}. On failure restore the prior list.
  const updateItem = async (id: string, patch: Partial<ActionItem>): Promise<void> => {
    const prev = items
    const next = prev.map((it) => (it.id === id ? { ...it, ...patch } : it))
    setItems(next)
    writeItemsCache(next)
    markBusy(id, true)
    try {
      await omiApi.patch(`/v1/action-items/${id}`, patch)
    } catch (e) {
      setItems(prev)
      writeItemsCache(prev)
      toast('Could not update task', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(id, false)
    }
  }

  const deleteItem = async (id: string): Promise<void> => {
    const prev = items
    const next = prev.filter((it) => it.id !== id)
    setItems(next)
    writeItemsCache(next)
    try {
      await omiApi.delete(`/v1/action-items/${id}`)
    } catch (e) {
      setItems(prev)
      writeItemsCache(prev)
      toast('Could not delete task', { tone: 'error', body: apiError(e) })
    }
  }

  const saveNew = async (): Promise<void> => {
    const text = draft.trim()
    if (!text || saving) return
    setSaving(true)
    try {
      const due = dateInputToIso(draftDue)
      await omiApi.post('/v1/action-items', {
        description: text,
        ...(due ? { due_at: due } : {})
      })
      // Re-fetch so we get the server-assigned id/timestamps rather than guess.
      await load()
      setComposing(false)
      setDraft('')
      setDraftDue('')
    } catch (e) {
      toast('Could not create task', { tone: 'error', body: apiError(e) })
    } finally {
      setSaving(false)
    }
  }

  const commitEdit = (id: string): void => {
    const text = editDraft.trim()
    setEditingId(null)
    const original = items.find((it) => it.id === id)
    if (text && original && text !== original.description) {
      void updateItem(id, { description: text })
    }
  }

  const openCount = useMemo(() => items.filter((t) => !t.completed).length, [items])
  const doneCount = items.length - openCount

  const visible = useMemo(
    () =>
      items.filter((t) =>
        filter === 'all' ? true : filter === 'open' ? !t.completed : t.completed
      ),
    [items, filter]
  )

  // For open/all: group open items by due bucket. For done/all: a flat
  // completed list (newest first), shown after the open buckets.
  const openGroups = useMemo(() => {
    if (filter === 'done') return []
    const groups: Record<Bucket, ActionItem[]> = {
      overdue: [],
      today: [],
      tomorrow: [],
      upcoming: [],
      nodate: []
    }
    for (const t of items) {
      if (t.completed) continue
      groups[bucketOf(t)].push(t)
    }
    for (const b of BUCKET_ORDER) {
      groups[b].sort((a, c) => {
        const ad = a.due_at ? new Date(a.due_at).getTime() : Infinity
        const cd = c.due_at ? new Date(c.due_at).getTime() : Infinity
        if (ad !== cd) return ad - cd
        return (
          (new Date(c.created_at ?? 0).getTime() || 0) -
          (new Date(a.created_at ?? 0).getTime() || 0)
        )
      })
    }
    return BUCKET_ORDER.filter((b) => groups[b].length > 0).map((b) => ({
      bucket: b,
      items: groups[b]
    }))
  }, [items, filter])

  const doneItems = useMemo(() => {
    if (filter === 'open') return []
    return items
      .filter((t) => t.completed)
      .sort(
        (a, c) =>
          (new Date(c.completed_at ?? c.created_at ?? 0).getTime() || 0) -
          (new Date(a.completed_at ?? a.created_at ?? 0).getTime() || 0)
      )
  }, [items, filter])

  const renderRow = (t: ActionItem): React.JSX.Element => {
    const isBusy = busy.has(t.id)
    const conv = t.conversation_id ? convs[t.conversation_id] : undefined
    const overdue = !t.completed && bucketOf(t) === 'overdue'
    return (
      <li key={t.id} className="surface-card group flex items-start gap-3 p-4 animate-fade-in">
        <button
          onClick={() => void updateItem(t.id, { completed: !t.completed })}
          disabled={isBusy}
          aria-label={t.completed ? 'Mark as not done' : 'Mark as done'}
          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all duration-200 ${
            t.completed
              ? 'border-white/30 bg-white/15 text-white'
              : 'border-white/20 hover:border-white/45'
          } ${isBusy ? 'opacity-50' : ''}`}
        >
          {t.completed && <Check className="h-3.5 w-3.5" />}
        </button>

        <div className="min-w-0 flex-1">
          {editingId === t.id ? (
            <input
              autoFocus
              value={editDraft}
              onChange={(e) => setEditDraft(e.target.value)}
              onBlur={() => commitEdit(t.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitEdit(t.id)
                else if (e.key === 'Escape') setEditingId(null)
              }}
              className="w-full border-0 border-b border-white/25 bg-transparent pb-0.5 text-sm text-white focus:border-white/60 focus:outline-none focus:ring-0"
            />
          ) : (
            <button
              onClick={() => {
                setEditDraft(t.description)
                setEditingId(t.id)
              }}
              title="Click to edit"
              className={`block w-full text-left text-sm leading-relaxed ${
                t.completed ? 'text-white/40 line-through' : 'text-white/90'
              }`}
            >
              {t.description}
            </button>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
            {dueEditingId === t.id ? (
              <span className="inline-flex items-center gap-1">
                <input
                  type="date"
                  autoFocus
                  value={toDateInputValue(t.due_at)}
                  onChange={(e) => {
                    void updateItem(t.id, { due_at: dateInputToIso(e.target.value) })
                    setDueEditingId(null)
                  }}
                  onBlur={() => setDueEditingId(null)}
                  className="rounded-md border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                />
                {t.due_at && (
                  <button
                    onMouseDown={(e) => {
                      e.preventDefault()
                      void updateItem(t.id, { due_at: null })
                      setDueEditingId(null)
                    }}
                    className="text-white/40 hover:text-white/70"
                    title="Clear due date"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </span>
            ) : (
              <button
                onClick={() => setDueEditingId(t.id)}
                className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5 ${
                  t.due_at ? (overdue ? 'text-rose-300/90' : 'text-white/65') : 'text-white/35'
                }`}
                title="Set due date"
              >
                <Calendar className="h-3 w-3" />
                {t.due_at ? formatDue(t.due_at) : 'Set date'}
              </button>
            )}

            {conv && (
              <Link
                to={`/conversations/${t.conversation_id}`}
                className="inline-flex items-center gap-1.5 truncate hover:text-white/70"
              >
                {conv.emoji && <span>{conv.emoji}</span>}
                <span className="truncate">{conv.title}</span>
              </Link>
            )}
          </div>
        </div>

        <button
          onClick={() => void deleteItem(t.id)}
          className="mt-0.5 shrink-0 rounded-md p-1 text-white/30 opacity-0 transition-all hover:bg-white/5 hover:text-rose-300/80 group-hover:opacity-100"
          title="Delete task"
          aria-label="Delete task"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </li>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Tasks"
        titleSlot={<TasksGoalsToggle />}
        subtitle={loading ? 'Loading…' : `${openCount} open · ${doneCount} done`}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
              {(['open', 'done', 'all'] as const).map((f) => (
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
            <button
              onClick={() => setComposing((c) => !c)}
              className="btn-primary px-3 py-2"
              title="Add a task"
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
        {composing && (
          <div className="mx-auto mb-5 max-w-3xl">
            <div className="surface-card animate-fade-in p-4">
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void saveNew()
                  } else if (e.key === 'Escape') {
                    setComposing(false)
                    setDraft('')
                    setDraftDue('')
                  }
                }}
                placeholder="What needs to get done?"
                className="input-field"
              />
              <div className="mt-3 flex items-center gap-2">
                <label className="flex items-center gap-1.5 text-xs text-white/45">
                  <Calendar className="h-3.5 w-3.5" />
                  <input
                    type="date"
                    value={draftDue}
                    onChange={(e) => setDraftDue(e.target.value)}
                    className="rounded-md border border-white/20 bg-black/30 px-2 py-1 text-xs text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                  />
                </label>
                <button
                  onClick={() => {
                    setComposing(false)
                    setDraft('')
                    setDraftDue('')
                  }}
                  className="btn-ghost ml-auto px-3 py-2"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  onClick={saveNew}
                  disabled={saving || !draft.trim()}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Add task'}
                </button>
              </div>
            </div>
          </div>
        )}

        {loading && (
          <ul className="mx-auto max-w-3xl space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className="surface-card flex items-start gap-3 p-4">
                <div className="skeleton mt-0.5 h-5 w-5 shrink-0 rounded-md" />
                <div className="flex-1 space-y-2">
                  <div className="skeleton h-4 w-3/4" />
                  <div className="skeleton h-3 w-1/3" />
                </div>
              </li>
            ))}
          </ul>
        )}

        {error && <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">{error}</div>}

        {!loading && items.length === 0 && !composing && (
          <EmptyState
            icon={ListChecks}
            title="No tasks yet"
            description="Action items from your conversations show up here, alongside any tasks you add. Click New to create one."
          />
        )}

        {!loading && items.length > 0 && visible.length === 0 && (
          <div className="flex flex-col items-center justify-center pt-16 text-center text-white/55">
            <Check className="mb-3 h-10 w-10 opacity-40" />
            <p className="text-sm">All caught up.</p>
          </div>
        )}

        {!loading && (openGroups.length > 0 || doneItems.length > 0) && (
          <div className="mx-auto max-w-3xl space-y-6">
            {openGroups.map((g) => (
              <section key={g.bucket}>
                <h2 className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40">
                  {BUCKET_LABEL[g.bucket]}
                  <span className="text-white/25">{g.items.length}</span>
                </h2>
                <ul className="space-y-2">{g.items.map(renderRow)}</ul>
              </section>
            ))}
            {doneItems.length > 0 && (
              <section>
                <h2 className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40">
                  Completed
                  <span className="text-white/25">{doneItems.length}</span>
                </h2>
                <ul className="space-y-2">{doneItems.map(renderRow)}</ul>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
