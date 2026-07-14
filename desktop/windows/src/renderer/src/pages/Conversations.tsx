import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  GanttChartSquare,
  Mic,
  Search,
  CheckSquare,
  MessageSquare,
  Radio,
  type LucideIcon
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import {
  conversationsCache,
  subscribeConversations,
  subscribeCloudRefresh,
  invalidateConversationsCache,
  refreshCloudConversations,
  getPendingConversations,
  reconcilePending,
  type ConversationRow
} from '../lib/pageCache'
import { hideSyncedLocals, reconcileSyncedLocals } from '../lib/sync/conversationsReconcile'
import { resyncConversation, retryUnsyncedConversations } from '../lib/sync/conversationSync'
import { backfillCandidates, runBackfill, type BackfillProgress } from '../lib/sync/backfill'
import type { CloudConversationLite } from '../lib/sync/outbox'
import {
  applyFilters,
  buildConversationQuery,
  groupConversationsByDate,
  hasActiveFilters,
  mergeableRows,
  type ConversationFilters,
  type FilterKind,
  type FolderFilter,
  type DateRange,
  NO_DATE_RANGE
} from '../lib/conversations/filtering'
import { fetchFolders, loadCachedFolders } from '../lib/conversations/folders'
import {
  mergeConversations,
  moveConversationToFolder,
  setConversationStarred,
  setConversationTitle
} from '../lib/conversations/mutations'
import { FolderTabsStrip } from '../components/conversations/FolderTabsStrip'
import { DateFilterButton } from '../components/conversations/DateFilterButton'
import { ConversationListRow } from '../components/conversations/ConversationListRow'
import { SelectionActionBar } from '../components/conversations/SelectionActionBar'
import { FolderDialog } from '../components/conversations/FolderDialog'
import { MergeConfirmDialog } from '../components/conversations/MergeConfirmDialog'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import type { LocalConversation, ConversationFolder } from '../../../shared/types'
import type { Conversation as CloudConversation } from '../lib/omiApi.generated'

// The "default view" = all folders + no date range. Only this view is written to
// the shared conversationsCache (filtered fetches keep it clean) and it's the only
// one whose warm cache lets the first mount skip a fetch. Type + search stay
// client-side so they don't affect this.
function isDefaultView(folder: FolderFilter, dateRange: DateRange): boolean {
  return folder.kind === 'all' && dateRange.start == null && dateRange.end == null
}

// Chat/recording type filter — a client-side segmented control over the merged rows.
const TYPE_TABS: { value: FilterKind; label: string; icon?: LucideIcon }[] = [
  { value: 'all', label: 'All' },
  { value: 'chat', label: 'Chats', icon: MessageSquare },
  { value: 'recording', label: 'Recordings', icon: Radio }
]

function summarize(segments: { text: string }[] | undefined): string {
  if (!segments || segments.length === 0) return ''
  return segments
    .map((s) => s.text)
    .filter(Boolean)
    .join(' ')
}

function syncBadgeFor(c: LocalConversation): 'pending' | 'failed' | undefined {
  if (c.kind === 'chat') return undefined
  const s = c.syncState
  if (s === 'pending' || s === 'posting' || s === 'unconfirmed') return 'pending'
  if (s === 'failed') return 'failed'
  return undefined
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
    sync: syncBadgeFor(c),
    sortAt: c.createdAt
  }
}

function ConversationSkeleton(): React.JSX.Element {
  return (
    <li className="surface-card flex items-center gap-3 p-3">
      <div className="skeleton h-9 w-9 rounded-xl" />
      <div className="min-w-0 flex-1">
        <div className="skeleton mb-1.5 h-4 w-2/5" />
        <div className="skeleton h-3 w-1/4" />
      </div>
    </li>
  )
}

export function Conversations(): React.JSX.Element {
  const navigate = useNavigate()
  const [rows, setRows] = useState<ConversationRow[]>(conversationsCache.rows ?? [])
  const [loading, setLoading] = useState(!conversationsCache.loaded)
  const [error, setError] = useState<string | null>(conversationsCache.error)
  const [query, setQuery] = useState('')
  const [type, setType] = useState<FilterKind>('all')
  const [folderFilter, setFolderFilter] = useState<FolderFilter>({ kind: 'all' })
  const [dateRange, setDateRange] = useState<DateRange>(NO_DATE_RANGE)
  const [folders, setFolders] = useState<ConversationFolder[]>([])
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ ids: string[]; timeout: number } | null>(
    null
  )
  const pendingTimeoutRef = useRef<number | null>(null)
  // Full local set (including hidden synced rows) — drives the backfill banner.
  const [locals, setLocals] = useState<LocalConversation[]>([])
  const [backfill, setBackfill] = useState<BackfillProgress | null>(null)
  const [backfillRunning, setBackfillRunning] = useState(false)
  const backfillRunningRef = useRef(false)
  // Dialogs.
  const [folderDialog, setFolderDialog] = useState<{ folder?: ConversationFolder } | null>(null)
  const [mergeOpen, setMergeOpen] = useState(false)

  // Folder/starred/date filters are applied SERVER-SIDE (the /v1/conversations
  // query supports them, so cloud pagination stays correct); type + search stay
  // client-side over the merged rows.
  const loadAll = useCallback(
    async (showLoading = false): Promise<void> => {
      if (showLoading) setLoading(true)
      conversationsCache.error = null
      setError(null)
      const out: ConversationRow[] = []
      let cloudLite: CloudConversationLite[] = []
      try {
        const r = await omiApi.get<CloudConversation[]>('/v1/conversations', {
          params: buildConversationQuery(folderFilter, dateRange)
        })
        const list = Array.isArray(r.data) ? r.data : []
        cloudLite = list
        for (const c of list) {
          const created = c.created_at ? new Date(c.created_at).getTime() : 0
          out.push({
            id: c.id,
            title: c.structured?.title || 'Untitled conversation',
            emoji: c.structured?.emoji || undefined,
            subtitle: c.created_at ? new Date(c.created_at).toLocaleString() : '',
            preview:
              c.structured?.overview ||
              summarize(c.transcript_segments).slice(0, 200) ||
              '(no transcript)',
            source: 'cloud',
            starred: c.starred ?? undefined,
            folderId: c.folder_id ?? null,
            sortAt: created
          })
        }
      } catch (e) {
        const msg = (e as Error).message
        conversationsCache.error = msg
        setError(msg)
      }
      try {
        // Reconcile: rows still awaiting sync whose cloud twin has now appeared
        // (same started_at/finished_at we posted) are adopted as done — this is
        // what dissolves a "Sync pending" row into its cloud conversation.
        const localRows = reconcileSyncedLocals(
          await window.omi.listLocalConversations(),
          cloudLite,
          (id, patch) => window.omi.updateLocalConversationSync(id, patch)
        )
        setLocals(localRows)
        // Synced rows whose cloud twin is in this fetch are hidden (the cloud row
        // is the real one); if the cloud fetch failed the local copy stays visible.
        const cloudIds = new Set(cloudLite.map((c) => c.id))
        for (const c of hideSyncedLocals(localRows, cloudIds)) out.push(localToRow(c))
        // Opportunistic retry of rows still waiting (throttled inside; serial).
        void retryUnsyncedConversations(localRows).then((anyDone) => {
          if (anyDone) refreshCloudConversations()
        })
      } catch (e) {
        console.error('Failed to load local conversations:', e)
      }
      // Drop optimistic pendings the backend has now produced, then fold the rest in
      // at the top so a just-finalized conversation shows instantly.
      reconcilePending(out.filter((r) => r.source === 'cloud'))
      const merged = [...getPendingConversations(), ...out].sort((a, b) => b.sortAt - a.sortAt)
      // Only the default view is the canonical shared cache.
      if (isDefaultView(folderFilter, dateRange)) {
        conversationsCache.rows = merged
        conversationsCache.loaded = true
      }
      setRows(merged)
      setLoading(false)
    },
    [folderFilter, dateRange]
  )

  // Load folders: cached first (instant paint), then reconcile from the backend.
  useEffect(() => {
    void loadCachedFolders()
      .then((f) => {
        if (f.length) setFolders(f)
      })
      .catch(() => {})
    void fetchFolders()
      .then(setFolders)
      .catch(() => {})
  }, [])

  // (Re)fetch when the folder/date filter changes. Skip the fetch only on the very
  // first mount when the default view is already warm in the shared cache (instant
  // paint from the useState seed); every filter change after that fetches fresh.
  const didInitRef = useRef(false)
  useEffect(() => {
    const firstMount = !didInitRef.current
    didInitRef.current = true
    if (
      firstMount &&
      isDefaultView(folderFilter, dateRange) &&
      conversationsCache.loaded &&
      (conversationsCache.rows?.length ?? 0) > 0
    ) {
      return
    }
    void loadAll(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- folder/date read once for the first-mount check; loadAll owns the fetch + its own deps
  }, [loadAll])

  // The continuous-recording host (and session-end) request a cloud re-fetch when
  // the backend publishes a new conversation; re-run the full fetch in place.
  useEffect(() => {
    return subscribeCloudRefresh(() => {
      void loadAll()
    })
  }, [loadAll])

  // Live refresh: when the local store changes (e.g. an Omi chat is being saved as
  // it streams), re-read local conversations and merge with the already-loaded
  // cloud rows — no extra cloud fetch — so the list updates in real time.
  useEffect(() => {
    return subscribeConversations(() => {
      window.omi
        .listLocalConversations()
        .then((freshLocals) => {
          setLocals(freshLocals)
          setRows((prev) => {
            const cloud = prev.filter((r) => r.source === 'cloud' && !r.pending)
            const cloudIds = new Set(cloud.map((r) => r.id))
            const localRows = hideSyncedLocals(freshLocals, cloudIds).map(localToRow)
            const merged = [...getPendingConversations(), ...cloud, ...localRows].sort(
              (a, b) => b.sortAt - a.sortAt
            )
            if (isDefaultView(folderFilter, dateRange)) {
              conversationsCache.rows = merged
            }
            return merged
          })
          setLoading(false)
        })
        .catch((e) => console.error('Live local refresh failed:', e))
    })
  }, [folderFilter, dateRange])

  // Legacy local-only recordings eligible for backfill; recomputed only when the
  // local set actually changes.
  const unsyncedPast = useMemo(() => backfillCandidates(locals).length, [locals])

  const filters: ConversationFilters = useMemo(
    () => ({ folder: folderFilter, type, query, dateRange }),
    [folderFilter, type, query, dateRange]
  )
  const visible = useMemo(() => applyFilters(rows, filters), [rows, filters])
  const sections = useMemo(() => groupConversationsByDate(visible), [visible])
  const anyFilter = hasActiveFilters(filters)

  const selectedRows = useMemo(() => visible.filter((r) => selected.has(r.id)), [visible, selected])
  const mergeableCount = mergeableRows(selectedRows).length

  // Manual per-row re-sync of a wedged 'Sync failed' row (resets the attempt cap).
  const handleRetrySync = useCallback((id: string): void => {
    void resyncConversation(id).then((out) => {
      if (out?.status === 'done') refreshCloudConversations()
      invalidateConversationsCache()
    })
  }, [])

  // One-time, user-confirmed backfill of pre-sync local recordings.
  const startBackfill = async (): Promise<void> => {
    if (backfillRunningRef.current) return
    backfillRunningRef.current = true
    setBackfillRunning(true)
    setBackfill({ total: unsyncedPast, synced: 0, failed: 0, capped: false })
    try {
      const result = await runBackfill(locals, (p) => setBackfill({ ...p }))
      setBackfill(result)
      if (result.synced > 0) refreshCloudConversations()
      else void loadAll()
    } catch (e) {
      console.error('Backfill failed:', e)
    } finally {
      backfillRunningRef.current = false
      setBackfillRunning(false)
    }
  }

  // --- Row mutations (optimistic; revert on error) ---

  const patchRow = (id: string, patch: Partial<ConversationRow>): void => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }

  const handleStar = (row: ConversationRow, next: boolean): void => {
    patchRow(row.id, { starred: next })
    void setConversationStarred(row.id, next).catch(() => {
      patchRow(row.id, { starred: !next }) // revert
    })
  }

  const handleMoveToFolder = (row: ConversationRow, folderId: string | null): void => {
    const prev = row.folderId ?? null
    patchRow(row.id, { folderId })
    void moveConversationToFolder(row.id, folderId)
      .then(() => {
        // Folder counts changed — refresh the strip (light call, cache-backed).
        void fetchFolders().then(setFolders)
      })
      .catch(() => patchRow(row.id, { folderId: prev }))
  }

  const handleRename = (row: ConversationRow, title: string): void => {
    const prev = row.title
    patchRow(row.id, { title })
    const write =
      row.source === 'cloud'
        ? setConversationTitle(row.id, title)
        : window.omi.updateLocalConversationTitle(row.id, title)
    void Promise.resolve(write).catch(() => patchRow(row.id, { title: prev }))
  }

  // --- Delete (5s undo, batched) ---

  const executeDeletion = async (ids: string[]): Promise<void> => {
    setDeleting(true)
    for (const id of ids) {
      const row = rows.find((r) => r.id === id)
      if (!row || row.pending) continue
      try {
        if (row.source === 'local') await window.omi.deleteLocalConversation(id)
        else await omiApi.delete(`/v1/conversations/${id}`)
      } catch (e) {
        console.error('Delete failed:', id, e)
      }
    }
    invalidateConversationsCache()
    setDeleting(false)
  }

  const scheduleDelete = (ids: string[]): void => {
    if (deleting || ids.length === 0) return
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

  // Cleanup timeout on unmount.
  useEffect(() => {
    return () => {
      if (pendingTimeoutRef.current) clearTimeout(pendingTimeoutRef.current)
    }
  }, [])

  // --- Merge (fire-and-forget; refetch after) ---

  const handleMergeConfirmed = async (): Promise<void> => {
    const ids = mergeableRows(selectedRows).map((r) => r.id)
    await mergeConversations(ids)
    setMergeOpen(false)
    setSelected(new Set())
    setSelectMode(false)
    // The new conversation is produced async and the originals are deleted — the
    // merge response carries no new id, so refetch now and once more shortly after.
    void loadAll()
    window.setTimeout(() => void loadAll(), 2500)
  }

  // --- Folder dialog callbacks ---

  const onFolderSaved = (): void => {
    setFolderDialog(null)
    void fetchFolders().then(setFolders)
  }
  const onFolderDeleted = (id: string): void => {
    setFolderDialog(null)
    if (folderFilter.kind === 'folder' && folderFilter.id === id) setFolderFilter({ kind: 'all' })
    void fetchFolders().then(setFolders)
  }

  const clearAllFilters = (): void => {
    setFolderFilter({ kind: 'all' })
    setType('all')
    setQuery('')
    setDateRange(NO_DATE_RANGE)
  }

  const allVisibleSelected = visible.length > 0 && selected.size === visible.length

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Conversations"
        subtitle={
          loading ? 'Loading…' : `${visible.length} conversation${visible.length === 1 ? '' : 's'}`
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

      {/* Search + type filter + date + select */}
      <div className="flex items-center gap-2 px-6 pb-3 lg:px-10">
        <div className="surface-panel flex flex-1 items-center gap-2 px-4 py-2.5">
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

        <div className="surface-panel flex items-center gap-1 p-1">
          {TYPE_TABS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => setType(value)}
              className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                type === value
                  ? 'bg-white/15 text-white'
                  : 'text-white/55 hover:bg-white/5 hover:text-white/80'
              }`}
            >
              {Icon && <Icon className="h-3.5 w-3.5" />}
              {label}
            </button>
          ))}
        </div>

        <DateFilterButton dateRange={dateRange} onChange={setDateRange} />

        <button
          onClick={() => {
            setSelectMode((o) => !o)
            if (selectMode) setSelected(new Set())
          }}
          className={`surface-panel flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-200 ${
            selectMode ? 'text-white' : 'text-white/55 hover:text-white/80'
          }`}
          title="Select conversations"
        >
          <CheckSquare className="h-4 w-4" />
          <span className="hidden sm:inline">{selectMode ? 'Done' : 'Select'}</span>
        </button>
      </div>

      {/* Folder tabs */}
      <FolderTabsStrip
        folders={folders}
        selected={folderFilter}
        onSelect={setFolderFilter}
        onCreate={() => setFolderDialog({})}
        onEditFolder={(f) => setFolderDialog({ folder: f })}
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {error && (
          <div className="surface-panel mb-5 px-4 py-3 text-sm text-white/60">
            Cloud conversations: {error}
          </div>
        )}
        {(unsyncedPast > 0 || backfillRunning) && (
          <div className="surface-panel mx-auto mb-5 flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
            <span className="text-sm text-white/60">
              {backfillRunning && backfill
                ? `Syncing past recordings… ${backfill.synced + backfill.failed}/${backfill.total}`
                : `${unsyncedPast} past recording${unsyncedPast === 1 ? ' is' : 's are'} only on this device`}
              {!backfillRunning && backfill?.capped && (
                <span className="text-white/40"> · hourly sync limit reached, run again later</span>
              )}
            </span>
            {!backfillRunning && (
              <button
                onClick={() => void startBackfill()}
                className="shrink-0 text-sm font-semibold text-white transition-colors hover:text-white/70"
              >
                Sync past recordings
              </button>
            )}
          </div>
        )}
        {loading && (
          <ul className="mx-auto max-w-5xl space-y-2.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <ConversationSkeleton key={i} />
            ))}
          </ul>
        )}
        {!loading && visible.length === 0 && (
          <EmptyState
            icon={GanttChartSquare}
            title={anyFilter ? 'No matching conversations' : 'No conversations yet'}
            description={
              anyFilter
                ? 'Try a different search or filter.'
                : 'Start a recording to capture audio and screen context. Your conversations will appear here.'
            }
            action={
              anyFilter ? (
                <button onClick={clearAllFilters} className="btn-ghost">
                  Clear filters
                </button>
              ) : (
                <Link to="/home" className="btn-record">
                  <Mic className="h-4 w-4" />
                  Start recording
                </Link>
              )
            }
          />
        )}
        {!loading && visible.length > 0 && (
          <div className="mx-auto max-w-5xl space-y-6">
            {sections.map((section) => (
              <section key={section.key}>
                <h2 className="section-label mb-2.5 px-1">{section.label}</h2>
                <ul className="space-y-2">
                  {section.rows.map((r) => (
                    <li key={r.id}>
                      <ConversationListRow
                        row={r}
                        folders={folders}
                        selectMode={selectMode}
                        selected={selected.has(r.id)}
                        onToggleSelect={(id) =>
                          setSelected((s) => {
                            const next = new Set(s)
                            if (next.has(id)) next.delete(id)
                            else next.add(id)
                            return next
                          })
                        }
                        onStar={handleStar}
                        onMoveToFolder={handleMoveToFolder}
                        onRename={handleRename}
                        onDelete={(row) => scheduleDelete([row.id])}
                        onRetrySync={handleRetrySync}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>

      {selectMode && (
        <SelectionActionBar
          selectedCount={selected.size}
          mergeableCount={mergeableCount}
          allSelected={allVisibleSelected}
          onToggleSelectAll={() =>
            setSelected(allVisibleSelected ? new Set() : new Set(visible.map((r) => r.id)))
          }
          onMerge={() => setMergeOpen(true)}
          onDelete={() => scheduleDelete(Array.from(selected))}
          deleting={deleting}
        />
      )}

      {pendingDelete && (
        <div className="glass-strong mx-6 mb-4 flex items-center justify-between rounded-2xl px-4 py-3 lg:mx-10">
          <span className="text-sm text-white/80">
            {pendingDelete.ids.length} conversation{pendingDelete.ids.length !== 1 ? 's' : ''} will
            be deleted in 5s
          </span>
          <button
            onClick={undoDelete}
            className="text-sm font-semibold text-white transition-colors hover:text-white/70"
          >
            Undo
          </button>
        </div>
      )}

      {folderDialog && (
        <FolderDialog
          folder={folderDialog.folder}
          onClose={() => setFolderDialog(null)}
          onSaved={onFolderSaved}
          onDeleted={onFolderDeleted}
        />
      )}

      {mergeOpen && (
        <MergeConfirmDialog
          count={mergeableCount}
          onCancel={() => setMergeOpen(false)}
          onConfirm={handleMergeConfirmed}
        />
      )}
    </div>
  )
}
