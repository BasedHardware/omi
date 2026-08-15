import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
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
  Flag,
  Sun,
  CheckSquare,
  Square
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { fetchAllActionItems } from '../lib/actionItems'
import { PageHeader } from '../components/layout/PageHeader'
import { TasksGoalsToggle } from '../components/layout/TasksGoalsToggle'
import { EmptyState } from '../components/ui/EmptyState'
import { TaskDetailPanel } from '../components/tasks/TaskDetailPanel'
import { TaskChatPanel } from '../components/tasks/TaskChatPanel'
import {
  EMPTY_SELECTION,
  applySelectionClick,
  clearSelection,
  selectAll,
  type TaskSelection
} from '../lib/taskSelection'
import {
  bulkDelete,
  bulkReschedule,
  bulkSetCompleted,
  describeBulkResult
} from '../lib/taskBulkOps'
import { PRIORITY_TINT, normalizePriority, todayDueAtMs } from '../lib/taskFields'
import { toast } from '../lib/toast'
import type { ActionItemRecord } from '../../../shared/types'
import type { Conversation as CloudConversation } from '../lib/omiApi.generated'

type ConvMeta = { title: string; emoji?: string }

// Module-level cache so navigating away and back is instant; refresh re-fetches.
// Reads are already local-first-instant (SQLite via IPC); the cache just avoids a
// skeleton flash on revisit. `onTasksChanged` keeps it fresh, so we no longer keep
// an optimistic mirror here — main owns optimism + revert-on-failure.
const cache = {
  items: null as ActionItemRecord[] | null,
  convs: {} as Record<string, ConvMeta>,
  loaded: false
}

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

// Best-effort conversation title/emoji map for the per-task source links. A failed
// conversations call still leaves the map empty (tasks come from the local store).
async function fetchConvMeta(): Promise<Record<string, ConvMeta>> {
  const res = await omiApi.get<CloudConversation[]>('/v1/conversations', {
    params: { limit: 200, offset: 0, statuses: 'completed,processing' }
  })
  const map: Record<string, ConvMeta> = {}
  if (Array.isArray(res.data)) {
    for (const c of res.data) {
      map[c.id] = {
        title: c.structured?.title || 'Untitled',
        emoji: c.structured?.emoji ?? undefined
      }
    }
  }
  return map
}

const DAY = 86_400_000

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

// Native <input type="date"> works in local YYYY-MM-DD; convert both ways while
// pinning the time to local noon so the day never slips across time zones. The
// store speaks epoch-ms, so these bridge ms ↔ the date input's string.
function msToDateInput(ms?: number | null): string {
  if (ms == null) return ''
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function dateInputToMs(v: string): number | null {
  if (!v) return null
  const d = new Date(`${v}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d.getTime()
}

function formatDue(ms: number): string {
  const d = new Date(ms)
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

type Bucket = 'today' | 'tomorrow' | 'later' | 'nodate'

// Four due-date buckets, matching Mac's TaskCategory (Today · Tomorrow · Later ·
// No Deadline). Overdue tasks fold into Today — there is no separate Overdue
// section — mirroring Mac's `categoryFor` (`dueAt < startOfTomorrow → .today`,
// TasksPage.swift) and the Flutter app's grouping.
function bucketOf(t: ActionItemRecord): Bucket {
  if (t.dueAt == null) return 'nodate'
  const due = startOfDay(t.dueAt)
  const today = startOfDay(Date.now())
  if (due <= today) return 'today' // overdue + today
  // Tomorrow's local start-of-day via Date.setDate (which handles DST shifts and
  // month/year boundaries). A fixed `today + DAY` offset is 23h/25h wrong on the
  // two DST-transition days each year, which would mis-bucket a "due tomorrow"
  // task into Later.
  const tomorrow = new Date(today)
  tomorrow.setDate(tomorrow.getDate() + 1)
  if (due === startOfDay(tomorrow.getTime())) return 'tomorrow'
  return 'later'
}

// A task whose due date is before today. Independent of bucketing (overdue rows
// live in the Today bucket) so the date badge can still flag them in rose.
function isOverdue(t: ActionItemRecord): boolean {
  return !t.completed && t.dueAt != null && startOfDay(t.dueAt) < startOfDay(Date.now())
}

const BUCKET_ORDER: Bucket[] = ['today', 'tomorrow', 'later', 'nodate']
const BUCKET_LABEL: Record<Bucket, string> = {
  today: 'Today',
  tomorrow: 'Tomorrow',
  later: 'Later',
  nodate: 'No due date'
}

// Priority filter chips (mac parity: TaskFilterTag.priorityHigh/Medium/Low —
// exact, case-sensitive match on the stored value, like mac's tag matching).
type PriorityFilter = 'any' | 'high' | 'medium' | 'low'

// Move the keyboard selection across the flat, rendered task order. Clamps at the
// ends (no wrap) and, when nothing is selected yet, Down picks the first row and Up
// the last — mirroring Mac's `moveSelection` (TasksPage.swift).
function moveSelection(
  nav: ActionItemRecord[],
  currentId: number | null,
  direction: 1 | -1
): number | null {
  if (nav.length === 0) return currentId
  const idx = currentId == null ? -1 : nav.findIndex((t) => t.id === currentId)
  if (idx === -1) return direction > 0 ? nav[0].id : nav[nav.length - 1].id
  const next = Math.min(Math.max(idx + direction, 0), nav.length - 1)
  return nav[next].id
}

export function Tasks(): React.JSX.Element {
  const [items, setItems] = useState<ActionItemRecord[]>(cache.items ?? [])
  const [convs, setConvs] = useState<Record<string, ConvMeta>>(cache.convs)
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter] = useState<'all' | 'open' | 'done'>('open')
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>('any')

  // The Today-section composer (mac parity: #11600's showsTodayComposer). Text
  // only — Enter always creates the task due today (23:59 local) and the composer
  // stays open for back-to-back entry. Hidden in the done view and while selecting.
  const [composing, setComposing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [dueEditingId, setDueEditingId] = useState<number | null>(null)
  const [busy, setBusy] = useState<Set<number>>(new Set())

  // Trailing panels — mutually exclusive, like mac's detail/chat exclusivity.
  const [detailTaskId, setDetailTaskId] = useState<number | null>(null)
  const [chatTaskId, setChatTaskId] = useState<number | null>(null)

  // Multi-select mode (mac parity: TaskMultiSelection). An explicit mode, entered
  // by the Select toggle; row clicks then drive the selection model.
  const [selectMode, setSelectMode] = useState(false)
  const [selection, setSelection] = useState<TaskSelection>(EMPTY_SELECTION)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [rescheduleOpen, setRescheduleOpen] = useState(false)

  // Keyboard-navigation selection (mac parity). The highlighted row a keyboard
  // user is driving; independent of the mouse hover/edit state above.
  const [keyboardSelectedTaskId, setKeyboardSelectedTaskId] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // Re-read the local task store. Called on mount, on every `onTasksChanged`
  // (optimistic write OR a background sync landing), and on manual refresh.
  const readTasks = useCallback(async (): Promise<void> => {
    try {
      const list = await fetchAllActionItems()
      cache.items = list
      cache.loaded = true
      setItems(list)
      setError(null)
    } catch (e) {
      setError(apiError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const readConvs = useCallback(async (): Promise<void> => {
    try {
      const map = await fetchConvMeta()
      cache.convs = map
      setConvs(map)
    } catch {
      // Source-link labels are best-effort; tasks render without them.
    }
  }, [])

  // Cold load: local rows (instant) + the conversation title map. Both loaders do
  // their setState after an await, so nest them in a callback rather than invoking
  // them straight from the effect body (their state updates are deferred, not sync).
  useEffect(() => {
    void (async () => {
      await readTasks()
      await readConvs()
    })()
  }, [readTasks, readConvs])

  // Local-first freshness: main fires `onTasksChanged` on every optimistic write
  // and whenever a background sync lands, so a single subscription replaces the old
  // mount-refetch loop, window-focus refetch, and create→reload dance.
  useEffect(() => window.omi.onTasksChanged(() => void readTasks()), [readTasks])

  // A background task mutation failed (e.g. a delete that the server rejected and
  // whose row main restored). The delete IPC resolves before its HTTP call, so the
  // deleteItem catch below never sees this — main signals it out-of-band. Toast it
  // so the reappearing row is explained instead of looking like a silent glitch.
  useEffect(
    () => window.omi.onTasksOpFailed((failure) => toast(failure.message, { tone: 'error' })),
    []
  )

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await window.omi.tasksReconcile().catch(() => {})
    await Promise.all([readTasks(), readConvs()])
    setRefreshing(false)
  }

  const markBusy = (id: number, on: boolean): void =>
    setBusy((s) => {
      const next = new Set(s)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  // Thin mutations: main owns the optimistic write + revert-on-failure and fires
  // `onTasksChanged`, which re-reads the list. All mutations require a synced row
  // (non-null backendId); the caller gates on that before invoking these.
  const toggleItem = async (t: ActionItemRecord): Promise<void> => {
    if (!t.backendId) return
    markBusy(t.id, true)
    try {
      await window.omi.tasksToggle({ backendId: t.backendId, completed: !t.completed })
    } catch (e) {
      toast('Could not update task', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(t.id, false)
    }
  }

  const updateItem = async (
    t: ActionItemRecord,
    fields: Parameters<typeof window.omi.tasksUpdate>[0]['fields']
  ): Promise<void> => {
    if (!t.backendId) return
    markBusy(t.id, true)
    try {
      await window.omi.tasksUpdate({ backendId: t.backendId, fields })
    } catch (e) {
      toast('Could not update task', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(t.id, false)
    }
  }

  const deleteItem = async (t: ActionItemRecord): Promise<void> => {
    if (!t.backendId) return
    markBusy(t.id, true)
    try {
      await window.omi.tasksDelete({ backendId: t.backendId })
    } catch (e) {
      toast('Could not delete task', { tone: 'error', body: apiError(e) })
    } finally {
      markBusy(t.id, false)
    }
  }

  // Enter in the Today composer: create due TODAY (mac's todayDueAt, 23:59 local)
  // and keep the composer open for back-to-back entry (#11600's commitTodayComposer).
  const saveNew = async (): Promise<void> => {
    const text = draft.trim()
    if (!text || saving) return
    setSaving(true)
    try {
      await window.omi.tasksCreate({ description: text, dueAt: todayDueAtMs() })
      // `onTasksChanged` surfaces the new (optimistic) row — no reload needed.
      setDraft('')
    } catch (e) {
      toast('Could not create task', { tone: 'error', body: apiError(e) })
    } finally {
      setSaving(false)
    }
  }

  const commitEdit = (t: ActionItemRecord): void => {
    const text = editDraft.trim()
    setEditingId(null)
    if (text && text !== t.description) {
      void updateItem(t, { description: text })
    }
  }

  // Open the inline description editor for a row. Shared by the row's click-to-edit
  // and the keyboard Enter binding so both use the one edit-open path.
  const startEdit = (t: ActionItemRecord): void => {
    setEditDraft(t.description)
    setEditingId(t.id)
  }

  // Detail panel opening refuses while selecting (mac: openDetail is refused in
  // multi-select mode) and closes the chat panel — the two are mutually exclusive.
  const openDetail = (t: ActionItemRecord): void => {
    if (selectMode) return
    setChatTaskId(null)
    setDetailTaskId(t.id)
  }

  const openInvestigate = (t: ActionItemRecord): void => {
    setDetailTaskId(null)
    setChatTaskId(t.id)
  }

  const exitSelectMode = (): void => {
    setSelectMode(false)
    setSelection(clearSelection())
    setRescheduleOpen(false)
  }

  const openCount = useMemo(() => items.filter((t) => !t.completed).length, [items])
  const doneCount = items.length - openCount

  const matchesPriority = useCallback(
    (t: ActionItemRecord): boolean => priorityFilter === 'any' || t.priority === priorityFilter,
    [priorityFilter]
  )

  const visible = useMemo(
    () =>
      items.filter(
        (t) =>
          (filter === 'all' ? true : filter === 'open' ? !t.completed : t.completed) &&
          matchesPriority(t)
      ),
    [items, filter, matchesPriority]
  )

  // For open/all: group open items by due bucket. For done/all: a flat
  // completed list (newest first), shown after the open buckets.
  const openGroups = useMemo(() => {
    if (filter === 'done') return []
    const groups: Record<Bucket, ActionItemRecord[]> = {
      today: [],
      tomorrow: [],
      later: [],
      nodate: []
    }
    for (const t of items) {
      if (t.completed || !matchesPriority(t)) continue
      groups[bucketOf(t)].push(t)
    }
    for (const b of BUCKET_ORDER) {
      groups[b].sort((a, c) => {
        const ad = a.dueAt ?? Infinity
        const cd = c.dueAt ?? Infinity
        if (ad !== cd) return ad - cd
        return c.createdAt - a.createdAt
      })
    }
    // The Today section renders while the composer is open even when it has no
    // rows yet (#11600's rendersSection), so the composer has a home.
    return BUCKET_ORDER.filter((b) => groups[b].length > 0 || (b === 'today' && composing)).map(
      (b) => ({
        bucket: b,
        items: groups[b]
      })
    )
  }, [items, filter, matchesPriority, composing])

  const doneItems = useMemo(() => {
    if (filter === 'open') return []
    // No completed_at on the local row; updatedAt is stamped when a task is toggled
    // complete, so it's the faithful "most recently done" proxy.
    return items
      .filter((t) => t.completed && matchesPriority(t))
      .sort((a, c) => c.updatedAt - a.updatedAt)
  }, [items, filter, matchesPriority])

  // The flat keyboard-navigation order: exactly what renders, top to bottom — the
  // open buckets (in BUCKET_ORDER) followed by the completed list. Mirrors Mac's
  // `navigationOrder` (all categories concatenated).
  const navOrder = useMemo<ActionItemRecord[]>(
    () => [...openGroups.flatMap((g) => g.items), ...doneItems],
    [openGroups, doneItems]
  )

  const selectedTasks = useMemo(
    () => navOrder.filter((t) => selection.selected.has(t.id)),
    [navOrder, selection]
  )

  const runBulk = async (
    verb: string,
    op: (tasks: ActionItemRecord[]) => Promise<import('../lib/taskBulkOps').BulkResult>
  ): Promise<void> => {
    if (bulkBusy || selectedTasks.length === 0) return
    setBulkBusy(true)
    try {
      const result = await op(selectedTasks)
      toast(describeBulkResult(verb, result), {
        tone: result.failures.length > 0 ? 'error' : 'success'
      })
      if (result.failures.length === 0) exitSelectMode()
    } finally {
      setBulkBusy(false)
    }
  }

  const bulkCompleteSelected = (): Promise<void> =>
    runBulk('Completed', (tasks) => bulkSetCompleted(tasks, true))

  const bulkDeleteSelected = async (): Promise<void> => {
    if (selectedTasks.length === 0) return
    // Mac confirms first: "Delete N tasks? This cannot be undone."
    const n = selectedTasks.length
    if (!window.confirm(`Delete ${n} ${n === 1 ? 'task' : 'tasks'}? This cannot be undone.`)) return
    await runBulk('Deleted', (tasks) => bulkDelete(tasks))
  }

  const bulkRescheduleSelected = async (value: string): Promise<void> => {
    setRescheduleOpen(false)
    await runBulk('Rescheduled', (tasks) => bulkReschedule(tasks, dateInputToMs(value)))
  }

  // Scroll the keyboard-selected row into view. Runs after render, so the row for a
  // just-set id (e.g. the neighbour picked on delete) exists when we query for it.
  useEffect(() => {
    if (keyboardSelectedTaskId == null) return
    const el = scrollRef.current?.querySelector(`[data-task-id="${keyboardSelectedTaskId}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [keyboardSelectedTaskId])

  // Switching the filter can leave the selected row unrendered while it's still in
  // `items` (the filter just hides it), so `items.find` would keep resolving it and
  // Space/Enter/Ctrl+D would act on a task the user can no longer see. Drop the
  // selection on every filter change. (A sync that removes a task deletes it from
  // `items` too, so the keyboard handlers' `items.find` already bails there.)
  const changeFilter = (f: 'all' | 'open' | 'done'): void => {
    setFilter(f)
    setKeyboardSelectedTaskId(null)
    // Scope change clears the bulk selection too (mac: clearMultiSelectionForScopeChange).
    setSelection(clearSelection())
    if (f === 'done') setComposing(false)
  }

  const changePriorityFilter = (p: PriorityFilter): void => {
    setPriorityFilter(p)
    setKeyboardSelectedTaskId(null)
    setSelection(clearSelection())
  }

  // Latest values the document keydown handler reads. Kept in a ref so the listener
  // registers once (no add/remove churn) yet never sees a stale closure. The sync
  // runs in a *layout* effect: a passive effect is scheduled after the commit, so a
  // key pressed in the window between "the reloaded rows are on screen" and "the
  // passive effect ran" would be handled against the previous navOrder — an
  // arrow/Ctrl+D that silently does nothing right after the list refreshes.
  const kbd = useRef({
    navOrder,
    selectedId: keyboardSelectedTaskId,
    items,
    busy,
    composing,
    selectMode,
    selectionActive: selection.selected.size > 0,
    detailOpen: detailTaskId != null,
    chatOpen: chatTaskId != null,
    toggleItem,
    deleteItem,
    startEdit
  })
  useLayoutEffect(() => {
    kbd.current = {
      navOrder,
      selectedId: keyboardSelectedTaskId,
      items,
      busy,
      composing,
      selectMode,
      selectionActive: selection.selected.size > 0,
      detailOpen: detailTaskId != null,
      chatOpen: chatTaskId != null,
      toggleItem,
      deleteItem,
      startEdit
    }
  })

  // List-level keyboard navigation (mac parity, flat-list subset — no indent/outdent
  // since Windows has no subtask hierarchy). Guards on the same `isTyping` check
  // useKeyboardNav uses so it never hijacks typing in the edit/compose inputs, and
  // leaves plain Ctrl+digit/comma/Escape-to-home to the global handler.
  useEffect(() => {
    const isTyping = (e: KeyboardEvent): boolean => {
      const t = e.target as HTMLElement | null
      return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
    }

    const handler = (e: KeyboardEvent): void => {
      if (isTyping(e)) return
      const s = kbd.current
      // The composer owns the keyboard while open (its input autofocuses); don't run
      // list nav underneath it.
      if (s.composing) return

      const ctrl = e.ctrlKey || e.metaKey

      // Ctrl+N — open the Today composer (mac: Cmd+N → beginTopInlineCreation).
      if (ctrl && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault()
        setSelectMode(false)
        setSelection(clearSelection())
        setComposing(true)
        return
      }

      // Ctrl+A in select mode — select every rendered row (mac: Cmd+A selectAll).
      if (ctrl && (e.key === 'a' || e.key === 'A') && s.selectMode) {
        e.preventDefault()
        setSelection(selectAll(s.navOrder.map((t) => t.id)))
        return
      }

      // Ctrl+D — delete the selected task, then select a sensible neighbour.
      if (ctrl && (e.key === 'd' || e.key === 'D')) {
        if (s.selectedId == null) return
        const task = s.items.find((x) => x.id === s.selectedId)
        if (!task) return
        e.preventDefault()
        const idx = s.navOrder.findIndex((x) => x.id === s.selectedId)
        let neighbour: number | null = null
        if (idx !== -1 && s.navOrder.length > 1) {
          const nextIdx = idx + 1 < s.navOrder.length ? idx + 1 : Math.max(0, idx - 1)
          neighbour = s.navOrder[nextIdx].id
        }
        setKeyboardSelectedTaskId(neighbour)
        void s.deleteItem(task)
        return
      }

      // Leave any other Ctrl/Cmd combo (page-jump shortcuts) to the global handler.
      if (ctrl) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setKeyboardSelectedTaskId(moveSelection(s.navOrder, s.selectedId, 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setKeyboardSelectedTaskId(moveSelection(s.navOrder, s.selectedId, -1))
        return
      }
      if (e.key === ' ' || e.code === 'Space') {
        // A focused button/link/select owns Space — don't toggle the list row and
        // don't preventDefault, or we'd suppress that control's own activation.
        if ((e.target as HTMLElement | null)?.closest('button, a, select, [role="button"]')) return
        if (s.selectedId == null) return
        const task = s.items.find((x) => x.id === s.selectedId)
        if (!task) return
        e.preventDefault()
        if (s.selectMode) {
          // In select mode Space toggles selection membership (mac: toggleFocused).
          setSelection((sel) => applySelectionClick([], sel, task.id, { ctrl: true, shift: false }))
          return
        }
        void s.toggleItem(task)
        return
      }
      if (e.key === 'Enter') {
        // Same guard as Space: a focused button/link/select owns Enter.
        if ((e.target as HTMLElement | null)?.closest('button, a, select, [role="button"]')) return
        if (s.selectedId == null) return
        const task = s.items.find((x) => x.id === s.selectedId)
        // Only editable once synced and not mid-mutation — matches the row's own
        // click-to-edit gate (isBusy = busy.has(id) || !backendId).
        if (!task || !task.backendId || s.busy.has(task.id)) return
        e.preventDefault()
        s.startEdit(task)
        return
      }
      if (e.key === 'Escape') {
        // Mac's escape hierarchy (TasksPage.handleEscapeKey + handleEscape):
        // chat/detail panel → multi-select → composer (its input handles its own
        // Esc while focused) → keyboard deselect → fall through (global Esc→Home).
        if (s.chatOpen) {
          e.preventDefault()
          setChatTaskId(null)
          return
        }
        if (s.detailOpen) {
          e.preventDefault()
          setDetailTaskId(null)
          return
        }
        if (s.selectMode) {
          e.preventDefault()
          exitSelectMode()
          return
        }
        if (s.selectedId != null) {
          e.preventDefault()
          setKeyboardSelectedTaskId(null)
        }
        return
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const detailTask =
    detailTaskId != null ? (items.find((t) => t.id === detailTaskId) ?? null) : null
  const chatTask = chatTaskId != null ? (items.find((t) => t.id === chatTaskId) ?? null) : null

  const renderRow = (t: ActionItemRecord): React.JSX.Element => {
    // A freshly-created row has backendId:null for a sub-second window until its
    // background POST + markSynced lands; treat that like the in-flight busy state
    // so its controls can't fire a mutation with no backendId.
    const isBusy = busy.has(t.id) || !t.backendId
    const conv = t.conversationId ? convs[t.conversationId] : undefined
    const overdue = isOverdue(t)
    const isSelected = keyboardSelectedTaskId === t.id
    const isBulkSelected = selection.selected.has(t.id)
    const priority = normalizePriority(t.priority)
    return (
      <li
        key={t.id}
        data-task-id={t.id}
        data-selected={isSelected ? 'true' : undefined}
        data-bulk-selected={isBulkSelected ? 'true' : undefined}
        onClick={(e) => {
          if (!selectMode) return
          // Row clicks drive the selection model in select mode; controls inside
          // the row (buttons/links/inputs) keep their own behavior.
          if ((e.target as HTMLElement | null)?.closest('a, input, [data-row-control]')) return
          setSelection((sel) =>
            applySelectionClick(
              navOrder.map((x) => x.id),
              sel,
              t.id,
              { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey }
            )
          )
        }}
        className={`surface-card group flex items-start gap-3 p-4 ${
          isSelected ? 'ring-1 ring-white/40' : ''
        } ${isBulkSelected ? 'bg-white/10 ring-1 ring-white/30' : ''} ${
          selectMode ? 'cursor-pointer select-none' : ''
        }`}
      >
        {selectMode ? (
          <span
            aria-label={isBulkSelected ? 'Selected' : 'Not selected'}
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center text-white/70"
          >
            {isBulkSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
          </span>
        ) : (
          <button
            data-row-control
            onClick={() => void toggleItem(t)}
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
        )}

        <div className="min-w-0 flex-1">
          {editingId === t.id ? (
            <input
              autoFocus
              value={editDraft}
              onChange={(e) => setEditDraft(e.target.value)}
              onBlur={() => commitEdit(t)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitEdit(t)
                else if (e.key === 'Escape') setEditingId(null)
              }}
              className="w-full border-0 border-b border-white/25 bg-transparent pb-0.5 text-sm text-white focus:border-white/60 focus:outline-none focus:ring-0"
            />
          ) : (
            <button
              data-row-control
              onClick={() => {
                if (selectMode) return
                if (isBusy) return
                startEdit(t)
              }}
              title={selectMode ? undefined : 'Click to edit'}
              className={`block w-full text-left text-sm leading-relaxed ${
                t.completed ? 'text-white/40 line-through' : 'text-white/90'
              }`}
            >
              {priority && (
                <Flag
                  aria-label={`${priority} priority`}
                  className={`mr-1.5 inline h-3 w-3 align-baseline ${PRIORITY_TINT[priority]}`}
                />
              )}
              {t.description}
            </button>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
            {dueEditingId === t.id ? (
              <span className="inline-flex items-center gap-1">
                <input
                  type="date"
                  autoFocus
                  value={msToDateInput(t.dueAt)}
                  onChange={(e) => {
                    const ms = dateInputToMs(e.target.value)
                    void updateItem(t, ms != null ? { dueAt: ms } : { clearDueAt: true })
                    setDueEditingId(null)
                  }}
                  onBlur={() => setDueEditingId(null)}
                  className="rounded-md border border-white/20 bg-black/30 px-1.5 py-0.5 text-[11px] text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                />
                {t.dueAt != null && (
                  <button
                    data-row-control
                    onMouseDown={(e) => {
                      e.preventDefault()
                      void updateItem(t, { clearDueAt: true })
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
                data-row-control
                onClick={() => {
                  if (!selectMode && !isBusy) setDueEditingId(t.id)
                }}
                className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition-colors hover:bg-white/5 ${
                  t.dueAt != null
                    ? overdue
                      ? 'text-rose-300/90'
                      : 'text-white/65'
                    : 'text-white/35'
                }`}
                title="Set due date"
              >
                <Calendar className="h-3 w-3" />
                {t.dueAt != null ? formatDue(t.dueAt) : 'Set date'}
              </button>
            )}

            {conv && (
              <Link
                to={`/conversations/${t.conversationId}`}
                className="inline-flex items-center gap-1.5 truncate hover:text-white/70"
              >
                {conv.emoji && <span>{conv.emoji}</span>}
                <span className="truncate">{conv.title}</span>
              </Link>
            )}
          </div>
        </div>

        {!selectMode && (
          <button
            data-row-control
            data-testid={`task-details-${t.id}`}
            onClick={() => openDetail(t)}
            className="mt-0.5 shrink-0 rounded-md p-1 text-white/30 opacity-0 transition-all hover:bg-white/5 hover:text-white/80 group-hover:opacity-100"
            title="Task details"
            aria-label="Task details"
          >
            <ListChecks className="h-4 w-4" />
          </button>
        )}
        {!selectMode && (
          <button
            data-row-control
            onClick={() => void deleteItem(t)}
            disabled={isBusy}
            className="mt-0.5 shrink-0 rounded-md p-1 text-white/30 opacity-0 transition-all hover:bg-white/5 hover:text-rose-300/80 group-hover:opacity-100 disabled:opacity-0"
            title="Delete task"
            aria-label="Delete task"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </li>
    )
  }

  // The Today-section composer row (#11600): first row of Today, aligned with the
  // rows, text only, Enter creates due-today and keeps composing.
  const composerRow = (
    <li className="surface-card flex items-center gap-3 p-4">
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
        <Sun className="h-4 w-4 text-white/35" />
      </span>
      <input
        data-testid="tasks-composer-field"
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
          }
        }}
        placeholder="Add a task"
        disabled={saving}
        className="min-w-0 flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/35 focus:outline-none"
      />
      {saving ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-white/40" />
      ) : (
        <button
          data-testid="tasks-composer-close"
          onClick={() => {
            setComposing(false)
            setDraft('')
          }}
          className="shrink-0 rounded-md p-1 text-white/30 hover:bg-white/5 hover:text-white/70"
          aria-label="Close composer"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </li>
  )

  const showTodayComposer = composing && filter !== 'done' && !selectMode

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
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
                    onClick={() => changeFilter(f)}
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
              <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
                {(['any', 'high', 'medium', 'low'] as const).map((p) => (
                  <button
                    key={p}
                    data-testid={`tasks-priority-filter-${p}`}
                    onClick={() => changePriorityFilter(p)}
                    className={`rounded-xl px-2.5 py-1.5 text-xs font-medium capitalize transition-all duration-200 ${
                      priorityFilter === p
                        ? 'bg-white/15 text-white'
                        : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                    }`}
                    title={p === 'any' ? 'Any priority' : `${p} priority`}
                  >
                    {p === 'any' ? 'Any' : p}
                  </button>
                ))}
              </div>
              <button
                data-testid="tasks-select-toggle"
                onClick={() => {
                  if (selectMode) exitSelectMode()
                  else {
                    setComposing(false)
                    setDetailTaskId(null)
                    setChatTaskId(null)
                    setSelectMode(true)
                  }
                }}
                className={`px-3 py-2 ${selectMode ? 'btn-primary' : 'btn-ghost'}`}
                title={selectMode ? 'Done selecting' : 'Select tasks'}
              >
                {selectMode ? 'Done' : 'Select'}
              </button>
              <button
                onClick={() => {
                  if (selectMode) return
                  setComposing((c) => !c)
                }}
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

        {selectMode && (
          <div
            data-testid="tasks-selection-bar"
            className="flex items-center gap-2 border-b border-white/10 bg-black/25 px-6 py-2 lg:px-10"
          >
            <span data-testid="tasks-selected-count" className="text-xs text-white/70">
              {selectedTasks.length} selected
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button
                data-testid="tasks-bulk-complete"
                onClick={() => void bulkCompleteSelected()}
                disabled={bulkBusy || selectedTasks.length === 0}
                className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-40"
              >
                <Check className="h-3.5 w-3.5" />
                Complete
              </button>
              {rescheduleOpen ? (
                <input
                  type="date"
                  autoFocus
                  data-testid="tasks-bulk-reschedule-date"
                  onChange={(e) => void bulkRescheduleSelected(e.target.value)}
                  onBlur={() => setRescheduleOpen(false)}
                  className="rounded-md border border-white/20 bg-black/30 px-2 py-1 text-xs text-white [color-scheme:dark] focus:border-white/50 focus:outline-none"
                />
              ) : (
                <button
                  data-testid="tasks-bulk-reschedule"
                  onClick={() => setRescheduleOpen(true)}
                  disabled={bulkBusy || selectedTasks.length === 0}
                  className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-40"
                >
                  <Calendar className="h-3.5 w-3.5" />
                  Reschedule
                </button>
              )}
              <button
                data-testid="tasks-bulk-delete"
                onClick={() => void bulkDeleteSelected()}
                disabled={bulkBusy || selectedTasks.length === 0}
                className="btn-ghost px-3 py-1.5 text-xs text-rose-300/80 hover:text-rose-300 disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete {selectedTasks.length > 0 ? selectedTasks.length : ''}
              </button>
            </div>
          </div>
        )}

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
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

          {error && (
            <div className="surface-panel mb-5 px-4 py-3 text-sm text-white/60">
              <p className="text-white/80">Couldn’t load your tasks.</p>
              <div className="mt-2 flex items-center gap-3">
                <button
                  onClick={() => {
                    setError(null)
                    setLoading(true)
                    void readTasks()
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

          {!loading && !error && items.length === 0 && !showTodayComposer && (
            <EmptyState
              icon={ListChecks}
              title="No tasks yet"
              description="Action items from your conversations show up here, alongside any tasks you add. Click New to create one."
            />
          )}

          {!loading && items.length > 0 && visible.length === 0 && !showTodayComposer && (
            <div className="flex flex-col items-center justify-center pt-16 text-center text-white/55">
              <Check className="mb-3 h-10 w-10 opacity-40" />
              <p className="text-sm">All caught up.</p>
            </div>
          )}

          {!loading && (openGroups.length > 0 || doneItems.length > 0 || showTodayComposer) && (
            <div className="mx-auto max-w-3xl space-y-6">
              {openGroups.map((g) => (
                <section key={g.bucket}>
                  <h2 className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40">
                    {BUCKET_LABEL[g.bucket]}
                    <span className="text-white/25">{g.items.length}</span>
                  </h2>
                  <ul className="space-y-2">
                    {g.bucket === 'today' && showTodayComposer && composerRow}
                    {g.items.map(renderRow)}
                  </ul>
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

      {chatTask ? (
        <TaskChatPanel
          key={chatTask.backendId ?? chatTask.id}
          task={chatTask}
          onClose={() => setChatTaskId(null)}
        />
      ) : detailTask ? (
        <TaskDetailPanel
          task={detailTask}
          conversationTitle={
            detailTask.conversationId ? convs[detailTask.conversationId]?.title : undefined
          }
          busy={busy.has(detailTask.id) || !detailTask.backendId}
          hasChat={!!detailTask.backendId}
          onClose={() => setDetailTaskId(null)}
          onToggle={(t) => void toggleItem(t)}
          onEdit={(t) => {
            setDetailTaskId(null)
            startEdit(t)
          }}
          onDelete={(t) => {
            setDetailTaskId(null)
            void deleteItem(t)
          }}
          onInvestigate={openInvestigate}
          onPriorityChange={(t, p) => void updateItem(t, { priority: p })}
        />
      ) : null}
    </div>
  )
}
