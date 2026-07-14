import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Copy,
  Link2,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Sparkles,
  Trash2
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { isLocalConversationId, isPendingConversationId } from '../lib/conversationId'
import { invalidateConversationsCache } from '../lib/pageCache'
import { toast } from '../lib/toast'
import type {
  App as AppEntry,
  Conversation as ServerConversation,
  Person,
  TranscriptSegment
} from '../lib/omiApi.generated'
import type { ChatMessage, ConversationFolder } from '../../../shared/types'
import { Markdown } from '../components/Markdown'
import { Spinner } from '../components/ui/Spinner'
import { ModalShell } from '../components/conversations/ModalShell'
import { MoveToFolderMenu } from '../components/conversations/MoveToFolderMenu'
import { NameSpeakerModal } from '../components/conversations/NameSpeakerModal'
import { TranscriptDrawer } from '../components/conversations/TranscriptDrawer'
import { fetchPeople } from '../lib/conversations/people'
import { fetchFolders } from '../lib/conversations/folders'
import {
  getConversationShareLink,
  moveConversationToFolder,
  reprocessConversation,
  setConversationTitle
} from '../lib/conversations/mutations'
import {
  POLL_INTERVAL_MS,
  isEnriching,
  shouldStopPolling
} from '../lib/conversations/detailPolling'
import {
  conversationDuration,
  displayCategory,
  formatDuration,
  formatWhen
} from '../lib/conversations/detailFormat'

// Mac's ConversationDetailView, ported: a FULL PAGE (not a modal/drawer) that
// replaces the list, with a 450px transcript drawer that slides in from the right.
//
// Deliberate deviations from Mac, both approved:
//  - Action items stay INTERACTIVE here. Mac renders them display-only; Windows
//    already had a working toggle and keeps it (positional contract:
//    PATCH /v1/conversations/{id}/action-items {items_idx, values}).
//  - Speaker naming never fabricates a segment id. See lib/conversations/speakers.ts.
//
// There is intentionally NO star button in this header — starring lives on the
// list row only (Mac parity).

const INSIGHT_COLLAPSE_CHARS = 200

type LocalDisplay = {
  title: string
  subtitle?: string
  transcript?: string
  chatMessages?: ChatMessage[]
}

function Chip({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-border bg-white/[0.04] px-2.5 py-1 text-[11px] text-text-tertiary">
      {children}
    </span>
  )
}

function ToolbarButton({
  onClick,
  title,
  disabled,
  children
}: {
  onClick: () => void
  title: string
  disabled?: boolean
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="btn-ghost p-2 disabled:opacity-40"
    >
      {children}
    </button>
  )
}

/** One app-insight card: collapsed past 200 chars, like Mac. */
function InsightCard({
  appName,
  content
}: {
  appName: string
  content: string
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const collapsible = content.length > INSIGHT_COLLAPSE_CHARS

  return (
    <div className="surface-card p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-white">{appName}</h3>
        {collapsible && (
          <button
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            title={expanded ? 'Collapse' : 'Expand'}
            className="btn-ghost shrink-0 p-1"
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
            />
          </button>
        )}
      </div>
      <div
        className={`mt-2 text-sm leading-relaxed text-text-secondary ${
          collapsible && !expanded ? 'line-clamp-3' : ''
        }`}
      >
        <Markdown text={content} />
      </div>
    </div>
  )
}

/** Rename dialog — Mac uses an alert with a TextField; Windows uses a centered
 *  modal. Title is a QUERY param on the backend (see mutations.setConversationTitle). */
function RenameModal({
  initial,
  onClose,
  onSave
}: {
  initial: string
  onClose: () => void
  onSave: (title: string) => void
}): React.JSX.Element {
  const [value, setValue] = useState(initial)
  return (
    <ModalShell onClose={onClose} labelledBy="rename-conv-title">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const next = value.trim()
          if (next) onSave(next)
        }}
      >
        <h2 id="rename-conv-title" className="font-display text-lg font-semibold text-white">
          Edit title
        </h2>
        {/* autoFocus is intentional: the modal only opens on an explicit user action */}
        <input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Conversation title"
          className="mt-4 w-full rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2 text-sm text-white focus:border-white/40 focus:outline-none"
        />
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost px-3 py-1.5 text-sm">
            Cancel
          </button>
          <button
            type="submit"
            disabled={!value.trim()}
            className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-bg-primary disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </form>
    </ModalShell>
  )
}

/**
 * Remounts the view whenever the conversation changes, so opening a different
 * conversation starts from clean state. Without the key we would have to reset
 * every piece of state synchronously inside the load effect — which is exactly
 * the cascading-render pattern react-hooks warns about.
 */
export function ConversationDetail({
  conversationId
}: {
  conversationId: string
}): React.JSX.Element {
  return <ConversationDetailView key={conversationId} conversationId={conversationId} />
}

function ConversationDetailView({ conversationId }: { conversationId: string }): React.JSX.Element {
  const id = conversationId
  const navigate = useNavigate()
  const isLocal = isLocalConversationId(id)
  const isPending = isPendingConversationId(id)

  const [conv, setConv] = useState<ServerConversation | null>(null)
  const [local, setLocal] = useState<LocalDisplay | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [people, setPeople] = useState<Person[]>([])
  const [folders, setFolders] = useState<ConversationFolder[]>([])
  const [apps, setApps] = useState<AppEntry[]>([])

  const [drawerOpen, setDrawerOpen] = useState(false) // Mac: closed by default
  const [renaming, setRenaming] = useState(false)
  const [naming, setNaming] = useState<TranscriptSegment | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [copied, setCopied] = useState<'link' | 'transcript' | null>(null)
  const [reprocessing, setReprocessing] = useState(false)
  const [pickingApp, setPickingApp] = useState(false)

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchConversation = useCallback(async (): Promise<ServerConversation> => {
    const r = await omiApi.get<ServerConversation>(`/v1/conversations/${id}`)
    return r.data
  }, [id])

  // Initial load (runs once per conversation — the component is keyed by id).
  // Folder/people lookups are best-effort: a failure there must never blank out
  // the conversation itself.
  useEffect(() => {
    let cancelled = false
    if (isPending) return
    ;(async () => {
      try {
        if (isLocal) {
          const c = await window.omi.getLocalConversation(id)
          if (cancelled) return
          if (!c) {
            setError('Local conversation not found')
            return
          }
          setLocal(
            c.kind === 'chat'
              ? {
                  title: c.title || 'Chat with Omi',
                  subtitle: `${new Date(c.startedAt).toLocaleString()} · ${c.messages?.length ?? 0} messages`,
                  chatMessages: c.messages ?? [],
                  transcript: c.transcript
                }
              : {
                  title: c.title || 'Recording',
                  subtitle: `${new Date(c.startedAt).toLocaleString()} · ${Math.round(
                    (c.endedAt - c.startedAt) / 1000
                  )}s · local only`,
                  transcript: c.transcript
                }
          )
          return
        }

        const c = await fetchConversation()
        if (cancelled) return
        setConv(c)

        const [ppl, flds] = await Promise.all([
          fetchPeople().catch(() => [] as Person[]),
          fetchFolders().catch(() => [] as ConversationFolder[])
        ])
        if (cancelled) return
        setPeople(ppl)
        setFolders(flds)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [id, isLocal, isPending, fetchConversation])

  // Poll while Omi enriches: 15 attempts, 2s apart, stopping the moment the
  // status leaves `processing`. A self-scheduling timeout (not setInterval) so a
  // slow response can't stack requests.
  useEffect(() => {
    if (!conv || isLocal || !isEnriching(conv)) return

    let cancelled = false
    let attempt = 0

    const tick = async (): Promise<void> => {
      attempt++
      try {
        const next = await fetchConversation()
        if (cancelled) return
        setConv(next)
        if (shouldStopPolling(next.status, attempt)) return
      } catch {
        if (cancelled) return
        if (shouldStopPolling('processing', attempt)) return // still counts against the ceiling
      }
      pollRef.current = setTimeout(tick, POLL_INTERVAL_MS)
    }

    pollRef.current = setTimeout(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      if (pollRef.current) clearTimeout(pollRef.current)
      pollRef.current = null
    }
    // Re-arms only when the id changes or enrichment starts/stops — not on every
    // `conv` update, which would restart the ladder on each poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, isLocal, conv && isEnriching(conv), fetchConversation])

  const segments = useMemo(() => conv?.transcript_segments ?? [], [conv])

  const transcriptText = useMemo(() => {
    if (local) return local.transcript ?? ''
    return segments
      .map((s) => `${s.is_user ? 'You' : (s.speaker ?? 'Speaker')}: ${s.text}`)
      .join('\n')
  }, [local, segments])

  const flash = (what: 'link' | 'transcript'): void => {
    setCopied(what)
    setTimeout(() => setCopied((c) => (c === what ? null : c)), 1500)
  }

  const onCopyTranscript = async (): Promise<void> => {
    await navigator.clipboard.writeText(transcriptText)
    flash('transcript')
  }

  const onCopyLink = async (): Promise<void> => {
    try {
      const url = await getConversationShareLink(id)
      await navigator.clipboard.writeText(url)
      flash('link')
    } catch (e) {
      toast('Could not copy link', { tone: 'error', body: (e as Error).message })
    }
  }

  const onRename = async (title: string): Promise<void> => {
    setRenaming(false)
    const prev = conv?.structured?.title ?? local?.title ?? ''
    // Optimistic; revert on failure.
    if (conv) setConv({ ...conv, structured: { ...conv.structured, title } })
    else if (local) setLocal({ ...local, title })
    try {
      if (isLocal) await window.omi.updateLocalConversationTitle(id, title)
      else await setConversationTitle(id, title)
      invalidateConversationsCache()
    } catch (e) {
      if (conv) setConv((c) => (c ? { ...c, structured: { ...c.structured, title: prev } } : c))
      else setLocal((l) => (l ? { ...l, title: prev } : l))
      toast('Rename failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const onDelete = async (): Promise<void> => {
    setConfirmDelete(false)
    try {
      if (isLocal) await window.omi.deleteLocalConversation(id)
      else await omiApi.delete(`/v1/conversations/${id}`)
      invalidateConversationsCache()
      toast('Conversation deleted', { tone: 'info' })
      navigate('/conversations')
    } catch (e) {
      toast('Delete failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const onMoveToFolder = async (folderId: string | null): Promise<void> => {
    if (!conv) return
    const prev = conv.folder_id ?? null
    setConv({ ...conv, folder_id: folderId })
    try {
      await moveConversationToFolder(id, folderId)
      invalidateConversationsCache()
    } catch (e) {
      setConv((c) => (c ? { ...c, folder_id: prev } : c))
      toast('Could not move conversation', { tone: 'error', body: (e as Error).message })
    }
  }

  const onReprocess = async (appId?: string): Promise<void> => {
    setPickingApp(false)
    setReprocessing(true)
    try {
      await reprocessConversation(id, appId)
      toast('Reprocessing', { tone: 'info', body: 'Omi is regenerating the summary.' })
      setConv((c) => (c ? { ...c, status: 'processing' } : c))
    } catch (e) {
      toast('Reprocess failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setReprocessing(false)
    }
  }

  const openAppPicker = async (): Promise<void> => {
    setPickingApp(true)
    if (apps.length === 0) {
      try {
        const r = await omiApi.get<AppEntry[]>('/v1/apps', { params: { include_reviews: false } })
        setApps(Array.isArray(r.data) ? r.data : [])
      } catch {
        /* the picker degrades to an empty state */
      }
    }
  }

  const refetch = useCallback(async (): Promise<void> => {
    try {
      setConv(await fetchConversation())
    } catch {
      /* keep what we have */
    }
  }, [fetchConversation])

  const onToggleActionItem = async (idx: number): Promise<void> => {
    const items = conv?.structured?.action_items
    const item = items?.[idx]
    if (!conv || !items || !item) return
    const next = !item.completed
    const apply = (v: boolean): void =>
      setConv((c) =>
        c?.structured?.action_items
          ? {
              ...c,
              structured: {
                ...c.structured,
                action_items: c.structured.action_items.map((a, i) =>
                  i === idx ? { ...a, completed: v } : a
                )
              }
            }
          : c
      )
    apply(next)
    // The generated embedded ActionItem model has no `id` (backend/models/structured.py)
    // — hence the narrow rather than a plain property read.
    const itemId = (item as { id?: string }).id
    try {
      if (itemId) {
        // Standalone action item: `completed` is bound as a QUERY param
        // (backend/routers/action_items.py::toggle_action_item_completion) — a JSON
        // body is silently ignored and the missing query param 422s. Embedded items
        // never carry an id today, so this branch is currently unreachable; it is
        // kept (and pinned by a test) so a backend that starts returning ids does
        // not silently regress.
        await omiApi.patch(`/v1/action-items/${itemId}/completed`, null, {
          params: { completed: next }
        })
      } else {
        // Positional contract: SetConversationActionItemsStateRequest takes parallel
        // arrays and addresses items by INDEX, not id.
        await omiApi.patch(`/v1/conversations/${id}/action-items`, {
          items_idx: [idx],
          values: [next]
        })
      }
    } catch (e) {
      apply(!next)
      toast('Could not update task', { tone: 'error', body: (e as Error).message })
    }
  }

  // ── Shells ────────────────────────────────────────────────────────────────
  const shell = (body: React.ReactNode, title = 'Conversation'): React.JSX.Element => (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 items-center gap-3 px-6 pt-4 pb-3 lg:px-10">
        <button
          onClick={() => navigate('/conversations')}
          className="btn-ghost -ml-1 p-2"
          title="Back"
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h1 className="font-display text-xl font-bold text-white">{title}</h1>
      </header>
      {body}
    </div>
  )

  if (isPending) {
    return shell(
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-10 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-text-tertiary" aria-hidden />
        <p className="max-w-sm text-sm text-text-tertiary">
          Omi is still processing this conversation. It’ll appear in your list shortly.
        </p>
      </div>
    )
  }

  if (error) {
    return shell(<div className="px-10 py-8 text-sm text-text-tertiary">{error}</div>)
  }

  if (local) {
    return shell(
      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10">
        <div className="mx-auto max-w-3xl space-y-4">
          <p className="text-sm text-text-tertiary">{local.subtitle}</p>
          <div className="surface-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="section-label">{local.chatMessages ? 'Messages' : 'Transcript'}</h2>
              <button onClick={onCopyTranscript} className="btn-ghost px-2.5 py-1 text-[11px]">
                {copied === 'transcript' ? 'Copied' : 'Copy'}
              </button>
            </div>
            {local.chatMessages ? (
              <ul className="space-y-3">
                {local.chatMessages.map((m, i) => (
                  <li
                    key={i}
                    className={
                      m.role === 'user'
                        ? 'glass ml-auto max-w-[85%] rounded-2xl px-4 py-3 text-sm text-white'
                        : 'glass-subtle mr-auto max-w-[85%] rounded-2xl px-4 py-3 text-sm text-text-secondary'
                    }
                  >
                    <div className="mb-1 text-[10px] uppercase tracking-wide text-text-quaternary">
                      {m.role === 'user' ? 'You' : 'Omi'}
                    </div>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <pre className="whitespace-pre-wrap font-body text-sm leading-relaxed text-text-secondary">
                {local.transcript || '(no transcript)'}
              </pre>
            )}
          </div>
        </div>
      </div>,
      local.title
    )
  }

  if (!conv) {
    return shell(
      <div className="flex flex-1 items-center justify-center">
        <Spinner label="Loading conversation…" />
      </div>
    )
  }

  const structured = conv.structured ?? {}
  const title = structured.title || 'Conversation'
  const overview = structured.overview?.trim() ?? ''
  const actionItems = structured.action_items ?? []
  const insights = (conv.apps_results ?? []).filter((r) => r.content?.trim())
  const enriching = isEnriching(conv)
  const status = conv.status ?? ''
  const duration = conversationDuration(conv)
  const category = displayCategory(conv)
  const appName = (appId: string | null): string =>
    apps.find((a) => a.id === appId)?.name ?? 'App insight'

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      {/* ── Header / toolbar ─────────────────────────────────────────────── */}
      <header className="shrink-0 px-6 pt-4 pb-3 lg:px-10">
        <div className="flex items-start gap-3">
          <button
            onClick={() => navigate('/conversations')}
            className="btn-ghost -ml-1 mt-0.5 shrink-0 p-2"
            title="Back"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              {structured.emoji && (
                <span className="shrink-0 text-xl" aria-hidden>
                  {structured.emoji}
                </span>
              )}
              <h1 className="truncate font-display text-xl font-bold tracking-tight text-white">
                {title}
              </h1>
              <button
                onClick={() => setRenaming(true)}
                className="btn-ghost shrink-0 p-1"
                title="Edit title"
                aria-label="Edit title"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              {status && status !== 'completed' && (
                <span className="badge shrink-0 capitalize">{status.replace(/_/g, ' ')}</span>
              )}
            </div>
            <p className="mt-1 text-xs text-text-tertiary">{formatWhen(conv)}</p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => setDrawerOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded-full border border-border bg-white/[0.04] px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-white/10 hover:text-white"
              aria-expanded={drawerOpen}
            >
              {drawerOpen ? (
                <PanelRightClose className="h-3.5 w-3.5" />
              ) : (
                <PanelRightOpen className="h-3.5 w-3.5" />
              )}
              {drawerOpen ? 'Hide Transcript' : 'View Transcript'}
            </button>

            <ToolbarButton onClick={onCopyLink} title="Copy link">
              {copied === 'link' ? <Check className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
            </ToolbarButton>
            <ToolbarButton onClick={onCopyTranscript} title="Copy transcript">
              {copied === 'transcript' ? (
                <Check className="h-4 w-4" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </ToolbarButton>
            {folders.length > 0 && (
              <MoveToFolderMenu
                folders={folders}
                currentFolderId={conv.folder_id}
                onMove={onMoveToFolder}
              />
            )}
            <ToolbarButton onClick={() => setConfirmDelete(true)} title="Delete conversation">
              <Trash2 className="h-4 w-4" />
            </ToolbarButton>
          </div>
        </div>
      </header>

      {/* ── Body ─────────────────────────────────────────────────────────── */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-10 lg:px-10">
        <div className="mx-auto max-w-3xl space-y-4">
          {enriching ? (
            <div className="surface-card flex flex-col items-center gap-2 p-8 text-center">
              <Loader2 className="h-5 w-5 animate-spin text-text-tertiary" aria-hidden />
              <p className="text-sm text-white">Processing conversation…</p>
              <p className="text-xs text-text-tertiary">Generating summary and action items</p>
            </div>
          ) : (
            overview && (
              <section className="surface-card p-6">
                <h2 className="section-label mb-3 flex items-center gap-2">
                  <Sparkles className="h-3.5 w-3.5" aria-hidden />
                  Summary
                </h2>
                <div className="text-sm leading-relaxed text-text-secondary">
                  <Markdown text={overview} />
                </div>
              </section>
            )
          )}

          {/* Metadata chips */}
          <div className="flex flex-wrap items-center gap-2">
            <Chip>{conv.source ?? 'unknown'}</Chip>
            {duration != null && <Chip>{formatDuration(duration)}</Chip>}
            {category && <Chip>{category}</Chip>}
          </div>

          {insights.length > 0 && (
            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="section-label">App Insights</h2>
                <button
                  onClick={openAppPicker}
                  disabled={reprocessing}
                  className="btn-ghost px-2.5 py-1 text-[11px] disabled:opacity-40"
                >
                  {reprocessing ? 'Reprocessing…' : 'Reprocess'}
                </button>
              </div>
              {insights.map((r, i) => (
                <InsightCard key={r.app_id ?? i} appName={appName(r.app_id)} content={r.content} />
              ))}
            </section>
          )}

          {/* Try with Apps — always rendered */}
          <section className="surface-card p-6">
            <h2 className="section-label mb-3">Try with Apps</h2>
            {apps.length === 0 ? (
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-text-tertiary">
                  Run an Omi app over this conversation for extra insights.
                </p>
                <button
                  onClick={openAppPicker}
                  className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/10"
                >
                  Browse apps
                </button>
              </div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {apps.slice(0, 12).map((a) => (
                  <button
                    key={a.id}
                    onClick={() => onReprocess(a.id)}
                    disabled={reprocessing}
                    className="w-40 shrink-0 rounded-xl border border-border bg-white/[0.04] p-3 text-left transition-colors hover:bg-white/10 disabled:opacity-40"
                  >
                    <p className="truncate text-xs font-medium text-white">{a.name}</p>
                    <p className="mt-0.5 truncate text-[10px] text-text-quaternary">{a.author}</p>
                  </button>
                ))}
              </div>
            )}
          </section>

          {actionItems.length > 0 && (
            <section className="surface-card p-6">
              <h2 className="section-label mb-3">Action Items</h2>
              <ul className="space-y-1.5">
                {actionItems.map((a, i) => (
                  <li key={i} className="flex items-start gap-3 py-1">
                    <button
                      onClick={() => onToggleActionItem(i)}
                      aria-pressed={!!a.completed}
                      title={a.completed ? 'Mark as open' : 'Mark as done'}
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all ${
                        a.completed
                          ? 'border-white/30 bg-white/15 text-white'
                          : 'border-white/20 hover:border-white/45'
                      }`}
                    >
                      {a.completed && <Check className="h-3 w-3" strokeWidth={3} />}
                    </button>
                    <span
                      className={`text-sm leading-relaxed ${
                        a.completed ? 'text-text-quaternary line-through' : 'text-text-secondary'
                      }`}
                    >
                      {a.description}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      <TranscriptDrawer
        open={drawerOpen}
        segments={segments}
        people={people}
        onClose={() => setDrawerOpen(false)}
        onNameSpeaker={setNaming}
      />

      {renaming && (
        <RenameModal initial={title} onClose={() => setRenaming(false)} onSave={onRename} />
      )}

      {naming && (
        <NameSpeakerModal
          conversationId={id}
          segments={segments}
          segment={naming}
          people={people}
          onClose={() => setNaming(null)}
          onSaved={refetch}
          onPersonCreated={(p) => setPeople((prev) => [...prev, p])}
        />
      )}

      {pickingApp && (
        <ModalShell onClose={() => setPickingApp(false)} labelledBy="pick-app-title">
          <h2 id="pick-app-title" className="font-display text-lg font-semibold text-white">
            Reprocess with an app
          </h2>
          <div className="mt-4 max-h-[320px] space-y-1.5 overflow-y-auto">
            <button
              onClick={() => onReprocess()}
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-white hover:bg-white/10"
            >
              Default summary
            </button>
            {apps.map((a) => (
              <button
                key={a.id}
                onClick={() => onReprocess(a.id)}
                className="w-full truncate rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-white hover:bg-white/10"
              >
                {a.name}
              </button>
            ))}
          </div>
        </ModalShell>
      )}

      {confirmDelete && (
        <ModalShell onClose={() => setConfirmDelete(false)} labelledBy="delete-conv-title">
          <h2 id="delete-conv-title" className="font-display text-lg font-semibold text-white">
            Delete conversation?
          </h2>
          <p className="mt-2 text-sm text-text-tertiary">
            “{title}” will be permanently deleted. This cannot be undone.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button
              onClick={() => setConfirmDelete(false)}
              className="btn-ghost px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={onDelete}
              className="rounded-lg bg-error px-3 py-1.5 text-sm font-medium text-white"
            >
              Delete
            </button>
          </div>
        </ModalShell>
      )}
    </div>
  )
}
