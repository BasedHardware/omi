import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ListChecks, Check, RefreshCw, Plus, Trash2, Calendar, X, Loader2, MessageCircle, Send, RotateCcw, ChevronDown, ChevronUp
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { toast } from '../lib/toast'
import { useAppState } from '../state/AppStateProvider'
import { ChatMessages } from '../components/chat/ChatMessages'
import { TaskDetailModal, TaskInfoButton } from '../components/tasks/TaskDetailModal'
import { DailyTaskSheet } from '../components/tasks/DailyTaskSheet'
import { cn } from '../lib/utils'
import type { ActionItem } from '../components/tasks/TaskDetailModal'

type ConvMeta = { title: string; emoji?: string }

type CloudConversation = {
  id: string
  title?: string | null
  structured?: { title?: string | null; emoji?: string | null } | null
}

const cache = {
  items: null as ActionItem[] | null,
  convs: {} as Record<string, ConvMeta>,
  loaded: false
}

function writeItemsCache(list: ActionItem[]): void { cache.items = list }

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

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
    month: 'short', day: 'numeric',
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
  overdue: 'Overdue', today: 'Today', tomorrow: 'Tomorrow', upcoming: 'Upcoming', nodate: 'No due date'
}

// ── Rich filter system — mirrors macOS TaskFilterTag ─────────────────────────
type FilterGroup = 'status' | 'date' | 'source' | 'priority' | 'category'

type FilterTag = {
  id: string
  group: FilterGroup
  label: string
}

const FILTER_TAGS: FilterTag[] = [
  // Status
  { id: 'open', group: 'status', label: 'Open' },
  { id: 'done', group: 'status', label: 'Done' },
  // Date
  { id: 'last7days', group: 'date', label: 'Last 7 Days' },
  // Source
  { id: 'from-conv', group: 'source', label: 'From Conversation' },
  { id: 'manual', group: 'source', label: 'Manual' },
  // Priority
  { id: 'priority-high', group: 'priority', label: 'High Priority' },
  { id: 'priority-medium', group: 'priority', label: 'Medium Priority' },
  { id: 'priority-low', group: 'priority', label: 'Low Priority' },
  // Category
  { id: 'cat-work', group: 'category', label: 'Work' },
  { id: 'cat-personal', group: 'category', label: 'Personal' },
  { id: 'cat-feature', group: 'category', label: 'Feature' },
  { id: 'cat-bug', group: 'category', label: 'Bug' },
  { id: 'cat-code', group: 'category', label: 'Code' },
  { id: 'cat-research', group: 'category', label: 'Research' },
  { id: 'cat-communication', group: 'category', label: 'Communication' },
  { id: 'cat-finance', group: 'category', label: 'Finance' },
  { id: 'cat-health', group: 'category', label: 'Health' },
  { id: 'cat-other', group: 'category', label: 'Other' },
]

const GROUP_LABELS: Record<FilterGroup, string> = {
  status: 'Status', date: 'Date', source: 'Source', priority: 'Priority', category: 'Category'
}

function applyFilters(items: ActionItem[], active: Set<string>): ActionItem[] {
  if (active.size === 0) return items.filter((t) => !t.completed) // default: open only
  // AND across groups, OR within group
  const byGroup = new Map<FilterGroup, string[]>()
  for (const id of active) {
    const tag = FILTER_TAGS.find((t) => t.id === id)
    if (!tag) continue
    if (!byGroup.has(tag.group)) byGroup.set(tag.group, [])
    byGroup.get(tag.group)!.push(id)
  }
  return items.filter((item) => {
    for (const [, ids] of byGroup) {
      const pass = ids.some((id) => matchFilter(item, id))
      if (!pass) return false
    }
    return true
  })
}

function matchFilter(item: ActionItem, filterId: string): boolean {
  switch (filterId) {
    case 'open': return !item.completed
    case 'done': return item.completed
    case 'last7days': {
      const ts = new Date(item.created_at ?? 0).getTime()
      return Date.now() - ts < 7 * DAY
    }
    case 'from-conv': return !!item.conversation_id
    case 'manual': return !item.conversation_id
    case 'priority-high': return item.priority === 'high'
    case 'priority-medium': return item.priority === 'medium'
    case 'priority-low': return item.priority === 'low'
    case 'cat-work': return item.category?.toLowerCase() === 'work'
    case 'cat-personal': return item.category?.toLowerCase() === 'personal'
    case 'cat-feature': return item.category?.toLowerCase() === 'feature'
    case 'cat-bug': return item.category?.toLowerCase() === 'bug'
    case 'cat-code': return item.category?.toLowerCase() === 'code'
    case 'cat-research': return item.category?.toLowerCase() === 'research'
    case 'cat-communication': return item.category?.toLowerCase() === 'communication'
    case 'cat-finance': return item.category?.toLowerCase() === 'finance'
    case 'cat-health': return item.category?.toLowerCase() === 'health'
    case 'cat-other': return item.category?.toLowerCase() === 'other' || (!!item.category && !['work','personal','feature','bug','code','research','communication','finance','health'].includes(item.category.toLowerCase()))
    default: return true
  }
}

function FilterPanel({
  active,
  onToggle,
  onClear
}: {
  active: Set<string>
  onToggle: (id: string) => void
  onClear: () => void
}): React.JSX.Element {
  const groups = Array.from(new Set(FILTER_TAGS.map((t) => t.group))) as FilterGroup[]
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3 space-y-2">
      {groups.map((group) => (
        <div key={group} className="flex items-center gap-2 flex-wrap">
          <span className="w-20 shrink-0 text-[10px] font-semibold uppercase tracking-wider text-white/30">
            {GROUP_LABELS[group]}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {FILTER_TAGS.filter((t) => t.group === group).map((tag) => (
              <button
                key={tag.id}
                onClick={() => onToggle(tag.id)}
                className={cn(
                  'rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-all',
                  active.has(tag.id)
                    ? 'border-[color:var(--accent)]/50 bg-[color:var(--accent)]/15 text-[color:var(--accent)]'
                    : 'border-white/[0.08] bg-white/[0.03] text-white/45 hover:border-white/20 hover:text-white/70'
                )}
              >
                {tag.label}
              </button>
            ))}
          </div>
        </div>
      ))}
      {active.size > 0 && (
        <div className="flex justify-end pt-1">
          <button onClick={onClear} className="text-[11px] text-white/35 hover:text-white/70 transition-colors">
            Clear filters
          </button>
        </div>
      )}
    </div>
  )
}

function TaskChatPanel({ onClose }: { onClose: () => void }): React.JSX.Element {
  const { chat } = useAppState()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [chat.history])
  const send = (): void => {
    const text = input.trim()
    if (!text || chat.sending) return
    setInput('')
    void chat.send(text)
  }
  return (
    <div className="flex w-80 shrink-0 flex-col border-l border-white/[0.07] bg-[#070707] animate-fade-in">
      <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <span className="text-sm font-semibold text-white/80">Chat with Omi</span>
        <button onClick={onClose} className="rounded-lg p-1 text-white/40 hover:bg-white/[0.06] hover:text-white/70">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {chat.history.length === 0 ? (
          <div className="mt-10 px-2 text-center text-xs text-white/30 leading-relaxed">
            Ask Omi about your tasks, deadlines, or priorities.
          </div>
        ) : (
          <ChatMessages messages={chat.history} sending={chat.sending} variant="main" />
        )}
      </div>
      <div className="shrink-0 border-t border-white/[0.06] px-3 py-2.5">
        <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-2.5 py-1.5">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask about tasks…"
            className="flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none"
          />
          <button onClick={send} disabled={chat.sending || !input.trim()} className="shrink-0 rounded-lg p-1.5 text-white/50 transition-colors hover:text-white/90 disabled:opacity-30">
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function Tasks(): React.JSX.Element {
  const [items, setItems] = useState<ActionItem[]>(cache.items ?? [])
  const [convs, setConvs] = useState<Record<string, ConvMeta>>(cache.convs)
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Filter state
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set())
  const [filtersOpen, setFiltersOpen] = useState(false)

  const [chatOpen, setChatOpen] = useState(false)

  // Compose new task
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [draftDue, setDraftDue] = useState('')
  const [saving, setSaving] = useState(false)

  // Inline row editing
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [dueEditingId, setDueEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState<Set<string>>(new Set())

  // Detail modal
  const [detailTask, setDetailTask] = useState<ActionItem | null>(null)

  // Daily task sheet
  const [showDailySheet, setShowDailySheet] = useState(false)

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
        if (!cancelled) { setItems(r.items); setConvs(r.convs) }
      } catch (e) {
        if (!cancelled) setError(apiError(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  const markBusy = (id: string, on: boolean): void =>
    setBusy((s) => { const next = new Set(s); if (on) next.add(id); else next.delete(id); return next })

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

  const saveNew = async (description: string, dueAt?: string | null, priority?: ActionItem['priority']): Promise<void> => {
    if (!description || saving) return
    setSaving(true)
    try {
      await omiApi.post('/v1/action-items', {
        description,
        ...(dueAt ? { due_at: dueAt } : {}),
        ...(priority ? { priority } : {})
      })
      await load()
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
    if (text && original && text !== original.description) void updateItem(id, { description: text })
  }

  const toggleFilter = (id: string): void => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const visible = useMemo(() => applyFilters(items, activeFilters), [items, activeFilters])

  // Group open items by due bucket; show done items flat below
  const hasStatusFilter = activeFilters.has('open') || activeFilters.has('done') || activeFilters.size === 0
  const showOpen = activeFilters.size === 0 || activeFilters.has('open') || (!activeFilters.has('done'))
  const showDone = activeFilters.has('done')

  const openGroups = useMemo(() => {
    if (showDone && !showOpen) return []
    const openItems = visible.filter((t) => !t.completed)
    const groups: Record<Bucket, ActionItem[]> = { overdue: [], today: [], tomorrow: [], upcoming: [], nodate: [] }
    for (const t of openItems) groups[bucketOf(t)].push(t)
    for (const b of BUCKET_ORDER) {
      groups[b].sort((a, c) => {
        const ad = a.due_at ? new Date(a.due_at).getTime() : Infinity
        const cd = c.due_at ? new Date(c.due_at).getTime() : Infinity
        if (ad !== cd) return ad - cd
        return (new Date(c.created_at ?? 0).getTime() || 0) - (new Date(a.created_at ?? 0).getTime() || 0)
      })
    }
    return BUCKET_ORDER.filter((b) => groups[b].length > 0).map((b) => ({ bucket: b, items: groups[b] }))
  }, [visible, showOpen, showDone])

  const doneItems = useMemo(() => {
    if (!showDone && activeFilters.size > 0 && !activeFilters.has('done')) return []
    return visible
      .filter((t) => t.completed)
      .sort((a, c) =>
        (new Date(c.completed_at ?? c.created_at ?? 0).getTime() || 0) -
        (new Date(a.completed_at ?? a.created_at ?? 0).getTime() || 0)
      )
  }, [visible, showDone, activeFilters])

  const openCount = useMemo(() => items.filter((t) => !t.completed).length, [items])
  const doneCount = items.length - openCount

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
          className={cn(
            'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all duration-200',
            t.completed ? 'border-white/30 bg-white/15 text-white' : 'border-white/20 hover:border-white/45',
            isBusy && 'opacity-50'
          )}
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
              onClick={() => { setEditDraft(t.description); setEditingId(t.id) }}
              title="Click to edit"
              className={cn('block w-full text-left text-sm leading-relaxed', t.completed ? 'text-white/40 line-through' : 'text-white/90')}
            >
              {t.description}
            </button>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
            {/* Priority badge */}
            {t.priority && (
              <span className={cn(
                'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                t.priority === 'high' ? 'bg-red-500/15 text-red-400' :
                t.priority === 'medium' ? 'bg-orange-500/15 text-orange-400' :
                'bg-blue-500/15 text-blue-400'
              )}>
                {t.priority}
              </span>
            )}
            {/* Category badge */}
            {t.category && (
              <span className="rounded-full bg-white/[0.05] px-1.5 py-0.5 text-[10px] text-white/40">
                {t.category}
              </span>
            )}
            {/* Due date */}
            {dueEditingId === t.id ? (
              <span className="inline-flex items-center gap-1">
                <input
                  type="date"
                  autoFocus
                  value={toDateInputValue(t.due_at)}
                  onChange={(e) => { void updateItem(t.id, { due_at: dateInputToIso(e.target.value) }); setDueEditingId(null) }}
                  onBlur={() => setDueEditingId(null)}
                  className="rounded-md border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                />
                {t.due_at && (
                  <button
                    onMouseDown={(e) => { e.preventDefault(); void updateItem(t.id, { due_at: null }); setDueEditingId(null) }}
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
                className={cn(
                  'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5',
                  t.due_at ? (overdue ? 'text-rose-300/90' : 'text-white/65') : 'text-white/35'
                )}
                title="Set due date"
              >
                <Calendar className="h-3 w-3" />
                {t.due_at ? formatDue(t.due_at) : 'Set date'}
              </button>
            )}

            {conv && (
              <Link to={`/conversations/${t.conversation_id}`} className="inline-flex items-center gap-1.5 truncate hover:text-white/70">
                {conv.emoji && <span>{conv.emoji}</span>}
                <span className="truncate">{conv.title}</span>
              </Link>
            )}
          </div>
        </div>

        {/* Info button */}
        <TaskInfoButton onClick={() => setDetailTask(t)} />

        {/* Delete button */}
        <button
          onClick={() => void deleteItem(t.id)}
          className="mt-0.5 shrink-0 rounded-md p-1 text-white/30 opacity-0 transition-all hover:bg-white/5 hover:text-rose-300/80 group-hover:opacity-100"
          title="Delete task"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </li>
    )
  }

  const activeFilterCount = activeFilters.size

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Tasks"
        titleSlot={<TasksGoalsToggle />}
        subtitle={loading ? 'Loading…' : `${openCount} open · ${doneCount} done`}
        actions={
          <div className="flex items-center gap-2">
            {/* Filter toggle */}
            <button
              onClick={() => setFiltersOpen((v) => !v)}
              className={cn(
                'btn-ghost px-3 py-2 gap-1.5',
                filtersOpen || activeFilterCount > 0 ? 'bg-white/10 text-white' : ''
              )}
              title="Filter tasks"
            >
              {filtersOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              Filter
              {activeFilterCount > 0 && (
                <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-[color:var(--accent)] px-1 text-[10px] font-bold text-white">
                  {activeFilterCount}
                </span>
              )}
            </button>
            {/* Daily task */}
            <button
              onClick={() => setShowDailySheet(true)}
              className="btn-ghost px-3 py-2 gap-1.5"
              title="Create a daily repeating task"
            >
              <RotateCcw className="h-4 w-4" />
              Daily
            </button>
            <button onClick={() => setComposing((c) => !c)} className="btn-primary px-3 py-2" title="Add a task">
              <Plus className="h-4 w-4" />
              New
            </button>
            <button onClick={onRefresh} disabled={refreshing || loading} className="btn-ghost px-3 py-2 disabled:opacity-50" title="Refresh">
              <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
            </button>
            <button onClick={() => setChatOpen((c) => !c)} title="Chat with Omi about tasks" className={cn('btn-ghost px-3 py-2', chatOpen ? 'bg-white/10 text-white' : '')}>
              <MessageCircle className="h-4 w-4" />
            </button>
          </div>
        }
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
          {/* Filter panel */}
          {filtersOpen && (
            <div className="mx-auto mb-5 max-w-3xl">
              <FilterPanel active={activeFilters} onToggle={toggleFilter} onClear={() => setActiveFilters(new Set())} />
            </div>
          )}

          {composing && (
            <div className="mx-auto mb-5 max-w-3xl">
              <div className="surface-card animate-fade-in p-4">
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); void saveNew(draft.trim(), dateInputToIso(draftDue)).then(() => { setComposing(false); setDraft(''); setDraftDue('') }) }
                    else if (e.key === 'Escape') { setComposing(false); setDraft(''); setDraftDue('') }
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
                  <button onClick={() => { setComposing(false); setDraft(''); setDraftDue('') }} className="btn-ghost ml-auto px-3 py-2" disabled={saving}>Cancel</button>
                  <button
                    onClick={() => void saveNew(draft.trim(), dateInputToIso(draftDue)).then(() => { setComposing(false); setDraft(''); setDraftDue('') })}
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
            <EmptyState icon={ListChecks} title="No tasks yet" description="Action items from your conversations show up here, alongside any tasks you add." />
          )}

          {!loading && items.length > 0 && visible.length === 0 && (
            <div className="flex flex-col items-center justify-center pt-16 text-center text-white/55">
              <Check className="mb-3 h-10 w-10 opacity-40" />
              <p className="text-sm">No tasks match the current filters.</p>
              <button onClick={() => setActiveFilters(new Set())} className="mt-2 text-xs text-[color:var(--accent)] hover:underline">Clear filters</button>
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
        {chatOpen && <TaskChatPanel onClose={() => setChatOpen(false)} />}
      </div>

      {/* Task detail modal */}
      {detailTask && (
        <TaskDetailModal
          task={detailTask}
          convMeta={detailTask.conversation_id ? convs[detailTask.conversation_id] : undefined}
          onClose={() => setDetailTask(null)}
          onToggleComplete={(id, done) => void updateItem(id, { completed: done })}
          onDelete={(id) => { void deleteItem(id) }}
        />
      )}

      {/* Daily task sheet */}
      {showDailySheet && (
        <DailyTaskSheet
          onClose={() => setShowDailySheet(false)}
          onCreate={async (description, priority) => {
            await saveNew(description, null, priority)
          }}
        />
      )}
    </div>
  )
}
