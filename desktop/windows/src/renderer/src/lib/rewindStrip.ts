import type { RewindFrame } from '../../../shared/types'

/** A filmstrip entry: either a captured frame or a blank gap between blocks. */
export type StripItem =
  | { kind: 'frame'; frame: RewindFrame }
  | { kind: 'gap'; from: number; to: number }

/**
 * Lay sorted frames out as a filmstrip: frames close in time pack together, and
 * runs more than `gapMs` apart get a blank gap item, so empty time shows as
 * proportional blank space instead of forcing every frame to its exact time
 * position (which left ugly slivers between near-simultaneous shots).
 */
export function buildStripItems(frames: RewindFrame[], gapMs: number): StripItem[] {
  const items: StripItem[] = []
  for (let i = 0; i < frames.length; i++) {
    if (i > 0 && frames[i].ts - frames[i - 1].ts > gapMs) {
      items.push({ kind: 'gap', from: frames[i - 1].ts, to: frames[i].ts })
    }
    items.push({ kind: 'frame', frame: frames[i] })
  }
  return items
}

/** Representative timestamp for a strip item (a gap reports its midpoint). */
export function stripItemTs(item: StripItem): number {
  return item.kind === 'frame' ? item.frame.ts : Math.round((item.from + item.to) / 2)
}

/** Pixel width for a gap spacer, proportional to its duration but clamped. */
export function gapWidthPx(
  durationMs: number,
  pxPerMs: number,
  minPx: number,
  maxPx: number
): number {
  return Math.min(maxPx, Math.max(minPx, Math.round(durationMs * pxPerMs)))
}

/** Compact human duration for a gap label, e.g. "2m", "1h", "1h 30m". */
export function formatGapDuration(ms: number): string {
  const totalMin = Math.round(ms / 60_000)
  if (totalMin < 60) return `${totalMin}m`
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return m ? `${h}h ${m}m` : `${h}h`
}

/**
 * Index of the strip item the cursor is on: the gap item when the cursor sits in
 * a blank stretch, otherwise the nearest frame. Drives which item the strip
 * scrolls to / highlights, kept in sync with the bar's cursor.
 */
export function activeStripIndex(items: StripItem[], cursorTs: number): number {
  let best = -1
  let bestDist = Infinity
  for (let i = 0; i < items.length; i++) {
    const it = items[i]
    // A gap only "wins" when the cursor is strictly inside the blank stretch;
    // at its edges (which are real frames) the bounding frame should win.
    const d =
      it.kind === 'frame'
        ? Math.abs(it.frame.ts - cursorTs)
        : cursorTs > it.from && cursorTs < it.to
          ? 0
          : Infinity
    if (d < bestDist) {
      bestDist = d
      best = i
    }
  }
  return best
}
