import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  CalendarDays,
  Check,
  CheckSquare,
  Folder,
  GanttChartSquare,
  LayoutList,
  MessageSquare,
  Mic,
  Radio,
  Search,
  Share2,
  Star,
  Trash2
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import {
  conversationsCache,
  subscribeConversations,
  subscribeCloudRefresh,
  invalidateConversationsCache,
  getPendingConversations,
  reconcilePending,
  type ConversationRow
} from '../lib/pageCache'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import type { LocalConversation } from '../../../shared/types'

// --- Types ---

type CloudConversation = {
  id: string
  title?: string | null
  overview?: string | null
  created_at?: string
  finished_at?: string
  status?: string
  starred?: boolean
  transcript_segments?: { text: string }[]
  structured?: {
    title?: string | null
    emoji?: string | null
  } | null
}

type FolderItem = {
  id: string
  name: string
  color: string
  is_system: boolean
  conversation_count: number
}

type FilterKind = 'all' | 'chat' | 'recording' | 'starred'
type DateFilter = 'all' | 'today' | 'week' | 'month'

const DATE_FILTER_LABELS: Record<DateFilter, string> = {
  all: 'All time',
  today: 'Today',
  week: 'This week',
  month: 'This month'
}

// --- Helpers ---

function summarize(segments: { text: string }[] | undefined): string {
  if (!segments || segments.length === 0) return ''
  return segments
    .map((s) => s.text)
    .filter(Boolean)
    .join(' ')
}

function localToRow(c: LocalConversation): ConversationRow {
  const isChat = c.kind === 'chat'
  const rawPreview = isChat
    ? (c.messages?.find((m) => m.role === 'user')?.content ?? '')
    : c.transcript
  const preview = rawPreview
    ? rawPreview.slice(0, 200) + (rawPreview.length > 200 ? '…' : '')
    : isChat
      ? '(empty chat)'
      : '(empty transcript)'
  return {
    id: c.id,
    title: c.title || (isChat ? 'Chat with Omi' : 'Local recording'),
    subtitle: isChat
      ? `${new Date(c.startedAt).toLocaleString()} · ${c.messages?.length ?? 0} messages`
      : `${new Date(c.startedAt).toLocaleString()} · ${Math.round(
          (c.endedAt - c.startedAt) / 1000
        )}s`,
    preview,
    source: 'local',
    localKind: isChat ? 'chat' : 'recording',
    sortAt: c.createdAt
  }
}

/** macOS-style timestamp: "10:43 AM" today, "Yesterday, 10:43 AM", "Jan 29, 10:43 AM", "Jan 29, 2024, 10:43 AM" */
function formatConversationTs(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const yesterdayStart = todayStart - 86_400_000
  const dStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const timePart = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (dStart === todayStart) return timePart
  if (dStart === yesterdayStart) return `Yesterday, ${timePart}`
  if (d.getFullYear() === now.getFullYear())
    return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${timePart}`
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}, ${timePart}`
}

function dateFilterStart(f: DateFilter): number {
  const now = new Date()
  if (f === 'today') return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (f === 'week') {
    return new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay()).getTime()
  }
  if (f === 'month') return new Date(now.getFullYear(), now.getMonth(), 1).getTime()
  return 0
}

// --- Skeleton ---

function ConversationSkeleton(): React.JSX.Element {
  return (
    <li className="surface-card p-5">
      <div className="skeleton mb-2 h-5 w-2/5" />
      <div className="skeleton mb-3 h-3 w-1/4" />
      <div className="skeleton h-4 w-full" />
      <div className="skeleton mt-1.5 h-4 w-4/5" />
    </li>
  )
}

// --- Compact row (macOS parity: emoji badge + title + timestamp + star) ---

function CompactRow({
  r,
  onToggleStar
}: {
  r: ConversationRow
  onToggleStar: (id: string, current: boolean) => Promise<void>
}): React.JSX.Element {
  return (
    <div className="surface-card-interactive group relative flex items-center overflow-hidden">
      <Link
        to={`/conversations/${r.id}`}
        className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3"
      >
        {/* Emoji badge — matches macOS RoundedRectangle(cornerRadius: 12) emoji container */}
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.07] text-base leading-none ring-1 ring-inset ring-white/[0.06]">
          {r.emoji || '💬'}
        </div>
        {/* Title + meta */}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white/90">
            {r.title || <span className="italic text-text-tertiary">loading…</span>}
          </p>
          <p className="mt-0.5 truncate text-xs text-white/40">
            {formatConversationTs(r.sortAt)}
            {r.localKind === 'chat' && <span className="ml-1.5 text-white/25">· Chat</span>}
            {r.source === 'local' && r.localKind !== 'chat' && (
              <span className="ml-1.5 text-amber-400/60">· Not synced</span>
            )}
          </p>
        </div>
      </Link>
      {/* Star — always on right, amber when starred, reveals on hover when not */}
      {r.source === 'cloud' && (
        <button
          onClick={() => void onToggleStar(r.id, r.starred ?? false)}
          title={r.starred ? 'Unstar' : 'Star'}
          className={`mr-3 shrink-0 rounded-md p-1.5 transition-all ${
            r.starred
              ? 'text-amber-400'
              : 'text-white/0 group-hover:text-white/30 hover:!text-amber-400/70'
          }`}
        >
          <Star className="h-3.5 w-3.5" fill={r.starred ? 'currentColor' : 'none'} />
        </button>
      )}
    </div>
  )
}

// --- Main component ---

export function Conversations(): React.JSX.Element {
  const navigate = useNavigate()
  const [rows, setRows] = useState<ConversationRow[]>(conversationsCache.rows ?? [])
  const [loading, setLoading] = useState(!conversationsCache.loaded)
  const [error, setError] = useState<string | null>(conversationsCache.error)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterKind>('all')
  const [dateFilter, setDateFilter] = useState<DateFilter>('all')
  const [showDateMenu, setShowDateMenu] = useState(false)
  const [folderId, setFolderId] = useState<string | null>(null)
  const [folders, setFolders] = useState<FolderItem[]>([])
  const [compact, setCompact] = useState(() => localStorage.getItem('conv-compact') === 'true')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ ids: string[]; timeout: number } | null>(
    null
  )
  const pendingTimeoutRef = useRef<number | null>(null)
  // Stable ref so loadAll / subscriptions always see the current folderId
  const folderIdRef = useRef<string | null>(null)
  folderIdRef.current = folderId
  // Skip the initial folderId → folderId effect run on first mount
  const folderChangedRef = useRef(false)

  const loadAll = useCallback(async (): Promise<void> => {
    conversationsCache.error = null
    setError(null)
    const out: ConversationRow[] = []
    try {
      const params: Record<string, unknown> = { limit: 100, offset: 0 }
      if (folderIdRef.current) params.folder_id = folderIdRef.current
      const r = await omiApi.get<CloudConversation[]>('/v1/conversations', { params })
      const list = Array.isArray(r.data) ? r.data : []
      for (const c of list) {
        const created = c.created_at ? new Date(c.created_at).getTime() : 0
        out.push({
          id: c.id,
          title: c.structured?.title || c.title || 'Untitled conversation',
          emoji: c.structured?.emoji || undefined,
          subtitle: c.created_at ? new Date(c.created_at).toLocaleString() : '',
          preview:
            c.overview || summarize(c.transcript_segments).slice(0, 200) || '(no transcript)',
          source: 'cloud',
          starred: c.starred ?? false,
          sortAt: created
        })
      }
    } catch (e) {
      const msg = (e as Error).message
      conversationsCache.error = msg
      setError(msg)
    }
    // Only include local conversations when not filtering by folder (local rows have no folder concept)
    if (!folderIdRef.current) {
      try {
        const locals = await window.omi.listLocalConversations()
        for (const c of locals) out.push(localToRow(c))
      } catch (e) {
        console.error('Failed to load local conversations:', e)
      }
    }
    reconcilePending(out.filter((r) => r.source === 'cloud'))
    const merged = [...getPendingConversations(), ...out].sort((a, b) => b.sortAt - a.sortAt)
    conversationsCache.rows = merged
    conversationsCache.loaded = true
    setRows(merged)
    setLoading(false)
  }, [])

  // Load folders once on mount (optional — silent fail)
  useEffect(() => {
    omiApi
      .get<FolderItem[]>('/v1/folders')
      .then((r) => setFolders(Array.isArray(r.data) ? r.data : []))
      .catch(() => {
        /* folders are optional */
      })
  }, [])

  // Initial load (skip if already cached)
  useEffect(() => {
    if (conversationsCache.loaded) return
    void loadAll()
  }, [loadAll])

  // Re-fetch when folder selection changes (skip very first mount)
  useEffect(() => {
    if (!folderChangedRef.current) {
      folderChangedRef.current = true
      return
    }
    conversationsCache.loaded = false
    setLoading(true)
    void loadAll()
  }, [folderId, loadAll])

  // Cloud refresh subscription — respects current folder via ref
  useEffect(() => {
    return subscribeCloudRefresh(() => {
      void loadAll()
    })
  }, [loadAll])

  // Live local refresh — merge local changes while preserving cloud rows
  useEffect(() => {
    return subscribeConversations(() => {
      if (folderIdRef.current) return // skip local merge when folder is active
      window.omi
        .listLocalConversations()
        .then((locals) => {
          const localRows = locals.map(localToRow)
          setRows((prev) => {
            const cloud = prev.filter((r) => r.source === 'cloud' && !r.pending)
            const merged = [...getPendingConversations(), ...cloud, ...localRows].sort(
              (a, b) => b.sortAt - a.sortAt
            )
            conversationsCache.rows = merged
            return merged
          })
          setLoading(false)
        })
        .catch((e) => console.error('Live local refresh failed:', e))
    })
  }, [])

  const toggleStar = async (id: string, current: boolean): Promise<void> => {
    const next = !current
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, starred: next } : r)))
    try {
      await omiApi.patch(`/v1/conversations/${id}/starred`, null, { params: { starred: next } })
    } catch {
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, starred: current } : r)))
    }
  }

  const dateStart = dateFilterStart(dateFilter)
  const filtered = rows.filter((r) => {
    if (filter === 'chat' && r.localKind !== 'chat') return false
    if (filter === 'recording' && r.localKind !== 'recording') return false
    if (filter === 'starred' && !r.starred) return false
    if (dateFilter !== 'all' && r.sortAt < dateStart) return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      return (
        (r.title?.toLowerCase() ?? '').includes(q) ||
        (r.preview?.toLowerCase() ?? '').includes(q)
      )
    }
    return true
  })

  const executeDeletion = async (ids: string[]): Promise<void> => {
    setDeleting(true)
    for (const id of ids) {
      const row = rows.find((r) => r.id === id)
      if (!row) continue
      try {
        if (row.source === 'local') {
          await window.omi.deleteLocalConversation(id)
        } else {
          await omiApi.delete(`/v1/conversations/${id}`)
        }
      } catch (e) {
        console.error('Delete failed:', id, e)
      }
    }
    invalidateConversationsCache()
    setDeleting(false)
  }

  const handleDelete = (): void => {
    if (deleting || selected.size === 0) return
    const ids = Array.from(selected)
    const timeout = window.setTimeout(() => {
      setPendingDelete(null)
      void executeDeletion(ids)
    }, 5000)
    pendingTimeoutRef.current = timeout
    setPendingDelete({ ids, timeout })
    setSelected(new Set())
    setSelectMode(false)
  }

  const undoDelete = (): void => {
    if (pendingTimeoutRef.current) {
      clearTimeout(pendingTimeoutRef.current)
      pendingTimeoutRef.current = null
    }
    setPendingDelete(null)
  }

  useEffect(() => {
    return () => {
      if (pendingTimeoutRef.current) clearTimeout(pendingTimeoutRef.current)
    }
  }, [])

  const handleShare = async (): Promise<void> => {
    const items = rows.filter((r) => selected.has(r.id))
    const text = items.map((r) => `${r.title}\n${r.preview}`).join('\n\n---\n\n')
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // fallback
    }
  }

  const hasActiveFilter = filter !== 'all' || dateFilter !== 'all' || !!folderId || !!query

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Conversations"
        subtitle={
          loading ? 'Loading…' : `${rows.length} conversation${rows.length === 1 ? '' : 's'}`
        }
        actions={
          <button
            onClick={() => navigate('/conversations/live')}
            className="btn-record flex items-center gap-2"
            title="Start a live conversation"
          >
            <Mic className="h-4 w-4" />
            New
          </button>
        }
      />

      {/* Search + filter bar */}
      <div className="flex items-center gap-2 px-6 pb-2 lg:px-10">
        <div className="glass-subtle flex flex-1 items-center gap-2 px-4 py-2.5">
          <Search className="h-4 w-4 text-white/45" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations…"
            className="flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
          />
          {query && (
            <button onClick={() => setQuery('')} className="text-xs text-white/45 hover:text-white">
              Clear
            </button>
          )}
        </div>

        {/* Type filter chips */}
        <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
          {(
            [
              { id: 'all', label: 'All', Icon: null },
              { id: 'starred', label: 'Starred', Icon: Star },
              { id: 'chat', label: 'Chats', Icon: MessageSquare },
              { id: 'recording', label: 'Recordings', Icon: Radio }
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                filter === id
                  ? 'bg-white/15 text-white'
                  : 'text-white/55 hover:bg-white/5 hover:text-white/80'
              }`}
            >
              {Icon && <Icon className="h-3.5 w-3.5" />}
              {label}
            </button>
          ))}
        </div>

        {/* Date filter dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowDateMenu((v) => !v)}
            className={`glass-subtle flex items-center gap-1.5 px-3 py-2.5 text-sm transition-colors duration-200 ${
              dateFilter !== 'all' ? 'text-white' : 'text-white/55 hover:text-white/80'
            }`}
            title="Filter by date"
          >
            <CalendarDays className="h-4 w-4" />
            <span className="hidden lg:inline">{DATE_FILTER_LABELS[dateFilter]}</span>
          </button>
          {showDateMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowDateMenu(false)} />
              <div className="absolute right-0 top-full z-20 mt-1.5 min-w-[130px] rounded-xl border border-white/10 bg-[#1a1a1a]/95 py-1 shadow-xl backdrop-blur-md">
                {(['all', 'today', 'week', 'month'] as DateFilter[]).map((d) => (
                  <button
                    key={d}
                    onClick={() => {
                      setDateFilter(d)
                      setShowDateMenu(false)
                    }}
                    className={`flex w-full items-center px-3 py-2 text-sm transition-colors ${
                      dateFilter === d
                        ? 'text-white'
                        : 'text-white/60 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    {dateFilter === d ? (
                      <Check className="mr-2 h-3 w-3 shrink-0" />
                    ) : (
                      <span className="mr-2 w-3 shrink-0" />
                    )}
                    {DATE_FILTER_LABELS[d]}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Compact / expanded toggle */}
        <button
          onClick={() => {
            const next = !compact
            setCompact(next)
            localStorage.setItem('conv-compact', String(next))
          }}
          className={`glass-subtle flex items-center gap-2 px-3 py-2.5 text-sm transition-colors duration-200 ${
            compact ? 'text-white' : 'text-white/55 hover:text-white/80'
          }`}
          title={compact ? 'Switch to expanded view' : 'Switch to compact view'}
        >
          <LayoutList className="h-4 w-4" />
        </button>

        {/* Select */}
        <button
          onClick={() => {
            setSelectMode((o) => !o)
            if (selectMode) setSelected(new Set())
          }}
          className={`glass-subtle flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-200 ${
            selectMode ? 'text-white' : 'text-white/55 hover:text-white/80'
          }`}
          title="Select conversations"
        >
          <CheckSquare className="h-4 w-4" />
          <span className="hidden sm:inline">{selectMode ? 'Done' : 'Select'}</span>
        </button>
      </div>

      {/* Folder tab strip — only shown when user has folders */}
      {folders.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto px-6 pb-2 lg:px-10 [scrollbar-width:none]">
          <button
            onClick={() => setFolderId(null)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all ${
              folderId === null
                ? 'bg-white/15 text-white'
                : 'text-white/45 hover:bg-white/5 hover:text-white/70'
            }`}
          >
            <Folder className="h-3 w-3" />
            All
          </button>
          {folders.map((f) => (
            <button
              key={f.id}
              onClick={() => setFolderId(f.id === folderId ? null : f.id)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all ${
                folderId === f.id
                  ? 'bg-white/15 text-white'
                  : 'text-white/45 hover:bg-white/5 hover:text-white/70'
              }`}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: f.color || '#6B7280' }}
              />
              {f.name}
              {f.conversation_count > 0 && (
                <span className="text-white/25">{f.conversation_count}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Select mode action bar */}
      {selectMode && (
        <div className="flex items-center gap-2 px-6 pb-3 lg:px-10">
          <span className="text-xs text-white/50">{selected.size} selected</span>
          <button
            onClick={() => {
              if (selected.size === filtered.length) {
                setSelected(new Set())
              } else {
                setSelected(new Set(filtered.map((r) => r.id)))
              }
            }}
            className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            {selected.size === filtered.length ? 'Deselect all' : 'Select all'}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-400 hover:text-red-300"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
          <button
            onClick={handleShare}
            className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs"
          >
            <Share2 className="h-3.5 w-3.5" />
            Share
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4 lg:px-10 lg:py-6">
        {error && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">
            Cloud conversations: {error}
          </div>
        )}
        {loading && (
          <ul className="mx-auto max-w-3xl space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <ConversationSkeleton key={i} />
            ))}
          </ul>
        )}
        {!loading && filtered.length === 0 && (
          <EmptyState
            icon={filter === 'starred' ? Star : GanttChartSquare}
            title={
              filter === 'starred' && !query
                ? 'No starred conversations'
                : hasActiveFilter
                  ? 'No matching conversations'
                  : 'No conversations yet'
            }
            description={
              filter === 'starred' && !query
                ? 'Star a conversation to find it quickly. Hover a row and click the star icon.'
                : hasActiveFilter
                  ? 'Try a different search or filter.'
                  : 'Start a recording to capture audio and screen context. Your conversations will appear here.'
            }
            action={
              hasActiveFilter ? undefined : (
                <Link to="/home" className="btn-record">
                  <Mic className="h-4 w-4" />
                  Start recording
                </Link>
              )
            }
          />
        )}
        {!loading && filtered.length > 0 && (
          <ul className={`mx-auto max-w-3xl ${compact ? 'space-y-1.5' : 'space-y-2.5'}`}>
            {filtered.map((r) => {
              const checked = selected.has(r.id)

              // Select mode — same for compact and expanded
              if (selectMode) {
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => {
                        setSelected((s) => {
                          const next = new Set(s)
                          if (checked) next.delete(r.id)
                          else next.add(r.id)
                          return next
                        })
                      }}
                      className={`surface-card-interactive flex w-full items-center gap-4 p-5 text-left ${
                        checked ? 'ring-1 ring-white/20' : ''
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
                          checked
                            ? 'border-white/30 bg-white/20 text-white'
                            : 'border-white/20 bg-transparent'
                        }`}
                      >
                        {checked && <Check className="h-3.5 w-3.5" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="font-display text-base font-semibold leading-tight text-text-primary">
                          {r.emoji && <span className="mr-1.5">{r.emoji}</span>}
                          {r.title || <span className="italic text-text-tertiary">loading…</span>}
                        </div>
                        <div className="mt-1 text-xs text-text-quaternary">
                          {formatConversationTs(r.sortAt)}
                        </div>
                      </div>
                      {r.localKind === 'chat' ? (
                        <span className="badge shrink-0">Chat</span>
                      ) : r.source === 'local' ? (
                        <span className="badge-warning shrink-0">Not synced</span>
                      ) : null}
                    </button>
                  </li>
                )
              }

              // Compact mode — macOS-style single-line row
              if (compact) {
                return (
                  <li key={r.id}>
                    <CompactRow r={r} onToggleStar={toggleStar} />
                  </li>
                )
              }

              // Expanded mode — title + improved timestamp + preview
              return (
                <li key={r.id}>
                  <div className="surface-card-interactive group relative block">
                    {r.source === 'cloud' && (
                      <button
                        onClick={(e) => {
                          e.preventDefault()
                          void toggleStar(r.id, r.starred ?? false)
                        }}
                        title={r.starred ? 'Unstar' : 'Star'}
                        className={`absolute right-3 top-3 rounded-md p-1.5 transition-all ${
                          r.starred
                            ? 'text-amber-400'
                            : 'text-white/0 group-hover:text-white/35 hover:!text-white/70'
                        }`}
                      >
                        <Star
                          className="h-3.5 w-3.5"
                          fill={r.starred ? 'currentColor' : 'none'}
                        />
                      </button>
                    )}
                    <Link to={`/conversations/${r.id}`} className="block p-5">
                      <div className="flex items-start justify-between gap-3 pr-6">
                        <div className="font-display text-base font-semibold leading-tight text-text-primary">
                          {r.emoji && <span className="mr-1.5">{r.emoji}</span>}
                          {r.title || <span className="italic text-text-tertiary">loading…</span>}
                        </div>
                        {r.localKind === 'chat' ? (
                          <span className="badge shrink-0">Chat</span>
                        ) : (
                          r.source === 'local' && (
                            <span className="badge-warning shrink-0">Not synced</span>
                          )
                        )}
                      </div>
                      {/* macOS-style timestamp for cloud rows; original subtitle for local (includes duration/count) */}
                      <div className="mt-1 text-xs text-text-quaternary">
                        {r.source === 'cloud' ? formatConversationTs(r.sortAt) : r.subtitle}
                      </div>
                      <p className="mt-2.5 line-clamp-2 text-sm leading-relaxed text-text-tertiary">
                        {r.preview}
                      </p>
                    </Link>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {pendingDelete && (
        <div className="glass-strong mx-6 mb-4 flex items-center justify-between rounded-2xl px-4 py-3 lg:mx-10">
          <span className="text-sm text-white/80">
            {pendingDelete.ids.length} conversation
            {pendingDelete.ids.length !== 1 ? 's' : ''} will be deleted in 5s
          </span>
          <button
            onClick={undoDelete}
            className="text-sm font-semibold text-white transition-colors hover:text-white/70"
          >
            Undo
          </button>
        </div>
      )}
    </div>
  )
}
