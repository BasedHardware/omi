import { useEffect, useRef, useState } from 'react'
import type { OcrLine, RewindFrame } from '../../../../shared/types'
import {
  frameIndexAtCursor,
  REWIND_ACTIVITY_GAP_MS,
  REWIND_COVER_PAD_MS
} from '../../../../shared/timelineGeometry'
import { relativeTime, isSameDay } from '../../../../shared/relativeTime'
import { parseWindowTitle } from '../../lib/windowTitle'
import {
  containedImageRect,
  highlightTerms,
  lineTextMatches,
  normalizedBoxToRect
} from '../../lib/rewindOverlay'
import { MAC_PURPLE, macPurple } from '../../lib/macPalette'

// Purple search-highlight per the Track 4 UI ruling (Mac ports its purple as-is
// for the Rewind bounding-box overlay — a deliberate exception to the
// otherwise de-purpled Rewind surface).
const HIGHLIGHT_STROKE = MAC_PURPLE
const HIGHLIGHT_FILL = macPurple('0.2')

export function RewindPlayer({
  frames,
  cursorTs,
  highlightQuery = '',
  loading = false
}: {
  frames: RewindFrame[]
  cursorTs: number
  /** Active search query — when set, matching OCR lines are boxed on the frame. */
  highlightQuery?: string
  /** True while the frame set is still loading from the local store. Gates the
   *  "No frames yet" empty state so it can't flash before the frames arrive. */
  loading?: boolean
}): React.JSX.Element {
  const [src, setSrc] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [ocrLines, setOcrLines] = useState<OcrLine[]>([])
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null)
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 })
  const containerRef = useRef<HTMLDivElement | null>(null)

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
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount / reset-on-dependency-change; not a self-retriggering loop
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

  // Load per-line OCR boxes for the current frame only while a search is active.
  const terms = highlightTerms(highlightQuery)
  const wantHighlight = terms.length > 0
  const frameId = frame?.id
  useEffect(() => {
    let alive = true
    if (!wantHighlight || frameId == null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset when highlight disabled / frame changes; not a self-retriggering loop
      setOcrLines([])
      return
    }
    void window.omi.rewindFrameOcrLines(frameId).then((lines) => {
      if (alive) setOcrLines(lines)
    })
    return () => {
      alive = false
    }
  }, [frameId, wantHighlight])

  // Track the container size so the normalized boxes map onto the letterboxed image.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = (): void => setBox({ w: el.clientWidth, h: el.clientHeight })
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const contained = natural ? containedImageRect(box.w, box.h, natural.w, natural.h) : null
  const matches =
    wantHighlight && contained && contained.width > 0
      ? ocrLines.filter((l) => lineTextMatches(l.text, terms))
      : []

  return (
    <div className="flex flex-1 flex-col min-h-0">
      <div
        ref={containerRef}
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-lg bg-black/40"
      >
        {frame ? (
          src ? (
            <img
              src={src}
              alt="screen frame"
              onClick={() => setExpanded(true)}
              onLoad={(e) =>
                setNatural({
                  w: e.currentTarget.naturalWidth,
                  h: e.currentTarget.naturalHeight
                })
              }
              className="max-h-full max-w-full cursor-pointer object-contain"
            />
          ) : (
            <div className="text-white/40 text-sm">Loading…</div>
          )
        ) : loading && frames.length === 0 ? (
          // Still loading the local frame set — show a neutral placeholder, not the
          // misleading "enable capture" message (the frames may already exist).
          <div className="text-white/40 text-sm">Loading…</div>
        ) : (
          <div className="text-white/50 text-sm">
            {frames.length === 0
              ? 'No frames yet — enable Rewind capture in Settings.'
              : 'No screenshot at this moment.'}
          </div>
        )}
        {contained &&
          matches.map((line, i) => {
            const r = normalizedBoxToRect(line, contained)
            return (
              <div
                key={i}
                className="pointer-events-none absolute rounded-[2px]"
                style={{
                  left: r.left,
                  top: r.top,
                  width: r.width,
                  height: r.height,
                  border: `2px solid ${HIGHLIGHT_STROKE}`,
                  backgroundColor: HIGHLIGHT_FILL
                }}
              />
            )
          })}
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
  // eslint-disable-next-line react-hooks/purity -- display-only timestamp, intentionally recomputed each render so relative labels stay current
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
