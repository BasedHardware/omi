import { describe, it, expect } from 'vitest'
import {
  computeBarBounds,
  displayForPoint,
  isCursorInPeekFootprint,
  isCursorOverPill,
  BAR_WINDOW_WIDTH,
  PILL_HIT_WIDTH,
  type DisplayLike
} from './placement'

const primary: DisplayLike = {
  id: 1,
  bounds: { x: 0, y: 0, width: 2560, height: 1440 },
  workArea: { x: 0, y: 0, width: 2560, height: 1392 },
  scaleFactor: 1
}
const secondary: DisplayLike = {
  id: 2,
  bounds: { x: 2560, y: -200, width: 1920, height: 1080 },
  workArea: { x: 2560, y: -200, width: 1920, height: 1032 },
  scaleFactor: 1.5
}

describe('isCursorInPeekFootprint (retract watchdog — merge-blocker regression)', () => {
  it('screen corners with the bar open must NOT count as hovering (retract fires)', () => {
    // Live bug: hovering top-left/right corners kept the bar open forever.
    expect(isCursorInPeekFootprint({ x: 0, y: 0 }, primary)).toBe(false) // top-left
    expect(isCursorInPeekFootprint({ x: 2559, y: 0 }, primary)).toBe(false) // top-right
    expect(isCursorInPeekFootprint({ x: 2560, y: -200 }, secondary)).toBe(false)
    expect(isCursorInPeekFootprint({ x: 4479, y: -200 }, secondary)).toBe(false)
  })

  it('the bar footprint itself keeps it open', () => {
    // Top-center of the primary display, within the footprint height.
    expect(isCursorInPeekFootprint({ x: 1280, y: 0 }, primary)).toBe(true)
    expect(isCursorInPeekFootprint({ x: 1280, y: 40 }, primary)).toBe(true)
    // …but below it, it retracts.
    expect(isCursorInPeekFootprint({ x: 1280, y: 200 }, primary)).toBe(false)
    // Just outside the footprint width, it retracts.
    expect(isCursorInPeekFootprint({ x: 1280 - 300, y: 0 }, primary)).toBe(false)
    // Centered footprint on the negative-origin secondary display.
    expect(isCursorInPeekFootprint({ x: 2560 + 960, y: -190 }, secondary)).toBe(true)
  })
})

describe('isCursorOverPill (click-through safety net — BUG 4 regression)', () => {
  it('only the 160×44 top-center pill rect captures clicks — dead space is click-through', () => {
    // Dead-center over the pill: interactive (the pill is clickable to expand).
    expect(isCursorOverPill({ x: 1280, y: 0 }, primary)).toBe(true)
    expect(isCursorOverPill({ x: 1280, y: 40 }, primary)).toBe(true)
    // Just below the pill (a control at ~y=60 under the top-center band, e.g. a
    // browser new-tab "+"): NOT over the pill → window stays click-through.
    expect(isCursorOverPill({ x: 1280, y: 60 }, primary)).toBe(false)
    // Off to the side but still inside the (larger) keep-open footprint: the bar
    // stays revealed, yet this dead space must pass clicks through.
    expect(isCursorInPeekFootprint({ x: 1280 + 120, y: 10 }, primary)).toBe(true)
    expect(isCursorOverPill({ x: 1280 + 120, y: 10 }, primary)).toBe(false)
  })

  it('is narrower than the keep-open footprint (clicks pass around the pill)', () => {
    expect(PILL_HIT_WIDTH).toBeLessThan(320) // < PEEK_FOOTPRINT_WIDTH
    const edge = 1280 + PILL_HIT_WIDTH / 2 + 1 // just outside the pill hit-rect
    expect(isCursorOverPill({ x: edge, y: 0 }, primary)).toBe(false)
  })

  it('centers on a negative-origin secondary display', () => {
    expect(isCursorOverPill({ x: 2560 + 960, y: -200 }, secondary)).toBe(true)
    expect(isCursorOverPill({ x: 2560 + 960, y: -140 }, secondary)).toBe(false) // below pill
  })
})

describe('computeBarBounds', () => {
  it('centers a fixed-width window at the physical top edge', () => {
    const b = computeBarBounds(primary)
    expect(b.width).toBe(BAR_WINDOW_WIDTH)
    expect(b.x).toBe(Math.round((2560 - BAR_WINDOW_WIDTH) / 2))
    expect(b.y).toBe(0) // bounds top, not workArea top
  })

  it('follows the display origin on a secondary monitor', () => {
    const b = computeBarBounds(secondary)
    expect(b.y).toBe(-200)
    expect(b.x).toBeGreaterThanOrEqual(2560)
    expect(b.x + b.width).toBeLessThanOrEqual(2560 + 1920)
  })

  it('clamps height to the work-area fraction and width to the display', () => {
    const tiny: DisplayLike = {
      id: 3,
      bounds: { x: 0, y: 0, width: 500, height: 400 },
      workArea: { x: 0, y: 0, width: 500, height: 360 },
      scaleFactor: 1
    }
    const b = computeBarBounds(tiny)
    expect(b.width).toBe(500)
    expect(b.height).toBe(Math.round(360 * 0.7))
  })
})

describe('displayForPoint', () => {
  it('picks the containing display, else the nearest', () => {
    expect(displayForPoint([primary, secondary], { x: 100, y: 100 }).id).toBe(1)
    expect(displayForPoint([primary, secondary], { x: 3000, y: 10 }).id).toBe(2)
    // Point outside every display → nearest center.
    expect(displayForPoint([primary, secondary], { x: 9000, y: 0 }).id).toBe(2)
  })
})
