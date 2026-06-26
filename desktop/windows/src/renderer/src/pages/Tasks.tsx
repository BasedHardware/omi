import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ListChecks,
  Check,
  RefreshCw,
  Plus,
  Trash2,
  Calendar,
  X,
  Loader2,
  Bot,
  Play,
  ShieldCheck,
  Terminal,
  XCircle,
  Search,
  Save,
  ArrowUp,
  ArrowDown,
  Indent,
  Outdent,
  MessageSquare,
  Filter
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { toast } from '../lib/toast'
import {
  enqueueTaskAgentRun,
  useTaskAgentRuns,
  type TaskAgentProvider,
  type TaskAgentRun
} from '../lib/taskAgentQueue'

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

type TaskPriority = 'none' | 'low' | 'medium' | 'high'

type TaskLocalMeta = {
  category?: string
  tags: string[]
  priority: TaskPriority
  order: number
  indent: number
}

type TaskViewFilter = {
  status: 'all' | 'open' | 'done'
  query: string
  bucket: Bucket | 'all'
  source: string
  category: string
  tag: string
  priority: TaskPriority | 'all'
  dateFrom: string
  dateTo: string
}

type SavedTaskView = TaskViewFilter & {
  id: string
  name: string
  createdAt: number
}

const META_KEY = 'omi-windows-task-meta-v1'
const VIEWS_KEY = 'omi-windows-task-views-v1'

const EMPTY_META: TaskLocalMeta = {
  tags: [],
  priority: 'none',
  order: 0,
  indent: 0
}

const DEFAULT_VIEW_FILTER: TaskViewFilter = {
  status: 'open',
  query: '',
  bucket: 'all',
  source: 'all',
  category: 'all',
  tag: 'all',
  priority: 'all',
  dateFrom: '',
  dateTo: ''
}

function loadTaskMeta(): Record<string, TaskLocalMeta> {
  try {
    const raw = JSON.parse(localStorage.getItem(META_KEY) ?? '{}') as Record<
      string,
      Partial<TaskLocalMeta>
    >
    const out: Record<string, TaskLocalMeta> = {}
    for (const [id, value] of Object.entries(raw)) {
      out[id] = {
        category: typeof value.category === 'string' ? value.category : undefined,
        tags: Array.isArray(value.tags)
          ? value.tags.filter((tag): tag is string => typeof tag === 'string')
          : [],
        priority:
          value.priority === 'low' || value.priority === 'medium' || value.priority === 'high'
            ? value.priority
            : 'none',
        order: typeof value.order === 'number' && Number.isFinite(value.order) ? value.order : 0,
        indent:
          typeof value.indent === 'number' && Number.isFinite(value.indent)
            ? Math.max(0, Math.min(3, Math.floor(value.indent)))
            : 0
      }
    }
    return out
  } catch {
    return {}
  }
}

function saveTaskMeta(meta: Record<string, TaskLocalMeta>): void {
  try {
    localStorage.setItem(META_KEY, JSON.stringify(meta))
  } catch {
    /* best-effort */
  }
}

function loadSavedTaskViews(): SavedTaskView[] {
  try {
    const raw = JSON.parse(localStorage.getItem(VIEWS_KEY) ?? '[]') as Partial<SavedTaskView>[]
    return raw
      .filter((view): view is SavedTaskView => !!view.id && !!view.name)
      .map((view) => ({ ...DEFAULT_VIEW_FILTER, ...view }))
  } catch {
    return []
  }
}

function saveSavedTaskViews(views: SavedTaskView[]): void {
  try {
    localStorage.setItem(VIEWS_KEY, JSON.stringify(views))
  } catch {
    /* best-effort */
  }
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

const AGENT_STATUS_CLASS: Record<TaskAgentRun['status'], string> = {
  queued: 'text-white/45',
  running: 'text-sky-200/90',
  'waiting-approval': 'text-amber-200/90',
  completed: 'text-emerald-200/90',
  failed: 'text-rose-200/90'
}

function agentStatusLabel(status: TaskAgentRun['status']): string {
  switch (status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Running'
    case 'waiting-approval':
      return 'Waiting approval'
    case 'completed':
      return 'Completed'
    case 'failed':
      return 'Failed'
  }
}

function AgentRunRow({ run }: { run: TaskAgentRun }): React.JSX.Element {
  return (
    <li className="rounded-md border border-white/[0.08] bg-black/15 p-3">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-white/[0.06] text-white/65">
          {run.status === 'failed' ? (
            <XCircle className="h-4 w-4 text-rose-200/90" />
          ) : run.status === 'completed' ? (
            <Check className="h-4 w-4 text-emerald-200/90" />
          ) : run.status === 'waiting-approval' ? (
            <ShieldCheck className="h-4 w-4 text-amber-200/90" />
          ) : (
            <Terminal className="h-4 w-4" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-xs font-semibold ${AGENT_STATUS_CLASS[run.status]}`}>
              {agentStatusLabel(run.status)}
            </span>
            <span className="text-xs text-white/35">
              {run.provider === 'pi' ? 'Pi/Omi' : 'Claude account'}
            </span>
          </div>
          <div className="mt-1 line-clamp-2 text-sm text-white/80">{run.prompt}</div>
          {run.result && (
            <div className="mt-2 text-xs leading-relaxed text-white/55">{run.result}</div>
          )}
          {run.error && (
            <div className="mt-2 text-xs leading-relaxed text-rose-100/80">{run.error}</div>
          )}
          {(run.toolCalls.length > 0 || run.events.length > 0) && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {run.toolCalls.map((call) => (
                <span
                  key={call.id}
                  className="rounded-md border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-[11px] text-white/45"
                >
                  {call.name}
                </span>
              ))}
              {run.events.map((event, i) => (
                <span
                  key={`${event}-${i}`}
                  className="rounded-md border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-[11px] text-white/45"
                >
                  {event}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

export function Tasks(): React.JSX.Element {
  const [items, setItems] = useState<ActionItem[]>(cache.items ?? [])
  const [convs, setConvs] = useState<Record<string, ConvMeta>>(cache.convs)
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [viewFilter, setViewFilter] = useState<TaskViewFilter>(DEFAULT_VIEW_FILTER)
  const filter = viewFilter.status
  const [meta, setMeta] = useState<Record<string, TaskLocalMeta>>(() => loadTaskMeta())
  const [savedViews, setSavedViews] = useState<SavedTaskView[]>(() => loadSavedTaskViews())
  const [viewName, setViewName] = useState('')
  const [selectedTaskChatId, setSelectedTaskChatId] = useState<string | null>(null)
  const [taskChatDraft, setTaskChatDraft] = useState('')

  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [draftDue, setDraftDue] = useState('')
  const [saving, setSaving] = useState(false)
  const [agentPrompt, setAgentPrompt] = useState('')
  const [agentProvider, setAgentProvider] = useState<TaskAgentProvider>('pi')
  const agentRuns = useTaskAgentRuns()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [dueEditingId, setDueEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState<Set<string>>(new Set())

  const patchViewFilter = (patch: Partial<TaskViewFilter>): void => {
    setViewFilter((current) => ({ ...current, ...patch }))
  }

  const patchMeta = (id: string, patch: Partial<TaskLocalMeta>): void => {
    setMeta((current) => {
      const next = {
        ...current,
        [id]: { ...EMPTY_META, ...(current[id] ?? EMPTY_META), ...patch }
      }
      saveTaskMeta(next)
      return next
    })
  }

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

  const startAgentTask = (): void => {
    try {
      enqueueTaskAgentRun({ prompt: agentPrompt, provider: agentProvider })
      setAgentPrompt('')
      toast('Agent task queued', { tone: 'success' })
    } catch (e) {
      toast('Could not queue agent task', { tone: 'error', body: (e as Error).message })
    }
  }

  const saveCurrentView = (): void => {
    const name = viewName.trim()
    if (!name) return
    const next: SavedTaskView = {
      id: `task-view-${crypto.randomUUID()}`,
      name,
      createdAt: Date.now(),
      ...viewFilter
    }
    const views = [next, ...savedViews.filter((view) => view.name !== name)].slice(0, 12)
    setSavedViews(views)
    saveSavedTaskViews(views)
    setViewName('')
    toast('Task view saved', { tone: 'success' })
  }

  const applySavedView = (id: string): void => {
    const view = savedViews.find((candidate) => candidate.id === id)
    if (!view) return
    setViewFilter({
      status: view.status,
      query: view.query,
      bucket: view.bucket,
      source: view.source,
      category: view.category,
      tag: view.tag,
      priority: view.priority,
      dateFrom: view.dateFrom,
      dateTo: view.dateTo
    })
  }

  const cleanToday = async (): Promise<void> => {
    const dueNow = items.filter((item) => {
      if (item.completed || !item.due_at) return false
      const bucket = bucketOf(item)
      return bucket === 'overdue' || bucket === 'today'
    })
    if (dueNow.length === 0) {
      toast('No due tasks to clean up', { tone: 'info' })
      return
    }
    if (
      !confirm(`Mark ${dueNow.length} overdue/today task${dueNow.length === 1 ? '' : 's'} done?`)
    ) {
      return
    }
    for (const item of dueNow) {
      await updateItem(item.id, { completed: true })
    }
  }

  const moveTask = (id: string, direction: -1 | 1): void => {
    const index = visible.findIndex((item) => item.id === id)
    const target = index + direction
    if (index < 0 || target < 0 || target >= visible.length) return
    const ordered = [...visible]
    const [item] = ordered.splice(index, 1)
    ordered.splice(target, 0, item)
    setMeta((current) => {
      const next = { ...current }
      ordered.forEach((task, order) => {
        next[task.id] = { ...EMPTY_META, ...(next[task.id] ?? EMPTY_META), order: order + 1 }
      })
      saveTaskMeta(next)
      return next
    })
  }

  const startTaskChat = (): void => {
    const task = selectedTaskChatId ? items.find((item) => item.id === selectedTaskChatId) : null
    const text = taskChatDraft.trim()
    if (!task || !text) return
    const taskMeta = meta[task.id] ?? EMPTY_META
    enqueueTaskAgentRun({
      provider: agentProvider,
      prompt: [
        `Task: ${task.description}`,
        task.due_at ? `Due: ${formatDue(task.due_at)}` : 'Due: none',
        taskMeta.category ? `Category: ${taskMeta.category}` : '',
        taskMeta.tags.length > 0 ? `Tags: ${taskMeta.tags.join(', ')}` : '',
        '',
        text
      ]
        .filter(Boolean)
        .join('\n')
    })
    setTaskChatDraft('')
    toast('Task chat queued', { tone: 'success' })
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

  const categoryOptions = useMemo(() => {
    const values = new Set<string>()
    for (const value of Object.values(meta)) {
      if (value.category?.trim()) values.add(value.category.trim())
    }
    return [...values].sort((a, b) => a.localeCompare(b))
  }, [meta])

  const tagOptions = useMemo(() => {
    const values = new Set<string>()
    for (const value of Object.values(meta)) {
      for (const tag of value.tags) values.add(tag)
    }
    return [...values].sort((a, b) => a.localeCompare(b))
  }, [meta])

  const sourceOptions = useMemo(() => {
    const values = new Map<string, string>()
    for (const item of items) {
      if (!item.conversation_id) continue
      values.set(item.conversation_id, convs[item.conversation_id]?.title ?? 'Conversation')
    }
    return [...values.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [items, convs])

  const queryFilter = viewFilter.query
  const bucketFilter = viewFilter.bucket
  const sourceFilter = viewFilter.source
  const categoryFilter = viewFilter.category
  const tagFilter = viewFilter.tag
  const priorityFilter = viewFilter.priority
  const dateFromFilter = viewFilter.dateFrom
  const dateToFilter = viewFilter.dateTo

  const visible = (() => {
    const q = queryFilter.trim().toLowerCase()
    const from = dateFromFilter ? new Date(`${dateFromFilter}T00:00:00`).getTime() : null
    const to = dateToFilter ? new Date(`${dateToFilter}T23:59:59`).getTime() : null
    return items
      .filter((task) => {
        if (filter === 'open' && task.completed) return false
        if (filter === 'done' && !task.completed) return false
        const taskMeta = meta[task.id] ?? EMPTY_META
        const conv = task.conversation_id ? convs[task.conversation_id] : undefined
        const haystack = [
          task.description,
          taskMeta.category ?? '',
          taskMeta.priority,
          taskMeta.tags.join(' '),
          conv?.title ?? ''
        ]
          .join(' ')
          .toLowerCase()
        if (q && !haystack.includes(q)) return false
        if (bucketFilter !== 'all' && bucketOf(task) !== bucketFilter) return false
        if (sourceFilter !== 'all' && task.conversation_id !== sourceFilter) return false
        if (categoryFilter !== 'all' && taskMeta.category !== categoryFilter) return false
        if (tagFilter !== 'all' && !taskMeta.tags.includes(tagFilter)) return false
        if (priorityFilter !== 'all' && taskMeta.priority !== priorityFilter) return false
        if (from !== null || to !== null) {
          const due = task.due_at ? new Date(task.due_at).getTime() : NaN
          if (!Number.isFinite(due)) return false
          if (from !== null && due < from) return false
          if (to !== null && due > to) return false
        }
        return true
      })
      .sort((a, b) => {
        const ao = meta[a.id]?.order ?? 0
        const bo = meta[b.id]?.order ?? 0
        if (ao || bo) return ao - bo
        return 0
      })
  })()

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
    for (const t of visible) {
      if (t.completed) continue
      groups[bucketOf(t)].push(t)
    }
    for (const b of BUCKET_ORDER) {
      groups[b].sort((a, c) => {
        const ao = meta[a.id]?.order ?? 0
        const co = meta[c.id]?.order ?? 0
        if (ao || co) return ao - co
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
  }, [visible, filter, meta])

  const doneItems = useMemo(() => {
    if (filter === 'open') return []
    return visible
      .filter((t) => t.completed)
      .sort((a, c) => {
        const ao = meta[a.id]?.order ?? 0
        const co = meta[c.id]?.order ?? 0
        if (ao || co) return ao - co
        return (
          (new Date(c.completed_at ?? c.created_at ?? 0).getTime() || 0) -
          (new Date(a.completed_at ?? a.created_at ?? 0).getTime() || 0)
        )
      })
  }, [visible, filter, meta])

  const renderRow = (t: ActionItem): React.JSX.Element => {
    const isBusy = busy.has(t.id)
    const conv = t.conversation_id ? convs[t.conversation_id] : undefined
    const overdue = !t.completed && bucketOf(t) === 'overdue'
    const taskMeta = meta[t.id] ?? EMPTY_META
    return (
      <li
        key={t.id}
        className="surface-card group flex items-start gap-3 p-4 animate-fade-in"
        style={{ marginLeft: taskMeta.indent ? `${taskMeta.indent * 18}px` : undefined }}
        draggable
        onDragStart={(event) => event.dataTransfer.setData('text/plain', t.id)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          const fromId = event.dataTransfer.getData('text/plain')
          if (!fromId || fromId === t.id) return
          const fromIndex = visible.findIndex((item) => item.id === fromId)
          const toIndex = visible.findIndex((item) => item.id === t.id)
          if (fromIndex < 0 || toIndex < 0) return
          const ordered = [...visible]
          const [item] = ordered.splice(fromIndex, 1)
          ordered.splice(toIndex, 0, item)
          setMeta((current) => {
            const next = { ...current }
            ordered.forEach((task, order) => {
              next[task.id] = {
                ...EMPTY_META,
                ...(next[task.id] ?? EMPTY_META),
                order: order + 1
              }
            })
            saveTaskMeta(next)
            return next
          })
        }}
      >
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
            <select
              value={taskMeta.priority}
              onChange={(e) => patchMeta(t.id, { priority: e.target.value as TaskPriority })}
              className="rounded-md border border-white/10 bg-black/20 px-1.5 py-0.5 text-[11px] text-white/55 focus:border-white/35 focus:outline-none"
              title="Priority"
            >
              <option value="none" className="bg-neutral-900">
                Priority
              </option>
              <option value="high" className="bg-neutral-900">
                High
              </option>
              <option value="medium" className="bg-neutral-900">
                Medium
              </option>
              <option value="low" className="bg-neutral-900">
                Low
              </option>
            </select>
            <input
              value={taskMeta.category ?? ''}
              onChange={(e) => patchMeta(t.id, { category: e.target.value.trim() || undefined })}
              placeholder="Category"
              className="w-24 rounded-md border border-white/10 bg-black/20 px-1.5 py-0.5 text-[11px] text-white/55 placeholder:text-white/30 focus:border-white/35 focus:outline-none"
            />
            <input
              value={taskMeta.tags.join(', ')}
              onChange={(e) =>
                patchMeta(t.id, {
                  tags: e.target.value
                    .split(',')
                    .map((tag) => tag.trim())
                    .filter(Boolean)
                })
              }
              placeholder="Tags"
              className="w-28 rounded-md border border-white/10 bg-black/20 px-1.5 py-0.5 text-[11px] text-white/55 placeholder:text-white/30 focus:border-white/35 focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-0.5 flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            onClick={() => moveTask(t.id, -1)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
            title="Move up"
            aria-label="Move task up"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => moveTask(t.id, 1)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
            title="Move down"
            aria-label="Move task down"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => patchMeta(t.id, { indent: Math.max(0, taskMeta.indent - 1) })}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
            title="Outdent"
            aria-label="Outdent task"
          >
            <Outdent className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => patchMeta(t.id, { indent: Math.min(3, taskMeta.indent + 1) })}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
            title="Indent"
            aria-label="Indent task"
          >
            <Indent className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setSelectedTaskChatId(t.id)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/5 hover:text-white/70"
            title="Task chat"
            aria-label="Open task chat"
          >
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
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

  const selectedTask = selectedTaskChatId
    ? items.find((item) => item.id === selectedTaskChatId)
    : null

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
                  onClick={() => patchViewFilter({ status: f })}
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
        <div className="mx-auto mb-5 max-w-3xl">
          <div className="surface-card mb-4 animate-fade-in p-4">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-sm font-semibold text-white/85">
              <Filter className="h-4 w-4 text-white/55" />
              Filters and views
            </div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
              <label className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
                <input
                  value={viewFilter.query}
                  onChange={(e) => patchViewFilter({ query: e.target.value })}
                  placeholder="Search tasks, tags, sources"
                  className="input-field pl-9"
                />
              </label>
              <select
                value={viewFilter.bucket}
                onChange={(e) => patchViewFilter({ bucket: e.target.value as Bucket | 'all' })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="all" className="bg-neutral-900">
                  Any due bucket
                </option>
                {BUCKET_ORDER.map((bucket) => (
                  <option key={bucket} value={bucket} className="bg-neutral-900">
                    {BUCKET_LABEL[bucket]}
                  </option>
                ))}
              </select>
              <select
                value={viewFilter.priority}
                onChange={(e) =>
                  patchViewFilter({ priority: e.target.value as TaskPriority | 'all' })
                }
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="all" className="bg-neutral-900">
                  Any priority
                </option>
                <option value="high" className="bg-neutral-900">
                  High priority
                </option>
                <option value="medium" className="bg-neutral-900">
                  Medium priority
                </option>
                <option value="low" className="bg-neutral-900">
                  Low priority
                </option>
                <option value="none" className="bg-neutral-900">
                  No priority
                </option>
              </select>
              <select
                value={viewFilter.source}
                onChange={(e) => patchViewFilter({ source: e.target.value })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="all" className="bg-neutral-900">
                  Any source
                </option>
                {sourceOptions.map(([id, title]) => (
                  <option key={id} value={id} className="bg-neutral-900">
                    {title}
                  </option>
                ))}
              </select>
              <select
                value={viewFilter.category}
                onChange={(e) => patchViewFilter({ category: e.target.value })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="all" className="bg-neutral-900">
                  Any category
                </option>
                {categoryOptions.map((category) => (
                  <option key={category} value={category} className="bg-neutral-900">
                    {category}
                  </option>
                ))}
              </select>
              <select
                value={viewFilter.tag}
                onChange={(e) => patchViewFilter({ tag: e.target.value })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="all" className="bg-neutral-900">
                  Any tag
                </option>
                {tagOptions.map((tag) => (
                  <option key={tag} value={tag} className="bg-neutral-900">
                    {tag}
                  </option>
                ))}
              </select>
              <input
                type="date"
                value={viewFilter.dateFrom}
                onChange={(e) => patchViewFilter({ dateFrom: e.target.value })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white [color-scheme:dark] focus:border-white/25 focus:outline-none"
                title="Due from"
              />
              <input
                type="date"
                value={viewFilter.dateTo}
                onChange={(e) => patchViewFilter({ dateTo: e.target.value })}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white [color-scheme:dark] focus:border-white/25 focus:outline-none"
                title="Due to"
              />
              <div className="flex gap-2">
                <button onClick={() => void cleanToday()} className="btn-ghost flex-1 px-3 py-2">
                  Clean today
                </button>
                <button
                  onClick={() => setViewFilter(DEFAULT_VIEW_FILTER)}
                  className="btn-ghost flex-1 px-3 py-2"
                >
                  Reset
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                value={viewName}
                onChange={(e) => setViewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveCurrentView()
                }}
                placeholder="View name"
                className="min-w-40 flex-1 rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:border-white/25 focus:outline-none"
              />
              <button
                onClick={saveCurrentView}
                disabled={!viewName.trim()}
                className="btn-ghost inline-flex items-center gap-2 px-3 py-2 disabled:opacity-40"
              >
                <Save className="h-4 w-4" />
                Save view
              </button>
              {savedViews.length > 0 && (
                <select
                  defaultValue=""
                  onChange={(e) => {
                    applySavedView(e.target.value)
                    e.currentTarget.value = ''
                  }}
                  className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white focus:border-white/25 focus:outline-none"
                >
                  <option value="" className="bg-neutral-900">
                    Saved views
                  </option>
                  {savedViews.map((view) => (
                    <option key={view.id} value={view.id} className="bg-neutral-900">
                      {view.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div className="surface-card animate-fade-in p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/85">
              <Bot className="h-4 w-4 text-white/55" />
              Agent queue
            </div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px_auto]">
              <input
                value={agentPrompt}
                onChange={(e) => setAgentPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') startAgentTask()
                }}
                placeholder="Describe the task for an agent"
                className="input-field"
              />
              <select
                value={agentProvider}
                onChange={(e) => setAgentProvider(e.target.value as TaskAgentProvider)}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="pi" className="bg-neutral-900">
                  Pi/Omi
                </option>
                <option value="claude-acp" className="bg-neutral-900">
                  Claude
                </option>
              </select>
              <button
                onClick={startAgentTask}
                disabled={!agentPrompt.trim()}
                className="btn-primary inline-flex items-center gap-2 px-4 py-2 disabled:opacity-40"
              >
                <Play className="h-4 w-4" />
                Run
              </button>
            </div>
            {agentRuns.length > 0 && (
              <ul className="mt-3 space-y-2">
                {agentRuns.slice(0, 5).map((run) => (
                  <AgentRunRow key={run.id} run={run} />
                ))}
              </ul>
            )}
          </div>

          <div className="surface-card mt-4 animate-fade-in p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/85">
              <MessageSquare className="h-4 w-4 text-white/55" />
              Task chat
            </div>
            <div className="mb-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
              <select
                value={selectedTaskChatId ?? ''}
                onChange={(e) => setSelectedTaskChatId(e.target.value || null)}
                className="rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white focus:border-white/25 focus:outline-none"
              >
                <option value="" className="bg-neutral-900">
                  Select a task
                </option>
                {items.map((item) => (
                  <option key={item.id} value={item.id} className="bg-neutral-900">
                    {item.description}
                  </option>
                ))}
              </select>
              {selectedTask && (
                <button
                  onClick={() => {
                    setEditDraft(selectedTask.description)
                    setEditingId(selectedTask.id)
                  }}
                  className="btn-ghost px-3 py-2"
                >
                  Edit task
                </button>
              )}
            </div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]">
              <input
                value={taskChatDraft}
                onChange={(e) => setTaskChatDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') startTaskChat()
                }}
                placeholder={
                  selectedTask ? 'Ask an agent about this task' : 'Select a task to chat about'
                }
                disabled={!selectedTask}
                className="input-field disabled:opacity-45"
              />
              <button
                onClick={startTaskChat}
                disabled={!selectedTask || !taskChatDraft.trim()}
                className="btn-primary inline-flex items-center gap-2 px-4 py-2 disabled:opacity-40"
              >
                <Play className="h-4 w-4" />
                Ask
              </button>
            </div>
          </div>
        </div>

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
