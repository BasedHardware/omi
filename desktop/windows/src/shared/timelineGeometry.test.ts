import { describe, it, expect } from 'vitest'
import {
  tsToX,
  xToTs,
  nearestFrameIndex,
  axisTicks,
  activitySegments,
  frameIndexAtCursor
} from './timelineGeometry'

const H = 3_600_000

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

describe('tsToX / xToTs', () => {
  const span = { minTs: 1000, maxTs: 2000, width: 100 }
  it('maps min->0 and max->width', () => {
    expect(tsToX(1000, span)).toBe(0)
    expect(tsToX(2000, span)).toBe(100)
  })
  it('maps the midpoint', () => {
    expect(tsToX(1500, span)).toBe(50)
    expect(xToTs(50, span)).toBe(1500)
  })
  it('clamps out-of-range input', () => {
    expect(tsToX(5000, span)).toBe(100)
    expect(xToTs(-10, span)).toBe(1000)
  })
  it('handles a zero-width span without dividing by zero', () => {
    expect(tsToX(1000, { minTs: 1000, maxTs: 1000, width: 100 })).toBe(0)
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
