import { describe, it, expect } from 'vitest'
import { nextOverflowing } from './homeScroll'

describe('nextOverflowing', () => {
  it('turns the mask on only past a clear overflow', () => {
    // 0px overshoot: not overflowing.
    expect(nextOverflowing(false, 500, 500)).toBe(false)
    // A few px over is within the dead zone — stays off (no flicker at the boundary).
    expect(nextOverflowing(false, 510, 500)).toBe(false)
    // Clearly overflowing — turns on.
    expect(nextOverflowing(false, 540, 500)).toBe(true)
  })

  it('keeps the mask on until the content clearly fits again', () => {
    // Still clearly overflowing.
    expect(nextOverflowing(true, 540, 500)).toBe(true)
    // Dipped just under the on-threshold but not under the off-threshold — stays on.
    expect(nextOverflowing(true, 510, 500)).toBe(true)
    // Clearly fits now — turns off.
    expect(nextOverflowing(true, 502, 500)).toBe(false)
  })

  it('does not flip across a small oscillation around the boundary (the flicker)', () => {
    // Geometry wobbling by ~10px around the fit point during the open animation
    // must not toggle the flag once it has settled off.
    let on = false
    for (const overshoot of [8, 12, 6, 15, 10, 4, 14]) {
      on = nextOverflowing(on, 500 + overshoot, 500)
      expect(on).toBe(false) // never crosses the 24px on-threshold → never flickers on
    }
  })

  it('is stable once on despite the same small oscillation', () => {
    let on = nextOverflowing(false, 540, 500) // clearly overflowing → on
    expect(on).toBe(true)
    for (const overshoot of [8, 12, 6, 15, 10]) {
      on = nextOverflowing(on, 500 + overshoot, 500)
      expect(on).toBe(true) // stays > 4px off-threshold → never flickers off
    }
  })
})
