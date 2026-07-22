import { describe, it, expect } from 'vitest'
import { keepLastPositive } from './measure'

describe('keepLastPositive', () => {
  it('accepts a positive new measurement', () => {
    expect(keepLastPositive(0, 240)).toBe(240)
    expect(keepLastPositive(100, 240)).toBe(240)
  })

  // Regression: a display:none page panel makes the ResizeObserver report 0.
  // The cached size must survive so a re-shown panel does not paint at 0 and
  // then snap to the real size — the intermittent home-card / timeline glitch.
  it('keeps the last real size when the new measurement is 0 (hidden panel)', () => {
    expect(keepLastPositive(240, 0)).toBe(240)
  })

  it('keeps the previous size for missing / non-finite measurements', () => {
    expect(keepLastPositive(240, undefined)).toBe(240)
    expect(keepLastPositive(240, null)).toBe(240)
    expect(keepLastPositive(240, NaN)).toBe(240)
    expect(keepLastPositive(240, -5)).toBe(240)
  })

  it('stays at 0 before any real measurement has arrived', () => {
    // First paint before layout can legitimately read 0; callers keep their own
    // fallback (e.g. `|| 600`) for that pre-measure window.
    expect(keepLastPositive(0, 0)).toBe(0)
    expect(keepLastPositive(0, undefined)).toBe(0)
  })
})
