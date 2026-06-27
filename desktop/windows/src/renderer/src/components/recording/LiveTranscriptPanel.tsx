import { useEffect, useRef, useState } from 'react'
import { X, ChevronDown, ChevronUp, Mic } from 'lucide-react'
import { liveConversation, type LiveStatus } from '../../lib/liveConversation'
import type { TranscriptLine } from '../../../../shared/types'
import { cn } from '../../lib/utils'

function fmtTime(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Normalize raw speaker labels from Deepgram/Omi to a short display string
// "SPEAKER_00" → "S0", "Speaker 1" → "S1", "you" → "You", arbitrary → keep
function normalizeSpeaker(raw: string): string {
  const lower = raw.toLowerCase().trim()
  if (lower === 'you' || lower === 'user') return 'You'
  // Deepgram: SPEAKER_00, SPEAKER_01 …
  const dgMatch = raw.match(/^SPEAKER[_ ](\d+)$/i)
  if (dgMatch) return `S${parseInt(dgMatch[1], 10)}`
  // "Speaker 0", "Speaker 1"
  const spMatch = raw.match(/^Speaker\s+(\d+)$/i)
  if (spMatch) return `S${parseInt(spMatch[1], 10)}`
  return raw
}

// Stable per-speaker color palette matching macOS speakerColor() palette
// Maps canonical key (normalized label) → hue index
const SPEAKER_HUES = [
  { bg: 'bg-blue-500/25', text: 'text-blue-300', avatar: 'bg-blue-500/40', dot: 'bg-blue-400' },
  { bg: 'bg-violet-500/25', text: 'text-violet-300', avatar: 'bg-violet-500/40', dot: 'bg-violet-400' },
  { bg: 'bg-emerald-500/25', text: 'text-emerald-300', avatar: 'bg-emerald-500/40', dot: 'bg-emerald-400' },
  { bg: 'bg-amber-500/25', text: 'text-amber-300', avatar: 'bg-amber-500/40', dot: 'bg-amber-400' },
  { bg: 'bg-rose-500/25', text: 'text-rose-300', avatar: 'bg-rose-500/40', dot: 'bg-rose-400' },
  { bg: 'bg-cyan-500/25', text: 'text-cyan-300', avatar: 'bg-cyan-500/40', dot: 'bg-cyan-400' },
]
const USER_COLOR = { bg: 'bg-[color:var(--accent)]/20', text: 'text-white/80', avatar: 'bg-[color:var(--accent)]/50', dot: 'bg-white/60' }

function useSpeakerColors(): (key: string, isUser: boolean) => typeof USER_COLOR {
  const mapRef = useRef<Map<string, number>>(new Map())
  return (key: string, isUser: boolean) => {
    if (isUser) return USER_COLOR
    if (!mapRef.current.has(key)) {
      mapRef.current.set(key, mapRef.current.size % SPEAKER_HUES.length)
    }
    return SPEAKER_HUES[mapRef.current.get(key)!]
  }
}

function SpeakerBubble({
  line,
  speakerNames,
  isActive,
  getColor,
  onRename
}: {
  line: TranscriptLine
  speakerNames: Record<string, string>
  isActive: boolean
  getColor: (key: string, isUser: boolean) => typeof USER_COLOR
  onRename: (original: string, name: string) => void
}): React.JSX.Element {
  const rawSpeaker = line.speaker ?? 'Unknown'
  const normalized = normalizeSpeaker(rawSpeaker)
  const displaySpeaker = speakerNames[rawSpeaker] ?? normalized
  const isUser = displaySpeaker === 'You' || normalized === 'You'
  const colorSet = getColor(rawSpeaker, isUser)
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
      {/* Colored avatar */}
      <div
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white',
          colorSet.avatar
        )}
      >
        {initial}
      </div>

      <div className={cn('flex max-w-[75%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
        {/* Speaker chip with active pulse dot */}
        {line.speaker && (
          <div className="flex items-center gap-1">
            {isActive && (
              <span className={cn('h-1.5 w-1.5 rounded-full animate-speaker-pulse', colorSet.dot)} />
            )}
            {editing ? (
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
                className={cn(
                  'cursor-pointer rounded-full px-2 py-0.5 text-[10px] font-semibold transition-opacity',
                  colorSet.bg,
                  colorSet.text
                )}
              >
                {displaySpeaker}
              </button>
            )}
          </div>
        )}
        {/* Bubble */}
        <div
          className={cn(
            'rounded-2xl px-3 py-2 text-xs leading-relaxed text-white/90',
            isUser
              ? cn('rounded-br-sm', colorSet.bg)
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
 * Speaker labels are colored per-speaker (matching macOS speakerColor() palette)
 * and clickable to rename. The active speaker shows a pulsing dot.
 */
export function LiveTranscriptPanel(): React.JSX.Element | null {
  const [status, setStatus] = useState<LiveStatus>(() => liveConversation.getStatus())
  const [segments, setSegments] = useState<TranscriptLine[]>(() => liveConversation.getSegments())
  const [collapsed, setCollapsed] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>({})
  const startRef = useRef<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const getColor = useSpeakerColors()

  useEffect(() => {
    return liveConversation.subscribe(() => {
      setStatus(liveConversation.getStatus())
      setSegments([...liveConversation.getSegments()])
    })
  }, [])

  const isActive = status === 'live' || status === 'connecting'

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

  useEffect(() => {
    if (!collapsed && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [segments, collapsed])

  const handleRename = (original: string, name: string): void => {
    setSpeakerNames((prev) => ({ ...prev, [original]: name }))
  }

  if (!isActive || dismissed) return null

  // Most recent speaker — shown with pulse indicator
  const activeSpeaker = segments.length > 0 ? (segments[segments.length - 1].speaker ?? null) : null

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 w-72 max-w-[calc(100vw-2rem)]">
      <div className="pointer-events-auto glass-strong animate-spring-enter overflow-hidden rounded-2xl shadow-2xl">
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
                  isActive={seg.speaker === activeSpeaker && i === segments.length - 1}
                  getColor={getColor}
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
