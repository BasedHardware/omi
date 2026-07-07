export type TimeSpan = { minTs: number; maxTs: number; width: number }

// Frames within this gap form one activity block; the player treats positions
// outside any block (padded) as blank. Shared so the bar and player agree.
export const REWIND_ACTIVITY_GAP_MS = 60_000
export const REWIND_COVER_PAD_MS = 2_000

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v))

export function tsToX(ts: number, span: TimeSpan): number {
  const range = span.maxTs - span.minTs
  if (range <= 0) return 0
  return clamp(((ts - span.minTs) / range) * span.width, 0, span.width)
}

export function xToTs(x: number, span: TimeSpan): number {
  const range = span.maxTs - span.minTs
  if (span.width <= 0) return span.minTs
  return Math.round(span.minTs + clamp(x, 0, span.width) / span.width * range)
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
    TICK_INTERVALS.find((iv) => span / iv <= maxTicks - 1) ??
    TICK_INTERVALS[TICK_INTERVALS.length - 1]
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
export function activitySegments(
  sortedTs: number[],
  gapMs: number
): { start: number; end: number }[] {
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
 * Index of the frame to show for a cursor position, or -1 when the cursor sits
 * in a blank gap (no screenshots). A frame is shown only when the cursor falls
 * within an activity segment (padded by `padMs` so block edges and lone frames
 * stay clickable) — so clicking empty space on the timeline shows nothing,
 * matching what the activity bar draws.
 */
export function frameIndexAtCursor(
  sortedTs: number[],
  cursorTs: number,
  gapMs: number,
  padMs: number
): number {
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
