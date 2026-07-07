import { useEffect, useRef } from 'react'
import type { RewindFrame } from '../../../../shared/types'
import {
  tsToX,
  xToTs,
  axisTicks,
  activitySegments,
  REWIND_ACTIVITY_GAP_MS
} from '../../../../shared/timelineGeometry'
import { useElementWidth } from '../../hooks/useElementWidth'
import { isSameDay } from '../../../../shared/relativeTime'

const clockLabel = (ts: number): string =>
  new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const dateLabel = (ts: number): string =>
  new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' })

// Fixed horizontal time scale, so the activity bar is a SCROLLABLE broad timeline
// you can pan across — not a squished fit-to-width overview. Larger = more zoomed
// in (a longer history overflows the viewport and scrolls).
const PX_PER_HOUR = 140

// Axis ticks aligned to LOCAL time boundaries (round local hours/days), so labels
// don't land on UTC boundaries that render as e.g. "20:00". Reuses the shared
// spacing logic on timestamps shifted into local-wall-clock space, then shifts the
// results back to real timestamps. (Doesn't touch the shared, unit-tested fn.)
function localAxisTicks(minTs: number, maxTs: number, maxTicks: number): number[] {
  const off = new Date().getTimezoneOffset() * 60_000
  return axisTicks(minTs - off, maxTs - off, maxTicks).map((t) => t + off)
}

export function RewindTimelineBar({
  frames,
  bounds,
  cursorTs,
  onSeek
}: {
  frames: RewindFrame[]
  bounds: { min: number; max: number } | null
  cursorTs: number
  onSeek: (ts: number) => void
}): React.JSX.Element {
  const outerRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const viewWidth = useElementWidth(outerRef) || 600

  // Span the loaded frames (sorted ascending); `bounds` is only a fallback. Using
  // all-time bounds made the axis span days, so labels were wrong-scale.
  const dataMin = frames.length > 0 ? frames[0].ts : bounds?.min
  const dataMax = frames.length > 0 ? frames[frames.length - 1].ts : bounds?.max
  const hasSpan = dataMin != null && dataMax != null && dataMax > dataMin
  const minTs = dataMin ?? 0
  const maxTs = dataMax ?? 0

  // Content is laid out at the fixed scale, but never narrower than the viewport.
  const contentWidth = hasSpan
    ? Math.max(viewWidth, ((maxTs - minTs) / 3_600_000) * PX_PER_HOUR)
    : viewWidth
  const span = hasSpan ? { minTs, maxTs, width: contentWidth } : null

  const seekFromEvent = (clientX: number): void => {
    if (!innerRef.current || !span) return
    const rect = innerRef.current.getBoundingClientRect()
    onSeek(xToTs(clientX - rect.left, span))
  }

  const ticks = span ? localAxisTicks(minTs, maxTs, Math.max(4, Math.round(contentWidth / 110))) : []
  const segments = span ? activitySegments(frames.map((f) => f.ts), REWIND_ACTIVITY_GAP_MS) : []

  // Center the cursor whenever it actually CHANGES — the initial open position
  // (the newest frame, so the bar lands on the recent edge), a seek, or live-follow.
  // NOT on the per-second live poll: `span` is a fresh object every render, so
  // without this guard the effect would fire each tick and yank the bar back to the
  // cursor while the user is panning through history. Guarding on the cursor value
  // (not a one-shot `didInit`) also survives the load race where the frames and the
  // most-recent cursor arrive in separate renders.
  const lastCursorRef = useRef<number | null>(null)
  useEffect(() => {
    const outer = outerRef.current
    if (!outer || !span) return
    if (lastCursorRef.current === cursorTs) return // not a seek → leave the user's pan alone
    lastCursorRef.current = cursorTs
    outer.scrollLeft = Math.max(0, tsToX(cursorTs, span) - outer.clientWidth / 2)
  }, [contentWidth, cursorTs, span])

  return (
    <div className="w-full">
      <div className="mb-1 text-[10px] uppercase tracking-wide text-white/40">
        Activity · click to jump · scroll to pan
      </div>
      <div
        ref={outerRef}
        // A vertical wheel doesn't scroll an overflow-x container, so translate it.
        onWheel={(e) => {
          const el = outerRef.current
          if (el && e.deltaY !== 0) el.scrollLeft += e.deltaY
        }}
        className="no-scrollbar overflow-x-auto"
      >
        <div style={{ width: contentWidth }}>
          <div
            ref={innerRef}
            onClick={(e) => seekFromEvent(e.clientX)}
            className="relative h-12 cursor-pointer rounded bg-white/5"
          >
            {span &&
              segments.map((s) => {
                const left = tsToX(s.start, span)
                const right = tsToX(s.end, span)
                return (
                  <div
                    key={`seg-${s.start}`}
                    className="absolute top-1.5 bottom-1.5 rounded-sm bg-white/25"
                    style={{ left, width: Math.max(2, right - left) }}
                  />
                )
              })}
            {span &&
              ticks.map((t) => (
                <div
                  key={`tick-${t}`}
                  className="absolute top-0 h-full w-px bg-white/15"
                  style={{ left: tsToX(t, span) }}
                />
              ))}
            {span && (
              <div
                className="absolute top-0 h-full w-0.5 bg-[color:var(--accent)]"
                style={{ left: tsToX(cursorTs, span) }}
              />
            )}
          </div>
          {span && (
            <div className="relative h-4 text-[10px] text-white/40">
              {ticks.map((t, i) => {
                // Show the DATE on the first tick of each day (and the very first
                // tick) so panning across midnight is anchored; times elsewhere.
                const newDay = i === 0 || !isSameDay(ticks[i - 1], t)
                return (
                  <span
                    key={`label-${t}`}
                    className={`absolute -translate-x-1/2 whitespace-nowrap ${newDay ? 'font-medium text-white/60' : ''}`}
                    style={{ left: tsToX(t, span) }}
                  >
                    {newDay ? dateLabel(t) : clockLabel(t)}
                  </span>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
