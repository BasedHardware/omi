import { describe, it, expect } from 'vitest'
import {
  computeBarBounds,
  offscreenStageBounds,
  boundsSizeDrifted,
  OFFSCREEN_STAGE_MARGIN,
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

describe('offscreenStageBounds (multi-monitor DPI regression)', () => {
  // Live bug: sizing the bar window at a fixed far corner that sits on a
  // higher-scaleFactor monitor made Windows convert the DIP size using THAT
  // monitor's scale, so the bar revealed ~1.5× oversized (off-center + blurry)
  // on a lower-DPI main monitor. The staging rect must keep the window on the
  // SAME display as the final reveal so its size/paint scale are correct, and it
  // must be fully off-screen (above the top edge) so it never flashes.
  const PARKED = { x: -32000, y: -32000 }
  // A horizontal layout (side-by-side) — nothing above either display, so the
  // staged rect above the target is always in empty space.
  const horizontal = [primary, secondary]

  it('keeps the final size and horizontal center (no cross-DPI resize)', () => {
    const final = computeBarBounds(primary)
    const stage = offscreenStageBounds(final, horizontal, PARKED)
    expect(stage.width).toBe(final.width)
    expect(stage.height).toBe(final.height)
    expect(stage.x).toBe(final.x) // same center → within the target display's column
  })

  it('sits fully above the final top edge (off-screen, never visible)', () => {
    const final = computeBarBounds(primary)
    const stage = offscreenStageBounds(final, horizontal, PARKED)
    expect(stage.y + stage.height).toBeLessThan(final.y)
    expect(final.y - (stage.y + stage.height)).toBe(OFFSCREEN_STAGE_MARGIN)
  })

  it('follows a secondary display origin so staging stays on that display', () => {
    // The staging rect for a reveal on the negative-origin secondary must be
    // above THAT display (its own x-column), not the primary — otherwise it
    // would be sized under the primary's DPI again.
    const final = computeBarBounds(secondary)
    const stage = offscreenStageBounds(final, horizontal, PARKED)
    expect(stage.x).toBeGreaterThanOrEqual(secondary.bounds.x)
    expect(stage.x + stage.width).toBeLessThanOrEqual(secondary.bounds.x + secondary.bounds.width)
    expect(stage.y + stage.height).toBeLessThan(final.y)
  })

  it('falls back to the parked corner when a monitor is stacked ABOVE the target', () => {
    // Vertically-stacked layout: the target (lower) has another display directly
    // above it. Staging above the target would land ON the upper monitor — a
    // visible flash during the paint-ack window AND a cross-DPI resize if the
    // upper monitor's scale differs. Must fall back to the off-desktop corner.
    const lower: DisplayLike = {
      id: 10,
      bounds: { x: 0, y: 0, width: 1920, height: 1080 },
      workArea: { x: 0, y: 0, width: 1920, height: 1032 },
      scaleFactor: 1
    }
    const upper: DisplayLike = {
      id: 11,
      bounds: { x: 0, y: -1080, width: 1920, height: 1080 },
      workArea: { x: 0, y: -1080, width: 1920, height: 1032 },
      scaleFactor: 1.5
    }
    const final = computeBarBounds(lower)
    // Precondition: the naive staged rect really does overlap the upper monitor.
    const naiveStageTop = final.y - final.height - OFFSCREEN_STAGE_MARGIN
    expect(naiveStageTop).toBeLessThan(upper.bounds.y + upper.bounds.height)

    const stage = offscreenStageBounds(final, [lower, upper], PARKED)
    expect(stage.x).toBe(PARKED.x)
    expect(stage.y).toBe(PARKED.y)
    expect(stage.width).toBe(final.width) // size still carried through
    expect(stage.height).toBe(final.height)

    // Control: the SAME target with no monitor above it stages normally (proves
    // the fallback is triggered by the stacked monitor, not the layout in general).
    const stageAlone = offscreenStageBounds(final, [lower], PARKED)
    expect(stageAlone.x).toBe(final.x)
    expect(stageAlone.y).toBe(naiveStageTop)
  })
})

describe('boundsSizeDrifted (fullscreen cross-DPI reveal-size guard)', () => {
  // Live bug: summoning the bar while another app is FULLSCREEN on the target
  // monitor revealed it oversized/off-center/blurry. Mechanism: the final
  // on-screen setBounds moves the window off the 1.5× parked corner onto a 1.0×
  // monitor that (behind a fullscreen-exclusive app) is not treated as a
  // normally-composited destination, so Windows sizes it under the SOURCE (1.5×)
  // scale — 560×640 → 840×960. unparkWindow re-applies setBounds when this
  // predicate flags the drift (the window is by then geometrically on the target,
  // so the re-apply sizes correctly). It must NOT fire on a normal reveal.
  const bar = { x: 680, y: 0, width: 560, height: 640 }

  it('flags the 1.5× inflation (oversized/off-center/blurry reveal)', () => {
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 840, height: 960 })).toBe(true)
  })

  it('does NOT flag an exact reveal (no spurious re-apply)', () => {
    expect(boundsSizeDrifted(bar, { ...bar })).toBe(false)
  })

  it('tolerates ±1px fractional-scale rounding (1.5× monitor reveal)', () => {
    // A correct reveal onto a 1.5× monitor can round to 561×640 — not a drift.
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 561, height: 640 })).toBe(false)
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 559, height: 641 })).toBe(false)
  })

  it('does not flag exactly at the ±2px tolerance boundary (> 2, not >= 2)', () => {
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 562, height: 640 })).toBe(false)
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 558, height: 642 })).toBe(false)
  })

  it('flags a drift beyond the rounding tolerance', () => {
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 563, height: 640 })).toBe(true)
    expect(boundsSizeDrifted(bar, { x: 680, y: 0, width: 560, height: 644 })).toBe(true)
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
