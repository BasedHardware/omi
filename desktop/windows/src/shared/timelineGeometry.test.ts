import { describe, it, expect } from 'vitest'
import {
  buildTimelineMapping,
  tsToX,
  xToTs,
  tsInBreak,
  nearestFrameIndex,
  axisTicks,
  activitySegments,
  gapSegments,
  frameIndexAtCursor,
  REWIND_BREAK_THRESHOLD_MS
} from './timelineGeometry'

const H = 3_600_000

// pxPerHour 3600 → 1px per real second; minWidth 0 → no viewport stretch, so
// piece widths equal their natural (unstretched) sizes and are easy to assert.
// breakThresholdMs is pinned (not the shipped default) so the mapping-math
// scenarios below stay deterministic regardless of the tuning knob; a separate
// describe covers the real default threshold.
const OPTS = { pxPerHour: 3600, minWidth: 0, breakThresholdMs: 300_000 }
const MIN = 60_000 // 60s activity blocks in the scenarios below

describe('axisTicks', () => {
  it('picks a "nice" interval keeping the tick count within the budget', () => {
    const ticks = axisTicks(0, 6 * H, 8)
    expect(ticks).toEqual([0, H, 2 * H, 3 * H, 4 * H, 5 * H, 6 * H])
  })

  it('aligns ticks to interval boundaries (not the raw min)', () => {
    const ticks = axisTicks(1000, 6 * H + 1000, 8)
    expect(ticks).toEqual([H, 2 * H, 3 * H, 4 * H, 5 * H, 6 * H])
  })

  it('uses a coarser interval for a long span to stay within budget', () => {
    const ticks = axisTicks(0, 48 * H, 8)
    expect(ticks.every((t) => t % (12 * H) === 0)).toBe(true)
    expect(ticks.length).toBeLessThanOrEqual(8)
  })

  it('returns nothing for a non-positive span', () => {
    expect(axisTicks(500, 500, 8)).toEqual([])
    expect(axisTicks(900, 500, 8)).toEqual([])
  })
})

describe('buildTimelineMapping', () => {
  // Two 60s activity blocks (0–60s and 600–660s) with a 540s blank gap between.
  // The gap (540s ≥ 5min break threshold) collapses; each block lays out to
  // scale (60px at 1px/s).
  const twoBlocks = [0, MIN, 600_000, 660_000]

  it('collapses a ≥threshold gap to a fixed-width break and lays activity to scale', () => {
    const m = buildTimelineMapping(twoBlocks, 0, 660_000, OPTS)
    expect(m.pieces.map((p) => p.kind)).toEqual(['linear', 'break', 'linear'])
    const [a, gap, b] = m.pieces
    expect(a.xEnd - a.xStart).toBe(60) // 60s activity → 60px
    expect(gap.xEnd - gap.xStart).toBe(16) // 540s gap → fixed 16px break
    expect(b.xEnd - b.xStart).toBe(60)
    expect(m.width).toBe(136)
  })

  it('leaves a sub-threshold gap linear (uncompressed) — no break piece', () => {
    // 120s gap (< 5min) between two blocks stays real-duration: one linear run.
    const m = buildTimelineMapping([0, MIN, 180_000, 240_000], 0, 240_000, OPTS)
    expect(m.pieces.every((p) => p.kind === 'linear')).toBe(true)
    expect(m.pieces).toHaveLength(1)
    expect(m.width).toBe(240) // full 240s to scale, gap NOT collapsed
  })

  it('handles a window that is one giant gap (zero frames)', () => {
    const m = buildTimelineMapping([], 0, 1_000_000, OPTS)
    expect(m.pieces.map((p) => p.kind)).toEqual(['break'])
    expect(m.width).toBe(16)
    expect(tsToX(0, m)).toBe(0)
    expect(tsToX(1_000_000, m)).toBe(16)
  })

  it('puts a break at the window start when activity is only late', () => {
    const m = buildTimelineMapping([600_000, 660_000], 0, 660_000, OPTS)
    expect(m.pieces[0].kind).toBe('break')
    expect(m.pieces[0].tStart).toBe(0)
    expect(m.pieces.at(-1)?.kind).toBe('linear')
  })

  it('puts a break at the window end when activity is only early', () => {
    const m = buildTimelineMapping([0, MIN], 0, 660_000, OPTS)
    expect(m.pieces.map((p) => p.kind)).toEqual(['linear', 'break'])
    expect(m.pieces.at(-1)?.tEnd).toBe(660_000)
  })

  it('emits one break per collapsed gap for multiple consecutive breaks', () => {
    const m = buildTimelineMapping([0, MIN, 600_000, 660_000, 1_200_000, 1_260_000], 0, 1_260_000, OPTS)
    expect(m.pieces.map((p) => p.kind)).toEqual(['linear', 'break', 'linear', 'break', 'linear'])
  })

  it('stretches to minWidth by widening activity, never the breaks', () => {
    const m = buildTimelineMapping(twoBlocks, 0, 660_000, { ...OPTS, minWidth: 400 })
    expect(m.width).toBe(400)
    const gap = m.pieces.find((p) => p.kind === 'break')!
    expect(gap.xEnd - gap.xStart).toBe(16) // break stays fixed
    // The two activity pieces absorb all 264px of extra width equally.
    const acts = m.pieces.filter((p) => p.kind === 'linear')
    expect(acts[0].xEnd - acts[0].xStart).toBeCloseTo(192, 5)
    expect(acts[1].xEnd - acts[1].xStart).toBeCloseTo(192, 5)
  })

  it('fills the viewport even when the whole window is one break (no activity to widen)', () => {
    const m = buildTimelineMapping([], 0, 1_000_000, { ...OPTS, minWidth: 300 })
    expect(m.width).toBe(300)
    expect(m.pieces[0].xStart).toBe(0)
    expect(m.pieces[0].xEnd).toBe(300)
  })

  it('returns an empty mapping for a non-positive window', () => {
    const m = buildTimelineMapping([0, MIN], 500, 500, OPTS)
    expect(m.pieces).toEqual([])
    expect(tsToX(500, m)).toBe(0)
    expect(xToTs(10, m)).toBe(500)
  })
})

describe('buildTimelineMapping default break threshold', () => {
  // No breakThresholdMs override → the shipped default applies. Only genuinely
  // long dead stretches should collapse, so the bar isn't littered with seams.
  const DEFAULTS = { pxPerHour: 3600, minWidth: 0 }
  const hasBreak = (m: ReturnType<typeof buildTimelineMapping>): boolean =>
    m.pieces.some((p) => p.kind === 'break')

  it('defaults to at least 30 minutes', () => {
    expect(REWIND_BREAK_THRESHOLD_MS).toBeGreaterThanOrEqual(30 * 60_000)
  })

  it('does NOT collapse a 20-minute gap (stays linear, unmarked)', () => {
    const m = buildTimelineMapping([0, MIN, 20 * 60_000, 20 * 60_000 + MIN], 0, 20 * 60_000 + MIN, DEFAULTS)
    expect(hasBreak(m)).toBe(false)
  })

  it('DOES collapse a 45-minute gap', () => {
    const m = buildTimelineMapping([0, MIN, 45 * 60_000, 45 * 60_000 + MIN], 0, 45 * 60_000 + MIN, DEFAULTS)
    expect(hasBreak(m)).toBe(true)
  })
})

describe('tsToX / xToTs (non-linear mapping)', () => {
  const twoBlocks = [0, MIN, 600_000, 660_000]
  const m = buildTimelineMapping(twoBlocks, 0, 660_000, OPTS) // width 136, break 60–76px

  it('maps windowStart→0 and windowEnd→width', () => {
    expect(tsToX(0, m)).toBe(0)
    expect(tsToX(660_000, m)).toBe(136)
  })

  it('places activity to scale and collapses the gap between the blocks', () => {
    expect(tsToX(MIN, m)).toBe(60) // end of block A
    expect(tsToX(600_000, m)).toBe(76) // start of block B — only 16px past A
  })

  it('is monotonic non-decreasing across the whole domain (including the break)', () => {
    const samples = [0, 30_000, MIN, 200_000, 400_000, 600_000, 630_000, 660_000]
    const xs = samples.map((t) => tsToX(t, m))
    for (let i = 1; i < xs.length; i++) expect(xs[i]).toBeGreaterThanOrEqual(xs[i - 1])
  })

  it('round-trips a click inside an activity block', () => {
    expect(xToTs(30, m)).toBe(30_000) // 30px into block A → 30s
  })

  it('snaps a click inside a break to the nearest activity edge', () => {
    // Break spans x 60–76 (center 68). Left half → block A end; right half → block B start.
    expect(xToTs(63, m)).toBe(MIN) // near A edge
    expect(xToTs(74, m)).toBe(600_000) // near B edge
  })

  it('clamps out-of-range input to the ends', () => {
    expect(tsToX(-5000, m)).toBe(0)
    expect(tsToX(9_999_999, m)).toBe(136)
    expect(xToTs(-10, m)).toBe(0)
    expect(xToTs(9999, m)).toBe(660_000)
  })
})

describe('tsInBreak', () => {
  const m = buildTimelineMapping([0, MIN, 600_000, 660_000], 0, 660_000, OPTS)

  it('is true strictly inside a collapsed break', () => {
    expect(tsInBreak(300_000, m)).toBe(true)
  })

  it('is false at the break edges (they are activity boundaries)', () => {
    expect(tsInBreak(MIN, m)).toBe(false)
    expect(tsInBreak(600_000, m)).toBe(false)
  })

  it('is false inside an activity block', () => {
    expect(tsInBreak(30_000, m)).toBe(false)
  })
})

describe('activitySegments', () => {
  it('returns nothing for no frames', () => {
    expect(activitySegments([], 60_000)).toEqual([])
  })

  it('wraps a single frame as a zero-length segment', () => {
    expect(activitySegments([1000], 60_000)).toEqual([{ start: 1000, end: 1000 }])
  })

  it('merges frames within the gap into one segment', () => {
    expect(activitySegments([0, 30_000, 60_000], 60_000)).toEqual([{ start: 0, end: 60_000 }])
  })

  it('splits when the gap between frames exceeds the threshold', () => {
    expect(activitySegments([0, 1000, 200_000, 201_000], 60_000)).toEqual([
      { start: 0, end: 1000 },
      { start: 200_000, end: 201_000 }
    ])
  })

  it('keeps frames exactly at the gap threshold together', () => {
    expect(activitySegments([0, 60_000], 60_000)).toEqual([{ start: 0, end: 60_000 }])
  })
})

describe('gapSegments', () => {
  const GAP = 60_000

  it('yields one full-width gap for an empty timeline', () => {
    expect(gapSegments([], GAP, 0, 100_000)).toEqual([{ start: 0, end: 100_000 }])
  })

  it('returns the blank stretch between two activity blocks', () => {
    // Blocks 0–1000 and 200000–201000; the gap is the span between them.
    expect(gapSegments([0, 1000, 200_000, 201_000], GAP, 0, 201_000)).toEqual([
      { start: 1000, end: 200_000 }
    ])
  })

  it('includes leading and trailing gaps when the window overhangs the frames', () => {
    expect(gapSegments([1000, 2000], GAP, 0, 5000)).toEqual([
      { start: 0, end: 1000 },
      { start: 2000, end: 5000 }
    ])
  })

  it('leaves no gap where frames sit exactly one threshold apart (merged, not split)', () => {
    // Each hop is exactly the gap threshold, so activitySegments keeps them in
    // one block 0–120000 — the window is fully covered, no blank.
    expect(gapSegments([0, 60_000, 120_000], GAP, 0, 120_000)).toEqual([])
  })

  it('does not emit sub-threshold gaps that live inside one merged segment', () => {
    // 30s apart (< 60s) → one segment 0–90000, so the whole window is covered.
    expect(gapSegments([0, 30_000, 60_000, 90_000], GAP, 0, 90_000)).toEqual([])
  })

  it('is the exact complement of the activity blocks across the window', () => {
    expect(gapSegments([0, 1000, 200_000], GAP, 0, 200_000)).toEqual([
      { start: 1000, end: 200_000 }
    ])
  })

  it('returns nothing for a non-positive window', () => {
    expect(gapSegments([1000], GAP, 500, 500)).toEqual([])
    expect(gapSegments([1000], GAP, 900, 500)).toEqual([])
  })
})

describe('frameIndexAtCursor', () => {
  // Two activity blocks (0–2000 and 100000–101000) with a wide blank gap between.
  const ts = [0, 1000, 2000, 100_000, 101_000]
  const GAP = 60_000
  const PAD = 2_000

  it('returns the nearest frame when the cursor is inside a block', () => {
    expect(frameIndexAtCursor(ts, 1000, GAP, PAD)).toBe(1)
    expect(frameIndexAtCursor(ts, 100_400, GAP, PAD)).toBe(3)
  })

  it('returns -1 when the cursor is in a blank gap between blocks', () => {
    expect(frameIndexAtCursor(ts, 50_000, GAP, PAD)).toBe(-1)
  })

  it('tolerates clicks within the pad of a block edge', () => {
    expect(frameIndexAtCursor(ts, 3000, GAP, PAD)).toBe(2) // 1s past the block end
  })

  it('returns -1 just beyond the pad', () => {
    expect(frameIndexAtCursor(ts, 5000, GAP, PAD)).toBe(-1)
  })

  it('returns -1 for no frames', () => {
    expect(frameIndexAtCursor([], 1000, GAP, PAD)).toBe(-1)
  })
})

describe('nearestFrameIndex', () => {
  it('finds the frame closest in time', () => {
    expect(nearestFrameIndex([0, 100, 200], 130)).toBe(1)
    expect(nearestFrameIndex([0, 100, 200], 160)).toBe(2)
    expect(nearestFrameIndex([], 50)).toBe(-1)
  })
})
