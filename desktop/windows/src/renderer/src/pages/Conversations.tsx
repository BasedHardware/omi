import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  CalendarDays,
  Check,
  CheckSquare,
  Clipboard,
  Folder,
  FolderOpen,
  FolderPlus,
  GanttChartSquare,
  GitMerge,
  LayoutList,
  Link2,
  MessageSquare,
  Mic,
  Pencil,
  Radio,
  Search,
  Share2,
  Star,
  Trash2,
  X
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { toast } from '../lib/toast'
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

function FolderPickerDropdown({
  folders,
  onSelect,
  onClose
}: {
  folders: FolderItem[]
  onSelect: (folderId: string | null) => void
  onClose: () => void
}): React.JSX.Element {
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute right-0 top-full z-20 mt-1 min-w-[160px] rounded-xl border border-white/10 bg-[#1a1a1a]/95 py-1 shadow-xl backdrop-blur-md">
        <button
          onClick={() => onSelect(null)}
          className="flex w-full items-center gap-2 px-3 py-2 text-sm text-white/60 hover:bg-white/5 hover:text-white"
        >
          <Folder className="h-3.5 w-3.5 shrink-0 text-white/30" />
          No folder
        </button>
        {folders.map((f) => (
          <button
            key={f.id}
            onClick={() => onSelect(f.id)}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-white/60 hover:bg-white/5 hover:text-white"
          >
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: f.color || '#6B7280' }} />
            {f.name}
          </button>
        ))}
      </div>
    </>
  )
}

function CompactRow({
  r,
  editingId,
  editTitle,
  folders,
  onToggleStar,
  onStartEdit,
  onEditChange,
  onCommitEdit,
  onCancelEdit,
  onCopy,
  onCopyLink,
  onDeleteSingle,
  onMoveToFolder
}: {
  r: ConversationRow
  editingId: string | null
  editTitle: string
  folders: FolderItem[]
  onToggleStar: (id: string, current: boolean) => Promise<void>
  onStartEdit: (id: string, title: string) => void
  onEditChange: (v: string) => void
  onCommitEdit: (id: string) => void
  onCancelEdit: () => void
  onCopy: (r: ConversationRow) => void
  onCopyLink: (id: string) => void
  onDeleteSingle: (id: string) => void
  onMoveToFolder: (id: string, folderId: string | null) => void
}): React.JSX.Element {
  const isEditing = editingId === r.id
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  return (
    <div className="surface-card-interactive group relative flex items-center overflow-visible">
      <Link
        to={`/conversations/${r.id}`}
        className={`flex min-w-0 flex-1 items-center gap-3 px-4 py-3 ${isEditing ? 'pointer-events-none' : ''}`}
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.07] text-base leading-none ring-1 ring-inset ring-white/[0.06]">
          {r.emoji || '💬'}
        </div>
        <div className="min-w-0 flex-1">
          {isEditing ? (
            <input
              autoFocus
              value={editTitle}
              onChange={(e) => onEditChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); onCommitEdit(r.id) }
                if (e.key === 'Escape') onCancelEdit()
              }}
              onBlur={() => onCommitEdit(r.id)}
              onClick={(e) => e.preventDefault()}
              className="w-full rounded bg-white/10 px-1.5 py-0.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-white/30"
            />
          ) : (
            <p className="truncate text-sm font-medium text-white/90">
              {r.title || <span className="italic text-text-tertiary">loading…</span>}
            </p>
          )}
          <p className="mt-0.5 truncate text-xs text-white/40">
            {formatConversationTs(r.sortAt)}
            {r.localKind === 'chat' && <span className="ml-1.5 text-white/25">· Chat</span>}
            {r.source === 'local' && r.localKind !== 'chat' && (
              <span className="ml-1.5 text-amber-400/60">· Not synced</span>
            )}
          </p>
        </div>
      </Link>
      {/* Row action buttons — revealed on hover */}
      <div className="mr-2 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          onClick={(e) => { e.preventDefault(); onStartEdit(r.id, r.title) }}
          title="Edit title"
          className="rounded-md p-1.5 text-white/30 hover:text-white/80"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={(e) => { e.preventDefault(); onCopy(r) }}
          title="Copy preview"
          className="rounded-md p-1.5 text-white/30 hover:text-white/80"
        >
          <Clipboard className="h-3.5 w-3.5" />
        </button>
        {r.source === 'cloud' && (
          <button
            onClick={(e) => { e.preventDefault(); void onCopyLink(r.id) }}
            title="Copy shareable link"
            className="rounded-md p-1.5 text-white/30 hover:text-white/80"
          >
            <Link2 className="h-3.5 w-3.5" />
          </button>
        )}
        {r.source === 'cloud' && folders.length > 0 && (
          <div className="relative">
            <button
              onClick={(e) => { e.preventDefault(); setShowFolderPicker((v) => !v) }}
              title="Move to folder"
              className="rounded-md p-1.5 text-white/30 hover:text-white/80"
            >
              <FolderOpen className="h-3.5 w-3.5" />
            </button>
            {showFolderPicker && (
              <FolderPickerDropdown
                folders={folders}
                onSelect={(fid) => { onMoveToFolder(r.id, fid); setShowFolderPicker(false) }}
                onClose={() => setShowFolderPicker(false)}
              />
            )}
          </div>
        )}
        <button
          onClick={(e) => { e.preventDefault(); onDeleteSingle(r.id) }}
          title="Delete"
          className="rounded-md p-1.5 text-white/30 hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
        {r.source === 'cloud' && (
          <button
            onClick={(e) => { e.preventDefault(); void onToggleStar(r.id, r.starred ?? false) }}
            title={r.starred ? 'Unstar' : 'Star'}
            className={`rounded-md p-1.5 transition-colors ${
              r.starred ? 'text-amber-400' : 'text-white/30 hover:text-amber-400/70'
            }`}
          >
            <Star className="h-3.5 w-3.5" fill={r.starred ? 'currentColor' : 'none'} />
          </button>
        )}
      </div>
    </div>
  )
}

// --- Expanded row (non-compact) ---

function ExpandedRow({
  r,
  isEditingThis,
  editTitle,
  folders,
  onStartEdit,
  onEditChange,
  onCommitEdit,
  onCancelEdit,
  onCopy,
  onCopyLink,
  onDeleteSingle,
  onToggleStar,
  onMoveToFolder
}: {
  r: ConversationRow
  isEditingThis: boolean
  editTitle: string
  folders: FolderItem[]
  onStartEdit: (id: string, title: string) => void
  onEditChange: (v: string) => void
  onCommitEdit: (id: string) => void
  onCancelEdit: () => void
  onCopy: (r: ConversationRow) => void
  onCopyLink: (id: string) => void
  onDeleteSingle: (id: string) => void
  onToggleStar: (id: string, current: boolean) => Promise<void>
  onMoveToFolder: (id: string, folderId: string | null) => void
}): React.JSX.Element {
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  return (
    <div className="surface-card-interactive group relative block">
      {/* Hover action buttons — top-right */}
      <div className="absolute right-3 top-3 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          onClick={(e) => { e.preventDefault(); onStartEdit(r.id, r.title) }}
          title="Edit title"
          className="rounded-md p-1.5 text-white/30 hover:text-white/80"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={(e) => { e.preventDefault(); onCopy(r) }}
          title="Copy preview"
          className="rounded-md p-1.5 text-white/30 hover:text-white/80"
        >
          <Clipboard className="h-3.5 w-3.5" />
        </button>
        {r.source === 'cloud' && (
          <button
            onClick={(e) => { e.preventDefault(); onCopyLink(r.id) }}
            title="Copy shareable link"
            className="rounded-md p-1.5 text-white/30 hover:text-white/80"
          >
            <Link2 className="h-3.5 w-3.5" />
          </button>
        )}
        {r.source === 'cloud' && folders.length > 0 && (
          <div className="relative">
            <button
              onClick={(e) => { e.preventDefault(); setShowFolderPicker((v) => !v) }}
              title="Move to folder"
              className="rounded-md p-1.5 text-white/30 hover:text-white/80"
            >
              <FolderOpen className="h-3.5 w-3.5" />
            </button>
            {showFolderPicker && (
              <FolderPickerDropdown
                folders={folders}
                onSelect={(fid) => { onMoveToFolder(r.id, fid); setShowFolderPicker(false) }}
                onClose={() => setShowFolderPicker(false)}
              />
            )}
          </div>
        )}
        <button
          onClick={(e) => { e.preventDefault(); onDeleteSingle(r.id) }}
          title="Delete"
          className="rounded-md p-1.5 text-white/30 hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
        {r.source === 'cloud' && (
          <button
            onClick={(e) => { e.preventDefault(); void onToggleStar(r.id, r.starred ?? false) }}
            title={r.starred ? 'Unstar' : 'Star'}
            className={`rounded-md p-1.5 transition-colors ${
              r.starred ? 'text-amber-400' : 'text-white/30 hover:text-amber-400/70'
            }`}
          >
            <Star className="h-3.5 w-3.5" fill={r.starred ? 'currentColor' : 'none'} />
          </button>
        )}
      </div>
      <Link to={`/conversations/${r.id}`} className={`block p-5 ${isEditingThis ? 'pointer-events-none' : ''}`}>
        <div className="flex items-start justify-between gap-3 pr-36">
          {isEditingThis ? (
            <input
              autoFocus
              value={editTitle}
              onChange={(e) => onEditChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); onCommitEdit(r.id) }
                if (e.key === 'Escape') onCancelEdit()
              }}
              onBlur={() => onCommitEdit(r.id)}
              onClick={(e) => e.preventDefault()}
              className="font-display w-full rounded bg-white/10 px-2 py-0.5 text-base font-semibold text-text-primary focus:outline-none focus:ring-1 focus:ring-white/30"
            />
          ) : (
            <div className="font-display text-base font-semibold leading-tight text-text-primary">
              {r.emoji && <span className="mr-1.5">{r.emoji}</span>}
              {r.title || <span className="italic text-text-tertiary">loading…</span>}
            </div>
          )}
          {!isEditingThis && (r.localKind === 'chat' ? (
            <span className="badge shrink-0">Chat</span>
          ) : (
            r.source === 'local' && <span className="badge-warning shrink-0">Not synced</span>
          ))}
        </div>
        <div className="mt-1 text-xs text-text-quaternary">
          {r.source === 'cloud' ? formatConversationTs(r.sortAt) : r.subtitle}
        </div>
        <p className="mt-2.5 line-clamp-2 text-sm leading-relaxed text-text-tertiary">
          {r.preview}
        </p>
      </Link>
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
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [compact, setCompact] = useState(() => localStorage.getItem('conv-compact') === 'true')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ ids: string[]; timeout: number } | null>(
    null
  )
  const pendingTimeoutRef = useRef<number | null>(null)
  // Inline title edit
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [merging, setMerging] = useState(false)
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

  const startEdit = (id: string, title: string): void => {
    setEditingId(id)
    setEditTitle(title)
  }
  const cancelEdit = (): void => setEditingId(null)
  const commitEdit = async (id: string): Promise<void> => {
    const newTitle = editTitle.trim()
    setEditingId(null)
    if (!newTitle) return
    const row = rows.find((r) => r.id === id)
    if (!row || newTitle === row.title) return
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, title: newTitle } : r)))
    try {
      if (row.source === 'local') {
        await window.omi.updateLocalConversationTitle(id, newTitle)
      } else {
        await omiApi.patch(`/v1/conversations/${id}`, { title: newTitle })
      }
    } catch {
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, title: row.title } : r)))
    }
  }

  const copyRow = (r: ConversationRow): void => {
    void navigator.clipboard.writeText(`${r.title}\n\n${r.preview}`)
  }

  const doDeleteSingle = (id: string): void => {
    const timeout = window.setTimeout(() => {
      setPendingDelete(null)
      void executeDeletion([id])
    }, 5000)
    pendingTimeoutRef.current = timeout
    setPendingDelete({ ids: [id], timeout })
  }

  const createFolder = async (): Promise<void> => {
    const name = newFolderName.trim()
    if (!name) { setCreatingFolder(false); return }
    setCreatingFolder(false)
    setNewFolderName('')
    try {
      const res = await omiApi.post<FolderItem>('/v1/folders', { name, color: '#6B7280' })
      if (res.data) setFolders((f) => [...f, res.data])
    } catch { /* silent fail */ }
  }

  const deleteFolder = async (id: string): Promise<void> => {
    setFolders((f) => f.filter((x) => x.id !== id))
    if (folderId === id) setFolderId(null)
    try {
      await omiApi.delete(`/v1/folders/${id}`)
    } catch {
      // Restore on failure — reload from server
      const res = await omiApi.get<FolderItem[]>('/v1/folders').catch(() => null)
      if (res?.data) setFolders(res.data)
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

  const moveToFolder = async (id: string, fid: string | null): Promise<void> => {
    try {
      await omiApi.patch(`/v1/conversations/${id}/folder`, { folder_id: fid })
      // Remove from list when browsing a specific folder and conversation moved away
      if (folderId !== null && fid !== folderId) {
        setRows((rs) => rs.filter((r) => r.id !== id))
      }
      toast(fid ? 'Moved to folder' : 'Removed from folder', { tone: 'info' })
    } catch (e) {
      toast('Could not move conversation', { tone: 'error', body: (e as Error).message })
    }
  }

  const copyConversationLink = async (id: string): Promise<void> => {
    try {
      await omiApi.patch(`/v1/conversations/${id}/visibility`, null, { params: { value: 'shared' } })
      await navigator.clipboard.writeText(`https://h.omi.me/conversations/${id}`)
      toast('Link copied', { tone: 'info', body: 'Anyone with this link can view the conversation.' })
    } catch (e) {
      toast('Could not copy link', { tone: 'error', body: (e as Error).message })
    }
  }

  const handleMerge = async (): Promise<void> => {
    const cloudIds = Array.from(selected).filter((id) =>
      rows.find((r) => r.id === id && r.source === 'cloud')
    )
    if (cloudIds.length < 2) {
      toast('Select at least 2 cloud conversations to merge', { tone: 'warn' })
      return
    }
    if (
      !confirm(
        `Merge ${cloudIds.length} conversations? The originals will be deleted and replaced by a new merged conversation.`
      )
    )
      return
    setMerging(true)
    try {
      await omiApi.post('/v1/conversations/merge', { conversation_ids: cloudIds, reprocess: true })
      toast('Merge started', { tone: 'info', body: 'Refresh in a moment to see the merged conversation.' })
      setSelected(new Set())
      setSelectMode(false)
      setTimeout(() => void loadAll(), 6000)
    } catch (e) {
      toast('Merge failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setMerging(false)
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

      {/* Folder tab strip — always shown so "+" button is accessible */}
      <div className="flex items-center gap-1.5 overflow-x-auto px-6 pb-2 lg:px-10 [scrollbar-width:none]">
        {folders.length > 0 && (
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
        )}
        {folders.map((f) => (
          <div key={f.id} className="group/folder relative flex shrink-0 items-center">
            <button
              onClick={() => setFolderId(f.id === folderId ? null : f.id)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 pr-6 text-xs font-medium transition-all ${
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
            {/* Delete folder — revealed on hover */}
            <button
              onClick={() => void deleteFolder(f.id)}
              title={`Delete folder "${f.name}"`}
              className="absolute right-1 rounded-full p-0.5 text-white/0 transition-colors group-hover/folder:text-white/40 group-hover/folder:hover:text-white/80"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        {/* Create folder inline */}
        {creatingFolder ? (
          <input
            autoFocus
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); void createFolder() }
              if (e.key === 'Escape') { setCreatingFolder(false); setNewFolderName('') }
            }}
            onBlur={() => void createFolder()}
            placeholder="Folder name…"
            className="w-28 rounded-full bg-white/10 px-3 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-white/30"
          />
        ) : (
          <button
            onClick={() => setCreatingFolder(true)}
            title="New folder"
            className="flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs text-white/30 transition-colors hover:bg-white/5 hover:text-white/60"
          >
            <FolderPlus className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">New folder</span>
          </button>
        )}
      </div>

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
          {Array.from(selected).filter((id) => rows.find((r) => r.id === id && r.source === 'cloud')).length >= 2 && (
            <button
              onClick={() => void handleMerge()}
              disabled={merging}
              className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-40"
            >
              <GitMerge className="h-3.5 w-3.5" />
              {merging ? 'Merging…' : 'Merge'}
            </button>
          )}
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
                    <CompactRow
                      r={r}
                      editingId={editingId}
                      editTitle={editTitle}
                      folders={folders}
                      onToggleStar={toggleStar}
                      onStartEdit={startEdit}
                      onEditChange={setEditTitle}
                      onCommitEdit={(id) => void commitEdit(id)}
                      onCancelEdit={cancelEdit}
                      onCopy={copyRow}
                      onCopyLink={(id) => void copyConversationLink(id)}
                      onDeleteSingle={doDeleteSingle}
                      onMoveToFolder={(id, fid) => void moveToFolder(id, fid)}
                    />
                  </li>
                )
              }

              // Expanded mode — title + improved timestamp + preview
              const isEditingThis = editingId === r.id
              return (
                <li key={r.id}>
                  <ExpandedRow
                    r={r}
                    isEditingThis={isEditingThis}
                    editTitle={editTitle}
                    folders={folders}
                    onStartEdit={startEdit}
                    onEditChange={setEditTitle}
                    onCommitEdit={(id) => void commitEdit(id)}
                    onCancelEdit={cancelEdit}
                    onCopy={copyRow}
                    onCopyLink={(id) => void copyConversationLink(id)}
                    onDeleteSingle={doDeleteSingle}
                    onToggleStar={toggleStar}
                    onMoveToFolder={(id, fid) => void moveToFolder(id, fid)}
                  />
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
