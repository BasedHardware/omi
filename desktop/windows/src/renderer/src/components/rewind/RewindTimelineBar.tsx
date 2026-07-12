import { useEffect, useRef } from 'react'
import type { RewindFrame } from '../../../../shared/types'
import {
  buildTimelineMapping,
  tsToX,
  xToTs,
  tsInBreak,
  axisTicks,
  activitySegments,
  REWIND_ACTIVITY_GAP_MS,
  type TimelineMapping
} from '../../../../shared/timelineGeometry'
import { useElementWidth } from '../../hooks/useElementWidth'
import { isSameDay } from '../../../../shared/relativeTime'

const clockLabel = (ts: number): string =>
  new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
const dateLabel = (ts: number): string =>
  new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' })

// Fixed horizontal time scale for the ACTIVITY portions, so the bar is a broad
// scrollable timeline you can pan across — not a squished fit-to-width overview.
// Long blank gaps don't scroll past at this scale; they collapse to a break (see
// buildTimelineMapping), so activity keeps almost all the horizontal space.
const PX_PER_HOUR = 140
const TRACK_HEIGHT_PX = 48 // matches the track's `h-12`

// A quiet vertical zigzag "cut" seam spanning the track height — a chart axis
// break / video-editor splice mark. Kept thin and low-contrast so it reads as a
// seam you notice only when you look, not a bold symbol shouting for attention.
function breakZigzagPoints(width: number, height: number): string {
  const cx = width / 2
  const amp = Math.min(3, width * 0.22)
  // 5 rows → 4 diagonals → 3 gentle switchbacks, top to bottom.
  const rows = [0, height / 4, height / 2, (height * 3) / 4, height]
  return rows.map((y, i) => `${(i % 2 === 0 ? cx - amp : cx + amp).toFixed(1)},${y.toFixed(1)}`).join(' ')
}

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

  const frameTimes = frames.map((f) => f.ts)
  // Non-linear layout: activity to scale, long blank gaps collapsed to breaks.
  const mapping: TimelineMapping | null = hasSpan
    ? buildTimelineMapping(frameTimes, minTs, maxTs, { pxPerHour: PX_PER_HOUR, minWidth: viewWidth })
    : null
  const contentWidth = mapping ? mapping.width : viewWidth

  const seekFromEvent = (clientX: number): void => {
    if (!innerRef.current || !mapping) return
    const rect = innerRef.current.getBoundingClientRect()
    onSeek(xToTs(clientX - rect.left, mapping))
  }

  const ticks = mapping ? localAxisTicks(minTs, maxTs, Math.max(4, Math.round(contentWidth / 110))) : []
  // Ticks that land inside a collapsed break would pile up in ~16px — drop them;
  // the break mark stands in for that stretch of time.
  const visibleTicks = mapping ? ticks.filter((t) => !tsInBreak(t, mapping)) : []
  const segments = mapping ? activitySegments(frameTimes, REWIND_ACTIVITY_GAP_MS) : []
  const breaks = mapping ? mapping.pieces.filter((p) => p.kind === 'break') : []

  // Center the cursor whenever it actually CHANGES — the initial open position
  // (the newest frame, so the bar lands on the recent edge), a seek, or live-follow.
  // NOT on the per-second live poll: `mapping` is a fresh object every render, so
  // without this guard the effect would fire each tick and yank the bar back to the
  // cursor while the user is panning through history. Guarding on the cursor value
  // (not a one-shot `didInit`) also survives the load race where the frames and the
  // most-recent cursor arrive in separate renders.
  const lastCursorRef = useRef<number | null>(null)
  useEffect(() => {
    const outer = outerRef.current
    if (!outer || !mapping) return
    if (lastCursorRef.current === cursorTs) return // not a seek → leave the user's pan alone
    lastCursorRef.current = cursorTs
    outer.scrollLeft = Math.max(0, tsToX(cursorTs, mapping) - outer.clientWidth / 2)
  }, [contentWidth, cursorTs, mapping])

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
            {mapping &&
              breaks.map((b) => {
                const left = b.xStart
                const width = b.xEnd - b.xStart
                return (
                  // A thin, low-opacity zigzag seam — no fill/notch, so the track
                  // reads as continuous and the collapse is a quiet "cut", not a
                  // sore thumb. pointer-events-none keeps the surface scrubbable.
                  <svg
                    key={`break-${b.tStart}`}
                    data-testid="rewind-break"
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-0 text-white/20"
                    style={{ left, width }}
                    width={width}
                    height={TRACK_HEIGHT_PX}
                    viewBox={`0 0 ${width} ${TRACK_HEIGHT_PX}`}
                  >
                    <polyline
                      points={breakZigzagPoints(width, TRACK_HEIGHT_PX)}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={1.25}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  </svg>
                )
              })}
            {mapping &&
              segments.map((s) => {
                const left = tsToX(s.start, mapping)
                const right = tsToX(s.end, mapping)
                return (
                  <div
                    key={`seg-${s.start}`}
                    className="absolute top-1.5 bottom-1.5 rounded-sm bg-white/25"
                    style={{ left, width: Math.max(2, right - left) }}
                  />
                )
              })}
            {mapping &&
              visibleTicks.map((t) => (
                <div
                  key={`tick-${t}`}
                  className="absolute top-0 h-full w-px bg-white/15"
                  style={{ left: tsToX(t, mapping) }}
                />
              ))}
            {mapping && (
              <div
                className="absolute top-0 h-full w-0.5 bg-[color:var(--accent)]"
                style={{ left: tsToX(cursorTs, mapping) }}
              />
            )}
          </div>
          {mapping && (
            <div className="tnum relative h-4 text-[10px] text-white/40">
              {visibleTicks.map((t, i) => {
                // Show the DATE on the first tick of each day (and the very first
                // tick) so panning across midnight is anchored; times elsewhere.
                const newDay = i === 0 || !isSameDay(visibleTicks[i - 1], t)
                return (
                  <span
                    key={`label-${t}`}
                    className={`absolute -translate-x-1/2 whitespace-nowrap ${newDay ? 'font-medium text-white/60' : ''}`}
                    style={{ left: tsToX(t, mapping) }}
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
