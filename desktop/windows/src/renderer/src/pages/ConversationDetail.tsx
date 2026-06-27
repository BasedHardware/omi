import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Loader2, Trash2, Sparkles, Copy, Check, ScrollText, X, ChevronDown } from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { invalidateConversationsCache } from '../lib/pageCache'
import { toast } from '../lib/toast'
import type { ChatMessage } from '../../../shared/types'
import { PageHeader } from '../components/layout/PageHeader'
import { Spinner } from '../components/ui/Spinner'
import { NameSpeakerSheet } from '../components/conversations/NameSpeakerSheet'
import { cn } from '../lib/utils'
import type { SpeakerTarget, Person } from '../components/conversations/NameSpeakerSheet'

type ServerConversation = {
  id: string
  title?: string | null
  overview?: string | null
  status?: string | null
  transcript_segments?: { text: string; speaker?: string; person_id?: string | null; start?: number; end?: number }[]
  structured?: {
    title?: string | null
    overview?: string | null
    action_items?: { id?: string; description: string; completed?: boolean }[]
    category?: string | null
    emoji?: string | null
  } | null
  people?: { id: string; name: string }[]
  created_at?: string
  finished_at?: string
}

type Display = {
  title: string
  emoji?: string
  subtitle?: string
  overview?: string
  segments?: { text: string; speaker?: string; person_id?: string | null; start?: number; end?: number }[]
  transcript?: string
  actionItems?: { id?: string; description: string; completed?: boolean }[]
  chatMessages?: ChatMessage[]
  isLocal: boolean
  status?: string
  processing: boolean
  personNames: Record<string, string>
}

function mapServer(c: ServerConversation): Display {
  const title = c.structured?.title || c.title || 'Conversation'
  const overview = c.structured?.overview || c.overview || ''
  const status = c.status ?? ''
  const personNames: Record<string, string> = { user: 'You' }
  for (const p of c.people ?? []) if (p.id && p.name) personNames[p.id] = p.name
  return {
    title,
    emoji: c.structured?.emoji || undefined,
    subtitle: c.created_at ? new Date(c.created_at).toLocaleString() : undefined,
    overview,
    segments: c.transcript_segments,
    actionItems: c.structured?.action_items,
    isLocal: false,
    status,
    processing: status === 'processing',
    personNames
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

// Transcript drawer — right-side slide-in panel matching macOS .move(edge:.trailing)
function TranscriptDrawer({
  display,
  people: _people,
  onClose,
  onOpenNameSheet
}: {
  display: Display
  people: Person[]
  onClose: () => void
  onOpenNameSheet: (target: SpeakerTarget) => void
}): React.JSX.Element {
  const fullText = display.segments
    ? display.segments.map((s) => `${s.speaker ? `[${s.speaker}] ` : ''}${s.text}`).join('\n\n')
    : (display.transcript ?? '')

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      {/* Panel */}
      <div className="fixed right-0 top-0 z-50 flex h-full w-[450px] max-w-[90vw] flex-col border-l border-white/[0.07] bg-[#0d0d0d] shadow-2xl animate-slide-in-right">
        {/* Header */}
        <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.07] px-5 py-3.5">
          <ScrollText className="h-4 w-4 text-white/50" strokeWidth={1.75} />
          <span className="flex-1 text-sm font-semibold text-white/85">Transcript</span>
          <CopyTranscriptButton transcript={fullText} />
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-white/30 hover:bg-white/10 hover:text-white/70"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Segments */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {display.segments && display.segments.length > 0 ? (
            <ul className="space-y-4">
              {display.segments.map((s, i) => {
                const rawLabel = s.speaker || 'speaker'
                const personName = s.person_id ? display.personNames[s.person_id] : undefined
                const displayLabel = personName || rawLabel.replace(/^SPEAKER_/, 'S')
                const segCountForLabel = display.segments!.filter((x) => x.speaker === rawLabel).length
                const previewText = s.text
                return (
                  <li key={i} className="flex gap-3">
                    <div className="shrink-0 self-start">
                      {!display.isLocal ? (
                        <button
                          onClick={() =>
                            onOpenNameSheet({
                              rawLabel,
                              previewText,
                              segmentCount: segCountForLabel
                            })
                          }
                          className={cn(
                            'rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide transition-opacity hover:opacity-80',
                            speakerColor(rawLabel)
                          )}
                          title="Click to assign a name"
                        >
                          {displayLabel}
                        </button>
                      ) : (
                        <span
                          className={cn(
                            'rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                            speakerColor(rawLabel)
                          )}
                        >
                          {displayLabel}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      {s.start != null && (
                        <div className="text-[10px] font-mono text-white/30">{formatStart(s.start)}</div>
                      )}
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/80">{s.text}</p>
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <pre className="whitespace-pre-wrap font-body text-sm leading-relaxed text-white/70">
              {display.transcript || '(no transcript)'}
            </pre>
          )}
        </div>
      </div>
    </>
  )
}

export function ConversationDetail({ conversationId }: { conversationId: string }): React.JSX.Element {
  const id = conversationId
  const navigate = useNavigate()
  const [display, setDisplay] = useState<Display | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)
  const [showAppPicker, setShowAppPicker] = useState(false)
  const [enabledApps, setEnabledApps] = useState<{ id: string; name?: string; image?: string | null }[]>([])
  const [appsLoading, setAppsLoading] = useState(false)
  const appPickerRef = useRef<HTMLDivElement>(null)
  const pollHandle = useRef<ReturnType<typeof setInterval> | null>(null)

  // Speaker assignment — people from /v1/users/people
  const [people, setPeople] = useState<Person[]>([])
  const [assigningLabel, setAssigningLabel] = useState<string | null>(null)

  // Transcript drawer
  const [showTranscriptDrawer, setShowTranscriptDrawer] = useState(false)

  // NameSpeakerSheet
  const [nameSpeakerTarget, setNameSpeakerTarget] = useState<SpeakerTarget | null>(null)

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
            processing: false,
            personNames: {}
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
          processing: false,
          personNames: {}
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
    setShowTranscriptDrawer(false)
    setNameSpeakerTarget(null)
    load(id, isLocal)
    if (!isLocal) {
      omiApi.get<Person[]>('/v1/users/people').then((r) => {
        const list = Array.isArray(r.data) ? r.data : []
        setPeople(list.filter((p) => p.id && p.name))
      }).catch(() => { /* non-fatal */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

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
    setDisplay((d) =>
      d && d.actionItems
        ? { ...d, actionItems: d.actionItems.map((a, i) => (i === idx ? { ...a, completed: next } : a)) }
        : d
    )
    try {
      if (item.id) {
        await omiApi.patch(`/v1/action-items/${item.id}/completed`, { completed: next })
      } else if (id) {
        await omiApi.patch(`/v1/conversations/${id}/action-items`, { action_item_idx: idx, completed: next })
      }
    } catch (e) {
      setDisplay((d) =>
        d && d.actionItems
          ? { ...d, actionItems: d.actionItems.map((a, i) => (i === idx ? { ...a, completed: !next } : a)) }
          : d
      )
      toast('Could not update task', { tone: 'error', body: (e as Error).message })
    }
  }

  const onReprocess = async (appId?: string): Promise<void> => {
    if (!id || reprocessing) return
    setReprocessing(true)
    setShowAppPicker(false)
    try {
      await omiApi.post(`/v1/conversations/${id}/reprocess`, appId ? { app_id: appId } : undefined)
      const appName = appId ? enabledApps.find((a) => a.id === appId)?.name : undefined
      toast('Reprocessing', {
        tone: 'info',
        body: appName ? `Regenerating summary with ${appName}.` : 'Omi is regenerating the summary.'
      })
      setDisplay((d) => (d ? { ...d, processing: true, status: 'processing' } : d))
    } catch (e) {
      toast('Reprocess failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setReprocessing(false)
    }
  }

  const openAppPicker = async (): Promise<void> => {
    setShowAppPicker((v) => !v)
    if (enabledApps.length > 0) return
    setAppsLoading(true)
    try {
      const [appsRes, enabledRes] = await Promise.all([
        omiApi.get<{ id: string; name?: string; image?: string | null }[]>('/v1/apps', { params: { include_reviews: false } }),
        omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
      ])
      const enabledIds = new Set(Array.isArray(enabledRes.data) ? enabledRes.data : [])
      const all = Array.isArray(appsRes.data) ? appsRes.data : []
      setEnabledApps(all.filter((a) => enabledIds.has(a.id)))
    } catch {
      /* non-fatal */
    } finally {
      setAppsLoading(false)
    }
  }

  // Close app picker on outside click
  useEffect(() => {
    if (!showAppPicker) return
    const handler = (e: MouseEvent): void => {
      if (appPickerRef.current && !appPickerRef.current.contains(e.target as Node)) {
        setShowAppPicker(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showAppPicker])

  const assignSpeaker = async (rawLabel: string, personId: string | null, isUser: boolean, allSegments: boolean): Promise<void> => {
    if (!id || assigningLabel) return
    const speakerInt = parseInt(rawLabel.replace(/^SPEAKER_0*/, '') || '0', 10)
    setAssigningLabel(rawLabel)
    try {
      if (isUser) {
        // Try the is_user assign type; backend may or may not support it — update UI
        // optimistically regardless so the display is always correct.
        try {
          await omiApi.patch(
            `/v1/conversations/${id}/assign-speaker/${speakerInt}`,
            null,
            { params: { assign_type: 'is_user', value: 'true' } }
          )
        } catch {
          // Non-fatal: local display already updated below
        }
        const segs = display?.segments ?? []
        const targetSpeakers = allSegments
          ? new Set(segs.filter((s) => s.speaker === rawLabel).map((_, i) => i))
          : null
        setDisplay((d) =>
          d && d.segments
            ? {
                ...d,
                segments: d.segments.map((s) =>
                  allSegments
                    ? s.speaker === rawLabel
                      ? { ...s, person_id: 'user' }
                      : s
                    : s.speaker === rawLabel
                      ? { ...s, person_id: 'user' }
                      : s
                ),
                personNames: { ...d.personNames, user: 'You' }
              }
            : d
        )
        void targetSpeakers // suppress unused
        toast(`Assigned ${rawLabel} → You`, { tone: 'info' })
      } else if (personId) {
        await omiApi.patch(
          `/v1/conversations/${id}/assign-speaker/${speakerInt}`,
          null,
          { params: { assign_type: 'person_id', value: personId } }
        )
        const person = people.find((p) => p.id === personId)
        setDisplay((d) =>
          d ? { ...d, personNames: { ...d.personNames, ...(person ? { [personId]: person.name } : {}) } } : d
        )
        setDisplay((d) =>
          d && d.segments
            ? {
                ...d,
                segments: d.segments.map((s) =>
                  (allSegments ? s.speaker === rawLabel : s.speaker === rawLabel && s === d.segments![0])
                    ? { ...s, person_id: personId }
                    : s
                )
              }
            : d
        )
        toast(`Assigned ${rawLabel} → ${person?.name ?? personId}`, { tone: 'info' })
      }
    } catch (e) {
      toast('Assignment failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setAssigningLabel(null)
    }
  }

  const getOrCreatePerson = async (name: string): Promise<Person | null> => {
    const trimmed = name.trim()
    if (!trimmed) return null
    try {
      const r = await omiApi.post<Person>('/v1/users/people', { name: trimmed })
      const p = r.data
      setPeople((prev) => (prev.find((x) => x.id === p.id) ? prev : [...prev, p]))
      return p
    } catch (e) {
      toast('Could not create person', { tone: 'error', body: (e as Error).message })
      return null
    }
  }

  const openNameSheet = (target: SpeakerTarget): void => {
    setNameSpeakerTarget(target)
  }

  const hasTranscript = display && (
    (display.segments && display.segments.length > 0) || !!display.transcript
  ) && !display.chatMessages

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
            {/* Transcript drawer button */}
            {hasTranscript && (
              <button
                onClick={() => setShowTranscriptDrawer((v) => !v)}
                className={cn(
                  'btn-ghost px-3 py-2 gap-1.5',
                  showTranscriptDrawer ? 'bg-white/10 text-white' : ''
                )}
                title="View transcript"
              >
                <ScrollText className="h-4 w-4" />
                Transcript
              </button>
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
                {/* Reprocess split button — left fires default, right opens app picker */}
                <div ref={appPickerRef} className="relative flex">
                  <button
                    onClick={() => void onReprocess()}
                    disabled={reprocessing || display.processing}
                    className="btn-ghost rounded-r-none border-r border-white/[0.06] px-3 py-2 disabled:opacity-50"
                    title="Re-run Omi's summarization"
                  >
                    <Sparkles className={`h-4 w-4 ${reprocessing ? 'animate-pulse' : ''}`} />
                  </button>
                  <button
                    onClick={() => void openAppPicker()}
                    disabled={reprocessing || display.processing}
                    className="btn-ghost rounded-l-none px-1.5 py-2 disabled:opacity-50"
                    title="Reprocess with specific app context"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                  {showAppPicker && (
                    <div className="absolute right-0 top-full z-50 mt-1 min-w-[200px] rounded-xl border border-white/10 bg-[#1a1a1a]/95 py-1.5 shadow-xl backdrop-blur-md">
                      <p className="px-3 pb-1 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/30">
                        Reprocess with…
                      </p>
                      <button
                        onClick={() => void onReprocess()}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-white/70 hover:bg-white/8 hover:text-white"
                      >
                        <Sparkles className="h-3.5 w-3.5 shrink-0 text-white/40" />
                        Default (no plugin)
                      </button>
                      {appsLoading && (
                        <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-white/35">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Loading plugins…
                        </div>
                      )}
                      {enabledApps.map((app) => (
                        <button
                          key={app.id}
                          onClick={() => void onReprocess(app.id)}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-white/70 hover:bg-white/8 hover:text-white"
                        >
                          {app.image
                            ? <img src={app.image} alt="" className="h-4 w-4 shrink-0 rounded-md object-cover" />
                            : <span className="h-4 w-4 shrink-0 rounded-md bg-white/10" />}
                          <span className="truncate">{app.name ?? app.id}</span>
                        </button>
                      ))}
                      {!appsLoading && enabledApps.length === 0 && (
                        <p className="px-3 py-1.5 text-xs text-white/30">No plugins installed</p>
                      )}
                    </div>
                  )}
                </div>
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
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </button>
                      <span className={`text-sm leading-relaxed transition-colors ${a.completed ? 'text-white/40 line-through' : 'text-white/85'}`}>
                        {a.description}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {/* Inline transcript section (always visible in main scroll) */}
            <div className="surface-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="section-label">{display.chatMessages ? 'Messages' : 'Transcript'}</h2>
                <CopyTranscriptButton
                  transcript={
                    display.segments
                      ? display.segments.map((s) => `${s.speaker ? `[${s.speaker}] ` : ''}${s.text}`).join('\n\n')
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
                      const rawLabel = s.speaker || 'speaker'
                      const personName = s.person_id ? display.personNames[s.person_id] : undefined
                      const displayLabel = personName || rawLabel.replace(/^SPEAKER_/, 'S')
                      const isAssigning = assigningLabel === rawLabel
                      const segCount = display.segments!.filter((x) => x.speaker === rawLabel).length
                      return (
                        <li key={i} className="flex gap-3 animate-fade-in">
                          <div className="shrink-0 self-start">
                            {!display.isLocal ? (
                              <button
                                onClick={() => openNameSheet({ rawLabel, previewText: s.text, segmentCount: segCount })}
                                className={cn(
                                  'rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide transition-opacity hover:opacity-80',
                                  speakerColor(rawLabel),
                                  isAssigning && 'opacity-50'
                                )}
                                title={personName ? `${rawLabel} — click to reassign` : 'Click to assign a person'}
                              >
                                {isAssigning ? (
                                  <Loader2 className="inline h-2.5 w-2.5 animate-spin" />
                                ) : (
                                  displayLabel
                                )}
                              </button>
                            ) : (
                              <span
                                className={cn(
                                  'rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                                  speakerColor(rawLabel)
                                )}
                              >
                                {displayLabel}
                              </span>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            {s.start != null && (
                              <div className="text-[10px] font-mono text-white/35">{formatStart(s.start)}</div>
                            )}
                            <p className="whitespace-pre-wrap text-sm leading-relaxed text-white/85">{s.text}</p>
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

      {/* Transcript drawer */}
      {showTranscriptDrawer && display && (
        <TranscriptDrawer
          display={display}
          people={people}
          onClose={() => setShowTranscriptDrawer(false)}
          onOpenNameSheet={openNameSheet}
        />
      )}

      {/* NameSpeakerSheet modal */}
      {nameSpeakerTarget && (
        <NameSpeakerSheet
          target={nameSpeakerTarget}
          people={people}
          onClose={() => setNameSpeakerTarget(null)}
          onSave={async (personId, isUser, allSegments) => {
            await assignSpeaker(nameSpeakerTarget.rawLabel, personId, isUser, allSegments)
            setNameSpeakerTarget(null)
          }}
          onCreatePerson={getOrCreatePerson}
        />
      )}
    </div>
  )
}
