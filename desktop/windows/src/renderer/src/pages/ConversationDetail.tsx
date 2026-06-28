import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Loader2, Trash2, Sparkles, Copy, Check } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { invalidateConversationsCache } from '../lib/pageCache'
import { toast } from '../lib/toast'
import type { ChatMessage } from '../../../shared/types'
import { PageHeader } from '../components/layout/PageHeader'
import { Spinner } from '../components/ui/Spinner'

type ServerConversation = {
  id: string
  title?: string | null
  overview?: string | null
  status?: string | null
  transcript_segments?: { text: string; speaker?: string; start?: number; end?: number }[]
  structured?: {
    title?: string | null
    overview?: string | null
    action_items?: { id?: string; description: string; completed?: boolean }[]
    category?: string | null
    emoji?: string | null
  } | null
  created_at?: string
  finished_at?: string
}

type Display = {
  title: string
  emoji?: string
  subtitle?: string
  overview?: string
  segments?: { text: string; speaker?: string; start?: number; end?: number }[]
  transcript?: string
  actionItems?: { id?: string; description: string; completed?: boolean }[]
  chatMessages?: ChatMessage[]
  isLocal: boolean
  status?: string
  processing: boolean
}

function mapServer(c: ServerConversation): Display {
  const title = c.structured?.title || c.title || 'Conversation'
  const overview = c.structured?.overview || c.overview || ''
  const status = c.status ?? ''
  return {
    title,
    emoji: c.structured?.emoji || undefined,
    subtitle: c.created_at ? new Date(c.created_at).toLocaleString() : undefined,
    overview,
    segments: c.transcript_segments,
    actionItems: c.structured?.action_items,
    isLocal: false,
    status,
    processing: status === 'processing'
  }
}

function CopyTranscriptButton(props: { transcript: string }): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(props.transcript)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          /* fall through */
        }
      }}
      className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-black/15 px-2.5 py-1 text-[11px] text-white/65 transition-colors hover:bg-black/30 hover:text-white"
      title="Copy transcript"
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function speakerColor(label: string): string {
  // Stable hash from label → one of a handful of glass tints.
  const palette = [
    'border-emerald-400/30 bg-emerald-400/8 text-emerald-200',
    'border-sky-400/30 bg-sky-400/8 text-sky-200',
    'border-violet-400/30 bg-violet-400/8 text-violet-200',
    'border-amber-400/30 bg-amber-400/8 text-amber-200',
    'border-rose-400/30 bg-rose-400/8 text-rose-200',
    'border-white/15 bg-white/5 text-white/75'
  ]
  let h = 0
  for (let i = 0; i < label.length; i++) h = (h * 31 + label.charCodeAt(i)) | 0
  return palette[Math.abs(h) % palette.length]
}

function formatStart(seconds?: number): string {
  if (seconds == null) return ''
  const s = Math.max(0, Math.floor(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

export function ConversationDetail({ conversationId }: { conversationId: string }): React.JSX.Element {
  const id = conversationId
  const navigate = useNavigate()
  const [display, setDisplay] = useState<Display | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)
  const pollHandle = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchServer = async (idStr: string): Promise<Display | null> => {
    const r = await omiApi.get<ServerConversation>(`/v1/conversations/${idStr}`)
    return mapServer(r.data)
  }

  const load = async (idStr: string, isLocal: boolean): Promise<void> => {
    try {
      if (isLocal) {
        const c = await window.omi.getLocalConversation(idStr)
        if (!c) {
          setError('Local conversation not found')
          return
        }
        if (c.kind === 'chat') {
          setDisplay({
            title: c.title || 'Chat with Omi',
            subtitle: `${new Date(c.startedAt).toLocaleString()} · ${c.messages?.length ?? 0} messages`,
            chatMessages: c.messages ?? [],
            transcript: c.transcript,
            isLocal: true,
            processing: false
          })
          return
        }
        setDisplay({
          title: c.title || 'Recording',
          subtitle: `${new Date(c.startedAt).toLocaleString()} · ${Math.round(
            (c.endedAt - c.startedAt) / 1000
          )}s · local only`,
          transcript: c.transcript,
          segments: c.transcript
            ? [{ text: c.transcript, speaker: 'SPEAKER_00', start: 0 }]
            : undefined,
          isLocal: true,
          processing: false
        })
        return
      }
      const d = await fetchServer(idStr)
      if (d) setDisplay(d)
    } catch (e) {
      console.error('ConversationDetail load failed:', e)
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    if (!id) return
    const isLocal = id.startsWith('local-') || id.startsWith('chat-')
    setError(null)
    setDisplay(null)
    load(id, isLocal)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Poll while Omi is still processing — title/overview/action_items become
  // available once the pipeline finishes summarizing the segments we POSTed.
  useEffect(() => {
    if (!id || !display || display.isLocal) return
    if (!display.processing) {
      if (pollHandle.current) {
        clearInterval(pollHandle.current)
        pollHandle.current = null
      }
      return
    }
    if (pollHandle.current) return
    let ticks = 0
    pollHandle.current = setInterval(async () => {
      ticks++
      try {
        const d = await fetchServer(id)
        if (d) setDisplay(d)
        if (d && !d.processing) {
          if (pollHandle.current) clearInterval(pollHandle.current)
          pollHandle.current = null
        }
      } catch {
        /* retry next tick */
      }
      // Give up after ~60s; user can still refresh manually.
      if (ticks > 20) {
        if (pollHandle.current) clearInterval(pollHandle.current)
        pollHandle.current = null
      }
    }, 3000)
    return () => {
      if (pollHandle.current) clearInterval(pollHandle.current)
      pollHandle.current = null
    }
  }, [id, display])

  const onRefresh = async (): Promise<void> => {
    if (!id || refreshing) return
    setRefreshing(true)
    const isLocal = id.startsWith('local-') || id.startsWith('chat-')
    await load(id, isLocal)
    setRefreshing(false)
  }

  const onDeleteLocal = async (): Promise<void> => {
    if (!id) return
    if (!confirm('Delete this local recording? This cannot be undone.')) return
    try {
      await window.omi.deleteLocalConversation(id)
      invalidateConversationsCache()
      toast('Recording deleted', { tone: 'info' })
      navigate('/conversations')
    } catch (e) {
      toast('Delete failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const onRename = async (title: string): Promise<void> => {
    if (!id || !display) return
    const prev = display.title
    // Optimistic — update the heading immediately, revert if the write fails.
    setDisplay((d) => (d ? { ...d, title } : d))
    try {
      await window.omi.updateLocalConversationTitle(id, title)
      invalidateConversationsCache()
    } catch (e) {
      setDisplay((d) => (d ? { ...d, title: prev } : d))
      toast('Rename failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const onToggleActionItem = async (idx: number): Promise<void> => {
    if (!display?.actionItems) return
    const item = display.actionItems[idx]
    if (!item) return
    const next = !item.completed
    // Optimistic
    setDisplay((d) =>
      d && d.actionItems
        ? {
            ...d,
            actionItems: d.actionItems.map((a, i) => (i === idx ? { ...a, completed: next } : a))
          }
        : d
    )
    try {
      if (item.id) {
        await omiApi.patch(`/v1/action-items/${item.id}/completed`, { completed: next })
      } else if (id) {
        await omiApi.patch(`/v1/conversations/${id}/action-items`, {
          action_item_idx: idx,
          completed: next
        })
      }
    } catch (e) {
      // Revert
      setDisplay((d) =>
        d && d.actionItems
          ? {
              ...d,
              actionItems: d.actionItems.map((a, i) =>
                i === idx ? { ...a, completed: !next } : a
              )
            }
          : d
      )
      toast('Could not update task', { tone: 'error', body: (e as Error).message })
    }
  }

  const onReprocess = async (): Promise<void> => {
    if (!id || reprocessing) return
    setReprocessing(true)
    try {
      await omiApi.post(`/v1/conversations/${id}/reprocess`)
      toast('Reprocessing', { tone: 'info', body: 'Omi is regenerating the summary.' })
      // Trigger polling by marking processing=true locally.
      setDisplay((d) => (d ? { ...d, processing: true, status: 'processing' } : d))
    } catch (e) {
      toast('Reprocess failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setReprocessing(false)
    }
  }

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Conversation" onBack={() => navigate('/conversations')} />
        <div className="px-10 py-8 text-sm text-white/60">{error}</div>
      </div>
    )
  }
  if (!display) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Conversation" onBack={() => navigate('/conversations')} />
        <div className="flex flex-1 items-center justify-center">
          <Spinner label="Loading conversation…" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={display.emoji ? `${display.emoji} ${display.title}` : display.title}
        subtitle={display.subtitle}
        onBack={() => navigate('/conversations')}
        onRename={display.isLocal ? onRename : undefined}
        actions={
          <div className="flex items-center gap-2">
            {display.processing && (
              <span className="badge flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" />
                Processing
              </span>
            )}
            {display.isLocal ? (
              <>
                <span className={display.chatMessages ? 'badge' : 'badge-warning'}>
                  {display.chatMessages ? 'Chat' : 'local'}
                </span>
                <button
                  onClick={onDeleteLocal}
                  className="btn-ghost px-3 py-2"
                  title={display.chatMessages ? 'Delete chat' : 'Delete recording'}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={onReprocess}
                  disabled={reprocessing || display.processing}
                  className="btn-ghost px-3 py-2 disabled:opacity-50"
                  title="Re-run Omi's summarization"
                >
                  <Sparkles className={`h-4 w-4 ${reprocessing ? 'animate-pulse' : ''}`} />
                </button>
                <button
                  onClick={onRefresh}
                  disabled={refreshing}
                  className="btn-ghost px-3 py-2 disabled:opacity-50"
                  title="Refresh from Omi"
                >
                  <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
              </>
            )}
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-3xl">
          <div className="space-y-4">
            {display.overview && (
              <div className="surface-card p-6 animate-fade-in">
                <h2 className="section-label mb-3">Summary</h2>
                <p className="text-sm leading-relaxed text-white/85">{display.overview}</p>
              </div>
            )}
            {display.actionItems && display.actionItems.length > 0 && (
              <div className="surface-card p-6 animate-fade-in">
                <h2 className="section-label mb-3">Action items</h2>
                <ul className="space-y-1.5">
                  {display.actionItems.map((a, i) => (
                    <li key={i} className="flex items-start gap-3 py-1">
                      <button
                        onClick={() => onToggleActionItem(i)}
                        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all duration-200 ${
                          a.completed
                            ? 'border-white/30 bg-white/15 text-white'
                            : 'border-white/20 hover:border-white/45'
                        }`}
                        aria-pressed={!!a.completed}
                        title={a.completed ? 'Mark as open' : 'Mark as done'}
                      >
                        {a.completed && (
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="h-3 w-3"
                          >
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </button>
                      <span
                        className={`text-sm leading-relaxed transition-colors ${
                          a.completed ? 'text-white/40 line-through' : 'text-white/85'
                        }`}
                      >
                        {a.description}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="surface-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="section-label">{display.chatMessages ? 'Messages' : 'Transcript'}</h2>
                <CopyTranscriptButton
                  transcript={
                    display.segments
                      ? display.segments
                          .map((s) => `${s.speaker ? `[${s.speaker}] ` : ''}${s.text}`)
                          .join('\n\n')
                      : (display.transcript ?? '')
                  }
                />
              </div>
              <div className="max-h-[60vh] overflow-y-auto pr-1 -mr-1">
              {display.chatMessages ? (
                <ul className="space-y-3">
                  {display.chatMessages.map((m, i) => (
                    <li
                      key={i}
                      className={
                        m.role === 'user'
                          ? 'glass ml-auto max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed text-white'
                          : 'glass-subtle mr-auto max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed text-white/75'
                      }
                    >
                      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-white/40">
                        {m.role === 'user' ? 'You' : 'Omi'}
                      </div>
                      <div className="whitespace-pre-wrap">{m.content}</div>
                    </li>
                  ))}
                </ul>
              ) : display.segments && display.segments.length > 0 ? (
                <ul className="space-y-4">
                  {display.segments.map((s, i) => {
                    const label = s.speaker || 'speaker'
                    return (
                      <li key={i} className="flex gap-3 animate-fade-in">
                        <span
                          className={`shrink-0 self-start rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${speakerColor(
                            label
                          )}`}
                        >
                          {label.replace(/^SPEAKER_/, 'S')}
                        </span>
                        <div className="min-w-0 flex-1">
                          {s.start != null && (
                            <div className="text-[10px] font-mono text-white/35">
                              {formatStart(s.start)}
                            </div>
                          )}
                          <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/85">
                            {s.text}
                          </p>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <pre className="whitespace-pre-wrap font-body text-sm leading-relaxed text-white/75">
                  {display.transcript || '(no transcript)'}
                </pre>
              )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
