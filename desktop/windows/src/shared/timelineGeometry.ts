// Frames within this gap form one activity block; the player treats positions
// outside any block (padded) as blank. Shared so the bar and player agree.
export const REWIND_ACTIVITY_GAP_MS = 60_000
export const REWIND_COVER_PAD_MS = 2_000

// Only a genuinely long dead stretch collapses to a break — short gaps stay
// linear and unmarked (better to under-mark than clutter the bar with seams).
// A blank stretch at least this long is not drawn to scale; it collapses to a
// fixed-width axis "break" (a quiet cut seam) so activity keeps almost all the
// horizontal space instead of scrolling past a huge empty gap.
export const REWIND_BREAK_THRESHOLD_MS = 30 * 60_000
// Collapsed pixel width of one break, and the floor width a linear piece gets so
// a lone (zero-duration) frame is still visible/clickable.
export const REWIND_BREAK_PX = 16
export const REWIND_LINEAR_MIN_PX = 3

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v))

/**
 * One tile of the non-linear timeline. `linear` pieces map time↔pixels
 * proportionally to real duration; `break` pieces collapse a long blank stretch
 * to a fixed pixel width. Pieces tile [windowStart, windowEnd] contiguously and
 * their x-ranges are cumulative, so the overall mapping is monotonic.
 */
export type TimelinePiece = {
  kind: 'linear' | 'break'
  tStart: number
  tEnd: number
  xStart: number
  xEnd: number
}

export type TimelineMapping = {
  windowStart: number
  windowEnd: number
  width: number
  pieces: TimelinePiece[]
}

export type TimelineMappingOptions = {
  pxPerHour: number
  minWidth: number
  breakThresholdMs?: number
  breakPx?: number
  linearMinPx?: number
  activityGapMs?: number
}

// Human-friendly tick intervals (ms), smallest → largest.
const TICK_INTERVALS = [
  60_000, // 1m
  5 * 60_000, // 5m
  15 * 60_000, // 15m
  30 * 60_000, // 30m
  3_600_000, // 1h
  3 * 3_600_000, // 3h
  6 * 3_600_000, // 6h
  12 * 3_600_000, // 12h
  24 * 3_600_000 // 1d
]

/**
 * Timestamps for evenly-spaced axis labels across [minTs, maxTs]. Picks the
 * finest "nice" interval that keeps the count within `maxTicks`, and aligns
 * ticks to interval boundaries so labels land on round times (e.g. 3:00, 4:00).
 */
export function axisTicks(minTs: number, maxTs: number, maxTicks: number): number[] {
  const span = maxTs - minTs
  if (span <= 0) return []
  // Tick count across the span is floor(span/iv)+1, so cap span/iv at maxTicks-1
  // to keep the inclusive count within maxTicks.
  const interval =
    TICK_INTERVALS.find((iv) => span / iv <= maxTicks - 1) ?? TICK_INTERVALS[TICK_INTERVALS.length - 1]
  const first = Math.ceil(minTs / interval) * interval
  const ticks: number[] = []
  for (let t = first; t <= maxTs; t += interval) ticks.push(t)
  return ticks
}

/**
 * Group sorted frame timestamps into contiguous activity segments: consecutive
 * frames no more than `gapMs` apart belong to the same segment. Used to draw the
 * timeline as solid activity blocks (filled where screenshots exist) rather than
 * a confusing field of individual hairlines.
 */
export function activitySegments(sortedTs: number[], gapMs: number): { start: number; end: number }[] {
  if (sortedTs.length === 0) return []
  const segments: { start: number; end: number }[] = []
  let start = sortedTs[0]
  let prev = sortedTs[0]
  for (let i = 1; i < sortedTs.length; i++) {
    const t = sortedTs[i]
    if (t - prev > gapMs) {
      segments.push({ start, end: prev })
      start = t
    }
    prev = t
  }
  segments.push({ start, end: prev })
  return segments
}

/**
 * Complement of the activity segments within [windowStart, windowEnd]: the
 * stretches with no recorded activity. An empty timeline yields one full-width
 * gap; touching/adjacent segments leave no gap between them; and sub-threshold
 * gaps that `activitySegments` already merged never appear (they live inside a
 * single segment). Segments are clamped to the window. Used to find the blank
 * stretches that `buildTimelineMapping` collapses into breaks.
 */
export function gapSegments(
  sortedTs: number[],
  gapMs: number,
  windowStart: number,
  windowEnd: number
): { start: number; end: number }[] {
  if (windowEnd <= windowStart) return []
  const gaps: { start: number; end: number }[] = []
  let cursor = windowStart
  for (const seg of activitySegments(sortedTs, gapMs)) {
    const segStart = clamp(seg.start, windowStart, windowEnd)
    const segEnd = clamp(seg.end, windowStart, windowEnd)
    if (segStart > cursor) gaps.push({ start: cursor, end: segStart })
    cursor = Math.max(cursor, segEnd)
  }
  if (cursor < windowEnd) gaps.push({ start: cursor, end: windowEnd })
  return gaps
}

/**
 * Build the non-linear time↔pixel mapping for the activity bar. Long blank
 * stretches (≥ `breakThresholdMs`) collapse to a fixed-width break; everything
 * else lays out proportionally to real duration at `pxPerHour`. The content is
 * never narrower than `minWidth` — any slack is absorbed by the linear
 * (activity) pieces so breaks stay a constant width. The returned pieces are
 * ordered and cumulative, so both `tsToX` and `xToTs` share one monotonic map.
 */
export function buildTimelineMapping(
  sortedTs: number[],
  windowStart: number,
  windowEnd: number,
  opts: TimelineMappingOptions
): TimelineMapping {
  const {
    pxPerHour,
    minWidth,
    breakThresholdMs = REWIND_BREAK_THRESHOLD_MS,
    breakPx = REWIND_BREAK_PX,
    linearMinPx = REWIND_LINEAR_MIN_PX,
    activityGapMs = REWIND_ACTIVITY_GAP_MS
  } = opts

  if (windowEnd <= windowStart) {
    return { windowStart, windowEnd, width: Math.max(0, minWidth), pieces: [] }
  }

  const breaks = gapSegments(sortedTs, activityGapMs, windowStart, windowEnd).filter(
    (g) => g.end - g.start >= breakThresholdMs
  )

  const pieces: TimelinePiece[] = []
  let cursor = windowStart
  for (const b of breaks) {
    if (b.start > cursor) pieces.push({ kind: 'linear', tStart: cursor, tEnd: b.start, xStart: 0, xEnd: 0 })
    pieces.push({ kind: 'break', tStart: b.start, tEnd: b.end, xStart: 0, xEnd: 0 })
    cursor = b.end
  }
  if (cursor < windowEnd) {
    pieces.push({ kind: 'linear', tStart: cursor, tEnd: windowEnd, xStart: 0, xEnd: 0 })
  }

  // Natural (unstretched) width per piece.
  const natural = pieces.map((p) =>
    p.kind === 'break' ? breakPx : Math.max(linearMinPx, ((p.tEnd - p.tStart) / 3_600_000) * pxPerHour)
  )
  const total = natural.reduce((a, b) => a + b, 0)
  const width = Math.max(total, minWidth)
  const extra = width - total

  // Absorb stretch-to-viewport into the linear (activity) pieces so breaks keep
  // their fixed width. If there are no linear pieces (the window is one big
  // break), stretch the breaks so the bar still fills the viewport.
  const linearIdx = pieces.map((p, i) => (p.kind === 'linear' ? i : -1)).filter((i) => i >= 0)
  const stretchIdx = linearIdx.length > 0 ? linearIdx : pieces.map((_, i) => i)
  const stretchBase = stretchIdx.reduce((a, i) => a + natural[i], 0)
  const stretchSet = new Set(stretchIdx)

  let x = 0
  pieces.forEach((p, i) => {
    let w = natural[i]
    if (extra > 0 && stretchSet.has(i)) {
      w += stretchBase > 0 ? extra * (natural[i] / stretchBase) : extra / stretchIdx.length
    }
    p.xStart = x
    // Pin the final edge exactly to `width` so floating-point drift never leaves
    // a sliver of unmapped track at the right edge.
    p.xEnd = i === pieces.length - 1 ? width : x + w
    x = p.xEnd
  })

  return { windowStart, windowEnd, width, pieces }
}

/** Pixel x for a timestamp under the non-linear mapping. Monotonic; clamps out-of-range input. */
export function tsToX(ts: number, m: TimelineMapping): number {
  if (m.pieces.length === 0) return 0
  const t = clamp(ts, m.windowStart, m.windowEnd)
  const p = m.pieces.find((pc) => t <= pc.tEnd) ?? m.pieces[m.pieces.length - 1]
  if (p.tEnd === p.tStart) return p.xStart
  const px = p.xStart + ((t - p.tStart) / (p.tEnd - p.tStart)) * (p.xEnd - p.xStart)
  return clamp(px, 0, m.width)
}

/**
 * Timestamp for a pixel x under the non-linear mapping. Inside a linear piece
 * this inverts `tsToX`; inside a break (a dead zone with no frames) it snaps to
 * the nearest activity edge, so scrubbing a collapsed gap jumps cleanly to the
 * block on that side rather than landing in blank time.
 */
export function xToTs(x: number, m: TimelineMapping): number {
  if (m.pieces.length === 0) return m.windowStart
  const px = clamp(x, 0, m.width)
  const p = m.pieces.find((pc) => px <= pc.xEnd) ?? m.pieces[m.pieces.length - 1]
  if (p.kind === 'break') {
    return px - p.xStart <= (p.xEnd - p.xStart) / 2 ? p.tStart : p.tEnd
  }
  if (p.xEnd === p.xStart) return p.tStart
  return Math.round(p.tStart + ((px - p.xStart) / (p.xEnd - p.xStart)) * (p.tEnd - p.tStart))
}

/** True when `ts` falls strictly inside a collapsed break (used to drop axis ticks that land in a cut). */
export function tsInBreak(ts: number, m: TimelineMapping): boolean {
  return m.pieces.some((p) => p.kind === 'break' && ts > p.tStart && ts < p.tEnd)
}

/**
 * Index of the frame to show for a cursor position, or -1 when the cursor sits
 * in a blank gap (no screenshots). A frame is shown only when the cursor falls
 * within an activity segment (padded by `padMs` so block edges and lone frames
 * stay clickable) — so clicking empty space on the timeline shows nothing,
 * matching what the activity bar draws. Operates purely in the time domain, so
 * it is independent of the pixel mapping above.
 */
export function frameIndexAtCursor(sortedTs: number[], cursorTs: number, gapMs: number, padMs: number): number {
  if (sortedTs.length === 0) return -1
  const covered = activitySegments(sortedTs, gapMs).some(
    (s) => cursorTs >= s.start - padMs && cursorTs <= s.end + padMs
  )
  return covered ? nearestFrameIndex(sortedTs, cursorTs) : -1
}

/** Index of the frame whose ts is closest to `ts`; -1 for empty input. */
export function nearestFrameIndex(sortedTs: number[], ts: number): number {
  if (sortedTs.length === 0) return -1
  let best = 0
  let bestDist = Math.abs(sortedTs[0] - ts)
  for (let i = 1; i < sortedTs.length; i++) {
    const d = Math.abs(sortedTs[i] - ts)
    if (d < bestDist) {
      best = i
      bestDist = d
    }
  }
  return best
}
