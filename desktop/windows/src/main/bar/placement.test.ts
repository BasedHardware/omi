import { describe, it, expect } from 'vitest'
import {
  computeStripBounds,
  computeBarBounds,
  displayForPoint,
  shouldSuppressStrips,
  BAR_WINDOW_WIDTH,
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
  it('spans the display top edge, 1px tall, in DIPs', () => {
    expect(computeStripBounds(primary)).toEqual({ x: 0, y: 0, width: 2560, height: 1 })
    // Negative-origin secondary display (above-left arrangement) keeps its own origin.
    expect(computeStripBounds(secondary)).toEqual({ x: 2560, y: -200, width: 1920, height: 1 })
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
        { rect: { x: 0, y: 0, width: 2560, height: 1440 }, className: 'UnityWndClass', exePath: 'C:\\g\\game.exe' },
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
      shouldSuppressStrips({ rect: maxed, className: 'X', exePath: 'C:\\g\\game.exe' }, secondary, self)
    ).toBe(false)
  })

  it('never suppresses for shell surfaces, our own exe, or no rect', () => {
    const full = { x: 0, y: 0, width: 2560, height: 1440 }
    expect(
      shouldSuppressStrips({ rect: full, className: 'WorkerW', exePath: 'C:\\Windows\\explorer.exe' }, primary, self)
    ).toBe(false)
    expect(shouldSuppressStrips({ rect: full, className: 'Chrome_WidgetWin_1', exePath: self }, primary, self)).toBe(
      false
    )
    expect(shouldSuppressStrips({ rect: null, className: 'X', exePath: 'C:\\g\\game.exe' }, primary, self)).toBe(false)
  })
})
