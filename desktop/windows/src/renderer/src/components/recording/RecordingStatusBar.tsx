import { useEffect, useRef, useState } from 'react'
import { cn } from '../../lib/utils'
import { liveConversation, type LiveStatus } from '../../lib/liveConversation'
import { useAppState } from '../../state/AppStateProvider'

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/**
 * Compact recording/listening status pill for the sidebar.
 * Mirrors the macOS sidebar recording indicator: pulsing dot + label + elapsed
 * time + latest transcript snippet. Appears only while a live mic session or
 * manual recording is active; hidden when idle.
 */
export function RecordingStatusBar({
  collapsed
}: {
  collapsed: boolean
}): React.JSX.Element | null {
  const { recorder } = useAppState()
  const [liveStatus, setLiveStatus] = useState<LiveStatus>(() => liveConversation.getStatus())
  const [snippet, setSnippet] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  // Subscribe to the singleton live-conversation store so we react to
  // status changes (connecting → live → idle) and transcript arrivals.
  useEffect(() => {
    return liveConversation.subscribe(() => {
      setLiveStatus(liveConversation.getStatus())
      const segs = liveConversation.getSegments()
      const last = segs[segs.length - 1]
      // Show the tail of the latest segment — last 6 words so it fits the pill.
      setSnippet(last?.text?.trim().split(/\s+/).slice(-6).join(' ') ?? '')
    })
  }, [])

  // Active when the always-on session is connecting/live OR a manual recording
  // is running (screen-record or one-off mic via GlobalRecordButton).
  const isLiveActive = liveStatus === 'live' || liveStatus === 'connecting'
  const isActive = isLiveActive || recorder.recording

  // Elapsed timer: starts on first activation, resets to zero when idle.
  useEffect(() => {
    if (isActive) {
      if (startRef.current === null) startRef.current = Date.now()
      const id = setInterval(() => {
        setElapsed(Date.now() - (startRef.current ?? Date.now()))
      }, 1000)
      return () => clearInterval(id)
    }
    startRef.current = null
    setElapsed(0)
    return undefined
  }, [isActive])

  if (!isActive) return null

  const label = liveStatus === 'connecting' ? 'Connecting…' : 'Listening'
  // In expanded mode: show the live transcript snippet when there's one,
  // otherwise fall back to the status label. In collapsed mode, tooltip only.
  const displayText = snippet || label

  return (
    <div
      title={collapsed ? `${label} · ${fmt(elapsed)}` : undefined}
      className={cn(
        'mx-1 mb-1 flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.06] px-2.5 py-2 text-xs',
        collapsed && 'justify-center'
      )}
    >
      {/* Pulsing dot — same pattern used by many macOS recording indicators. */}
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-rose-500" />
      </span>

      {!collapsed && (
        <>
          <span className="flex-1 truncate text-white/70">{displayText}</span>
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-white/35">
            {fmt(elapsed)}
          </span>
        </>
      )}
    </div>
  )
}
