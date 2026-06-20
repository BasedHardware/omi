import { useEffect, useRef, useState } from 'react'
import { X, ChevronDown, ChevronUp, Mic } from 'lucide-react'
import { liveConversation, type LiveStatus } from '../../lib/liveConversation'
import type { TranscriptLine } from '../../../../shared/types'
import { cn } from '../../lib/utils'

function fmtTime(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function SpeakerBubble({
  line,
  speakerNames,
  onRename
}: {
  line: TranscriptLine
  speakerNames: Record<string, string>
  onRename: (original: string, name: string) => void
}): React.JSX.Element {
  const rawSpeaker = line.speaker ?? 'Unknown'
  const displaySpeaker = speakerNames[rawSpeaker] ?? rawSpeaker
  const isUser = displaySpeaker === 'You' || rawSpeaker === 'You'
  const initial = displaySpeaker ? displaySpeaker[0].toUpperCase() : '?'

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const startEdit = (): void => {
    setDraft(displaySpeaker)
    setEditing(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  const commit = (): void => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== displaySpeaker) onRename(rawSpeaker, trimmed)
    setEditing(false)
  }

  return (
    <div className={cn('flex items-end gap-2', isUser ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white',
          isUser ? 'bg-[color:var(--accent)]' : 'bg-white/20'
        )}
      >
        {initial}
      </div>

      <div className={cn('flex max-w-[75%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        {/* Speaker label — click to rename */}
        {line.speaker && (
          editing ? (
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit()
                else if (e.key === 'Escape') setEditing(false)
              }}
              className="rounded border border-white/20 bg-black/40 px-1.5 py-0.5 text-[10px] text-white focus:border-white/50 focus:outline-none"
              style={{ width: `${Math.max(60, draft.length * 8)}px` }}
            />
          ) : (
            <button
              onClick={startEdit}
              title="Click to rename speaker"
              className="cursor-pointer rounded px-1 text-[10px] text-white/40 hover:bg-white/[0.06] hover:text-white/70"
            >
              {displaySpeaker}
            </button>
          )
        )}
        {/* Bubble */}
        <div
          className={cn(
            'rounded-2xl px-3 py-2 text-xs leading-relaxed text-white/90',
            isUser
              ? 'rounded-br-sm bg-[color:var(--accent)]/30'
              : 'rounded-bl-sm bg-white/10'
          )}
        >
          {line.text}
        </div>
      </div>
    </div>
  )
}

/**
 * Floating live transcript panel — mirrors macOS LiveTranscriptPanel.
 * Shown at the bottom-right while recording is active; collapses to a pill.
 * Speaker labels are clickable to rename (e.g. "Speaker 1" → "Alice").
 */
export function LiveTranscriptPanel(): React.JSX.Element | null {
  const [status, setStatus] = useState<LiveStatus>(() => liveConversation.getStatus())
  const [segments, setSegments] = useState<TranscriptLine[]>(() => liveConversation.getSegments())
  const [collapsed, setCollapsed] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  // Persistent speaker name map for this session: "Speaker 1" → "Alice"
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>({})
  const startRef = useRef<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    return liveConversation.subscribe(() => {
      setStatus(liveConversation.getStatus())
      setSegments([...liveConversation.getSegments()])
    })
  }, [])

  const isActive = status === 'live' || status === 'connecting'

  // Reset dismissed state and speaker names when a new session starts
  useEffect(() => {
    if (isActive) {
      setDismissed(false)
      setSpeakerNames({})
      if (startRef.current === null) startRef.current = Date.now()
      const id = setInterval(() => setElapsed(Date.now() - (startRef.current ?? Date.now())), 1000)
      return () => clearInterval(id)
    }
    startRef.current = null
    setElapsed(0)
    return undefined
  }, [isActive])

  // Auto-scroll to bottom when new segments arrive
  useEffect(() => {
    if (!collapsed && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [segments, collapsed])

  const handleRename = (original: string, name: string): void => {
    setSpeakerNames((prev) => ({ ...prev, [original]: name }))
  }

  if (!isActive || dismissed) return null

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 w-72 max-w-[calc(100vw-2rem)]">
      <div className="pointer-events-auto glass-strong overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
          </span>
          <Mic className="h-3 w-3 shrink-0 text-white/50" strokeWidth={1.75} />
          <span className="flex-1 text-xs font-semibold text-white/80">
            {status === 'connecting' ? 'Connecting…' : 'Live Transcript'}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-white/35">{fmtTime(elapsed)}</span>
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
            title={collapsed ? 'Expand' : 'Collapse'}
          >
            {collapsed ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="rounded-md p-1 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
            title="Dismiss"
          >
            <X className="h-3 w-3" />
          </button>
        </div>

        {/* Transcript body */}
        {!collapsed && (
          <div
            ref={scrollRef}
            className="flex max-h-64 flex-col gap-3 overflow-y-auto px-3 py-3"
          >
            {segments.length === 0 ? (
              <div className="py-4 text-center text-xs text-white/35">
                {status === 'connecting' ? 'Connecting to transcription…' : 'Listening…'}
              </div>
            ) : (
              segments.map((seg, i) => (
                <SpeakerBubble
                  key={i}
                  line={seg}
                  speakerNames={speakerNames}
                  onRename={handleRename}
                />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
