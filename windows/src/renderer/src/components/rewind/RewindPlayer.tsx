import { useEffect, useState } from 'react'
import type { RewindFrame } from '../../../../shared/types'
import {
  frameIndexAtCursor,
  REWIND_ACTIVITY_GAP_MS,
  REWIND_COVER_PAD_MS
} from '../../../../shared/timelineGeometry'
import { relativeTime, isSameDay } from '../../../../shared/relativeTime'
import { parseWindowTitle } from '../../lib/windowTitle'

export function RewindPlayer({
  frames,
  cursorTs
}: {
  frames: RewindFrame[]
  cursorTs: number
}): React.JSX.Element {
  const [src, setSrc] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const idx = frameIndexAtCursor(
    frames.map((f) => f.ts),
    cursorTs,
    REWIND_ACTIVITY_GAP_MS,
    REWIND_COVER_PAD_MS
  )
  const frame = idx >= 0 ? frames[idx] : null

  useEffect(() => {
    let alive = true
    if (!frame) {
      setSrc(null)
      return
    }
    void window.omi.rewindFrameImage(frame.imagePath).then((dataUrl) => {
      if (alive) setSrc(dataUrl)
    })
    return () => {
      alive = false
    }
  }, [frame?.imagePath])

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg bg-black/40">
        {frame ? (
          src ? (
            <img
              src={src}
              alt="screen frame"
              onClick={() => setExpanded(true)}
              className="max-h-full max-w-full cursor-pointer object-contain"
            />
          ) : (
            <div className="text-white/40 text-sm">Loading…</div>
          )
        ) : (
          <div className="text-white/50 text-sm">
            {frames.length === 0
              ? 'No frames yet — enable Rewind capture in Settings.'
              : 'No screenshot at this moment.'}
          </div>
        )}
      </div>
      {frame && <FrameMeta frame={frame} />}
      {expanded && src && (
        <div
          onClick={() => setExpanded(false)}
          className="fixed inset-0 z-50 flex cursor-pointer items-center justify-center bg-black/90 p-6"
        >
          <img src={src} alt="screen frame" className="max-h-full max-w-full object-contain" />
        </div>
      )}
    </div>
  )
}

/** Time + app/window context for the frame under the cursor. */
function FrameMeta({ frame }: { frame: RewindFrame }): React.JSX.Element {
  const now = Date.now()
  const when = isSameDay(frame.ts, now)
    ? new Date(frame.ts).toLocaleTimeString()
    : new Date(frame.ts).toLocaleString()
  const { app, title } = parseWindowTitle(frame.windowTitle, frame.app || 'Unknown app')
  return (
    <div className="shrink-0 py-2 text-sm leading-snug">
      <div className="text-white/90">
        <span className="font-medium">{relativeTime(frame.ts, now)}</span>
        <span className="text-white/50"> · </span>
        <span className="text-white/70">{when}</span>
      </div>
      <div className="text-white/80">{app}</div>
      {title && <div className="truncate text-white/50">{title}</div>}
    </div>
  )
}
