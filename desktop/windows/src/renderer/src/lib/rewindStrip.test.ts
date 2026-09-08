import { describe, it, expect } from 'vitest'
import {
  buildStripItems,
  activeStripIndex,
  stripItemTs,
  gapWidthPx,
  formatGapDuration
} from './rewindStrip'
import type { RewindFrame } from '../../../shared/types'

const f = (ts: number): RewindFrame => ({ ts }) as RewindFrame
const GAP = 60_000

describe('buildStripItems', () => {
  it('returns nothing for no frames', () => {
    expect(buildStripItems([], GAP)).toEqual([])
  })

  it('emits only frame items when there are no gaps', () => {
    const items = buildStripItems([f(0), f(1000), f(2000)], GAP)
    expect(items.map((i) => i.kind)).toEqual(['frame', 'frame', 'frame'])
  })

  it('inserts a gap item between frames further apart than the threshold', () => {
    const items = buildStripItems([f(0), f(1000), f(200_000)], GAP)
    expect(items.map((i) => i.kind)).toEqual(['frame', 'frame', 'gap', 'frame'])
    expect(items[2]).toEqual({ kind: 'gap', from: 1000, to: 200_000 })
  })
})

describe('activeStripIndex', () => {
  const items = buildStripItems([f(0), f(1000), f(200_000), f(201_000)], GAP)

  it('selects the nearest frame when the cursor is on activity', () => {
    expect(activeStripIndex(items, 0)).toBe(0)
    expect(activeStripIndex(items, 200_500)).toBe(3)
  })

  it('selects the gap item when the cursor is in a blank stretch', () => {
    expect(activeStripIndex(items, 100_000)).toBe(2)
  })

  it('returns -1 for no items', () => {
    expect(activeStripIndex([], 0)).toBe(-1)
  })
})

describe('gapWidthPx', () => {
  const PX = 0.00015
  it('scales width with gap duration', () => {
    expect(gapWidthPx(2_000_000, PX, 48, 420)).toBe(300)
  })
  it('clamps very short gaps up to the minimum', () => {
    expect(gapWidthPx(60_000, PX, 48, 420)).toBe(48)
  })
  it('clamps very long gaps down to the maximum', () => {
    expect(gapWidthPx(10_000_000, PX, 48, 420)).toBe(420)
  })
})

describe('formatGapDuration', () => {
  it('shows minutes under an hour', () => {
    expect(formatGapDuration(2 * 60_000)).toBe('2m')
    expect(formatGapDuration(55 * 60_000)).toBe('55m')
  })
  it('shows whole hours', () => {
    expect(formatGapDuration(60 * 60_000)).toBe('1h')
  })
  it('shows hours and minutes', () => {
    expect(formatGapDuration(90 * 60_000)).toBe('1h 30m')
  })
})

describe('stripItemTs', () => {
  it('uses the frame timestamp for frame items', () => {
    expect(stripItemTs({ kind: 'frame', frame: f(1234) })).toBe(1234)
  })
  it('uses the midpoint for gap items', () => {
    expect(stripItemTs({ kind: 'gap', from: 1000, to: 3000 })).toBe(2000)
  })
})
