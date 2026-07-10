import { describe, it, expect } from 'vitest'
import {
  computeStripBounds,
  computeBarBounds,
  displayForPoint,
  isCursorInPeekFootprint,
  shouldSuppressStrips,
  BAR_WINDOW_WIDTH,
  STRIP_WIDTH,
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

describe('computeStripBounds', () => {
  it('is a 1px-tall CENTERED footprint — never the display width (merge-blocker regression)', () => {
    // Full-width strips hijacked the top edge: aiming at a maximized window's
    // ✕/minimize or browser tab-close buttons summoned the bar.
    const s = computeStripBounds(primary)
    expect(s.height).toBe(1)
    expect(s.width).toBe(STRIP_WIDTH)
    expect(s.x).toBe(Math.round((2560 - STRIP_WIDTH) / 2))
    // Corners are far outside the strip on every representative display.
    for (const d of [
      primary,
      secondary,
      { ...primary, bounds: { x: 0, y: 0, width: 1366, height: 768 } },
      { ...primary, bounds: { x: 0, y: 0, width: 3440, height: 1440 } }
    ]) {
      const strip = computeStripBounds(d)
      const b = d.bounds
      expect(strip.x).toBeGreaterThan(b.x + b.width * 0.25) // top-left corner excluded
      expect(strip.x + strip.width).toBeLessThan(b.x + b.width * 0.75) // top-right excluded
      expect(strip.y).toBe(b.y)
    }
  })

  it('keeps its own origin on a negative-origin secondary display', () => {
    const s = computeStripBounds(secondary)
    expect(s.y).toBe(-200)
    expect(s.x).toBe(Math.round(2560 + (1920 - STRIP_WIDTH) / 2))
  })
})

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

describe('shouldSuppressStrips', () => {
  const self = 'C:\\apps\\omi\\omi.exe'

  it('suppresses when the foreground rect covers the display (physical px)', () => {
    expect(
      shouldSuppressStrips(
        {
          rect: { x: 0, y: 0, width: 2560, height: 1440 },
          className: 'UnityWndClass',
          exePath: 'C:\\g\\game.exe'
        },
        primary,
        self
      )
    ).toBe(true)
  })

  it('accounts for scaleFactor on high-DPI displays', () => {
    // 1.5x display: 1920x1080 DIP = 2880x1620 physical.
    const rect = { x: 2560 * 1.5, y: -200 * 1.5, width: 2880, height: 1620 }
    expect(
      shouldSuppressStrips({ rect, className: 'X', exePath: 'C:\\g\\game.exe' }, secondary, self)
    ).toBe(true)
    // A merely maximized window (short of the taskbar) does not suppress.
    const maxed = { ...rect, height: 1550 }
    expect(
      shouldSuppressStrips(
        { rect: maxed, className: 'X', exePath: 'C:\\g\\game.exe' },
        secondary,
        self
      )
    ).toBe(false)
  })

  it('never suppresses for shell surfaces, our own exe, or no rect', () => {
    const full = { x: 0, y: 0, width: 2560, height: 1440 }
    expect(
      shouldSuppressStrips(
        { rect: full, className: 'WorkerW', exePath: 'C:\\Windows\\explorer.exe' },
        primary,
        self
      )
    ).toBe(false)
    expect(
      shouldSuppressStrips(
        { rect: full, className: 'Chrome_WidgetWin_1', exePath: self },
        primary,
        self
      )
    ).toBe(false)
    expect(
      shouldSuppressStrips(
        { rect: null, className: 'X', exePath: 'C:\\g\\game.exe' },
        primary,
        self
      )
    ).toBe(false)
  })
})
