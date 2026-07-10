import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  GanttChartSquare,
  Mic,
  Search,
  Trash2,
  Share2,
  CheckSquare,
  Check,
  MessageSquare,
  Radio
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
import { retryUnsyncedConversations } from '../lib/sync/conversationSync'
import { backfillCandidates, runBackfill, type BackfillProgress } from '../lib/sync/backfill'
import type { CloudConversationLite } from '../lib/sync/outbox'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import type { LocalConversation } from '../../../shared/types'
import type { Conversation as CloudConversation } from '../lib/omiApi.generated'

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

// Right-hand badge for a list row. Local recordings surface their sync-outbox
// state: queued/in-flight/unconfirmed → "Sync pending" (neutral — it resolves
// itself), a definitive failure → "Sync failed", legacy pre-sync rows →
// "Not synced" (the backfill banner offers to push those).
function RowBadge({ r }: { r: ConversationRow }): React.JSX.Element | null {
  if (r.localKind === 'chat') return <span className="badge shrink-0">Chat</span>
  if (r.source !== 'local') return null
  if (r.sync === 'pending') return <span className="badge shrink-0">Sync pending</span>
  if (r.sync === 'failed') return <span className="badge-warning shrink-0">Sync failed</span>
  return <span className="badge-warning shrink-0">Not synced</span>
}

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

type FilterKind = 'all' | 'chat' | 'recording'

export function Conversations(): React.JSX.Element {
  const navigate = useNavigate()
  const [rows, setRows] = useState<ConversationRow[]>(conversationsCache.rows ?? [])
  const [loading, setLoading] = useState(!conversationsCache.loaded)
  const [error, setError] = useState<string | null>(conversationsCache.error)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterKind>('all')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ ids: string[]; timeout: number } | null>(null)
  const pendingTimeoutRef = useRef<number | null>(null)
  // Full local set (including hidden synced rows) — drives the backfill banner.
  const [locals, setLocals] = useState<LocalConversation[]>([])
  const [backfill, setBackfill] = useState<BackfillProgress | null>(null)
  const [backfillRunning, setBackfillRunning] = useState(false)
  const backfillRunningRef = useRef(false)

  const loadAll = useCallback(async (): Promise<void> => {
    conversationsCache.error = null
    setError(null)
    const out: ConversationRow[] = []
    let cloudLite: CloudConversationLite[] = []
    try {
      const r = await omiApi.get<CloudConversation[]>('/v1/conversations', {
        params: { limit: 100, offset: 0 }
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
          preview: c.structured?.overview || summarize(c.transcript_segments).slice(0, 200) || '(no transcript)',
          source: 'cloud',
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
      const localRows = reconcileSyncedLocals(await window.omi.listLocalConversations(), cloudLite, (id, patch) =>
        window.omi.updateLocalConversationSync(id, patch)
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
    conversationsCache.rows = merged
    conversationsCache.loaded = true
    setRows(merged)
    setLoading(false)
  }, [])

  useEffect(() => {
    if (conversationsCache.loaded) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount / reset-on-dependency-change; not a self-retriggering loop
    void loadAll()
  }, [loadAll])

  // The continuous-recording host (and session-end) request a cloud re-fetch when
  // the backend publishes a new conversation; re-run the full fetch in place.
  useEffect(() => {
    return subscribeCloudRefresh(() => {
      void loadAll()
    })
  }, [loadAll])

  // Live refresh: when the local store changes (e.g. an Omi chat is being
  // saved as it streams), re-read local conversations and merge them with the
  // already-loaded cloud rows — no extra cloud fetch — so the list updates in
  // real time without waiting for a remount.
  useEffect(() => {
    return subscribeConversations(() => {
      window.omi
        .listLocalConversations()
        .then((freshLocals) => {
          setLocals(freshLocals)
          setRows((prev) => {
            // Keep the already-loaded CLOUD rows (not the optimistic pendings — those
            // come fresh from getPendingConversations so titles/removals reflect).
            const cloud = prev.filter((r) => r.source === 'cloud' && !r.pending)
            const cloudIds = new Set(cloud.map((r) => r.id))
            const localRows = hideSyncedLocals(freshLocals, cloudIds).map(localToRow)
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

  // Legacy local-only recordings eligible for backfill; recomputed only when
  // the local set actually changes.
  const unsyncedPast = useMemo(() => backfillCandidates(locals).length, [locals])

  // One-time, user-confirmed backfill of pre-sync local recordings (paced to
  // stay under the from-segments rate limit; resumable across runs).
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

  const filtered = rows.filter((r) => {
    if (filter === 'chat' && r.localKind !== 'chat') return false
    if (filter === 'recording' && r.localKind !== 'recording') return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      return (r.title?.toLowerCase() ?? '').includes(q) || (r.preview?.toLowerCase() ?? '').includes(q)
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

  // Cleanup timeout on unmount.
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

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Conversations"
        subtitle={loading ? 'Loading…' : `${rows.length} conversation${rows.length === 1 ? '' : 's'}`}
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
      <div className="flex items-center gap-2 px-6 pb-3 lg:px-10">
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

        <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
          <button
            onClick={() => setFilter('all')}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
              filter === 'all'
                ? 'bg-white/15 text-white'
                : 'text-white/55 hover:bg-white/5 hover:text-white/80'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('chat')}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
              filter === 'chat'
                ? 'bg-white/15 text-white'
                : 'text-white/55 hover:bg-white/5 hover:text-white/80'
            }`}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Chats
          </button>
          <button
            onClick={() => setFilter('recording')}
            className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
              filter === 'recording'
                ? 'bg-white/15 text-white'
                : 'text-white/55 hover:bg-white/5 hover:text-white/80'
            }`}
          >
            <Radio className="h-3.5 w-3.5" />
            Recordings
          </button>
        </div>

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

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        {error && (
          <div className="glass-subtle mb-5 px-4 py-3 text-sm text-white/60">
            Cloud conversations: {error}
          </div>
        )}
        {(unsyncedPast > 0 || backfillRunning) && (
          <div className="glass-subtle mx-auto mb-5 flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
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
          <ul className="mx-auto max-w-3xl space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <ConversationSkeleton key={i} />
            ))}
          </ul>
        )}
        {!loading && filtered.length === 0 && (
          <EmptyState
            icon={GanttChartSquare}
            title={query || filter !== 'all' ? 'No matching conversations' : 'No conversations yet'}
            description={
              query || filter !== 'all'
                ? 'Try a different search or filter.'
                : 'Start a recording to capture audio and screen context. Your conversations will appear here.'
            }
            action={
              query || filter !== 'all' ? undefined : (
                <Link to="/home" className="btn-record">
                  <Mic className="h-4 w-4" />
                  Start recording
                </Link>
              )
            }
          />
        )}
        {!loading && filtered.length > 0 && (
          <ul className="mx-auto max-w-3xl space-y-2.5">
            {filtered.map((r) => {
              const checked = selected.has(r.id)
              return (
                <li key={r.id}>
                  {selectMode ? (
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
                        <div className="font-display text-lg font-semibold leading-tight text-text-primary">
                          {r.emoji && <span className="mr-1.5">{r.emoji}</span>}
                          {r.title || <span className="italic text-text-tertiary">loading…</span>}
                        </div>
                        {r.subtitle && (
                          <div className="mt-1 text-xs text-text-quaternary">{r.subtitle}</div>
                        )}
                      </div>
                      <RowBadge r={r} />
                    </button>
                  ) : (
                    <Link
                      to={`/conversations/${r.id}`}
                      className="surface-card-interactive block p-5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="font-display text-lg font-semibold leading-tight text-text-primary">
                          {r.emoji && <span className="mr-1.5">{r.emoji}</span>}
                          {r.title || <span className="italic text-text-tertiary">loading…</span>}
                        </div>
                        <RowBadge r={r} />
                      </div>
                      {r.subtitle && (
                        <div className="mt-1 text-xs text-text-quaternary">{r.subtitle}</div>
                      )}
                      <p className="mt-2.5 line-clamp-2 text-sm leading-relaxed text-text-tertiary">
                        {r.preview}
                      </p>
                    </Link>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {pendingDelete && (
        <div className="glass-strong mx-6 mb-4 flex items-center justify-between rounded-2xl px-4 py-3 lg:mx-10">
          <span className="text-sm text-white/80">
            {pendingDelete.ids.length} conversation{pendingDelete.ids.length !== 1 ? 's' : ''} will be deleted in 5s
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
