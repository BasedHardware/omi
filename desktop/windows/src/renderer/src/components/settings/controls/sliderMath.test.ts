import { describe, it, expect } from 'vitest'
import { clamp, snapToStep, valueToFraction, fractionToValue } from './sliderMath'

describe('sliderMath.clamp', () => {
  it('clamps below/above and passes through in-range', () => {
    expect(clamp(-1, 0, 1)).toBe(0)
    expect(clamp(2, 0, 1)).toBe(1)
    expect(clamp(0.5, 0, 1)).toBe(0.5)
  })
})

describe('sliderMath.snapToStep', () => {
  it('snaps to the nearest step without float drift', () => {
    // 0.5..2.0 step 0.05 is the Font Size slider's config.
    expect(snapToStep(1.02, 0.5, 2, 0.05)).toBe(1.0)
    expect(snapToStep(1.03, 0.5, 2, 0.05)).toBe(1.05)
    // Would be 1.9500000000000002 via raw arithmetic — must stay clean.
    expect(snapToStep(1.94, 0.5, 2, 0.05)).toBe(1.95)
  })

  it('clamps out-of-range inputs to the endpoints', () => {
    expect(snapToStep(0.1, 0.5, 2, 0.05)).toBe(0.5)
    expect(snapToStep(9, 0.5, 2, 0.05)).toBe(2.0)
  })

  it('lands exactly on min and max', () => {
    expect(snapToStep(0.5, 0.5, 2, 0.05)).toBe(0.5)
    expect(snapToStep(2.0, 0.5, 2, 0.05)).toBe(2.0)
  })

  it('only clamps when step is non-positive', () => {
    expect(snapToStep(1.234, 0, 2, 0)).toBe(1.234)
  })
})

describe('sliderMath.valueToFraction', () => {
  it('maps min/mid/max to 0/0.5/1', () => {
    expect(valueToFraction(0.5, 0.5, 2)).toBe(0)
    expect(valueToFraction(1.25, 0.5, 2)).toBeCloseTo(0.5, 10)
    expect(valueToFraction(2, 0.5, 2)).toBe(1)
  })

  it('clamps out-of-range values into 0..1', () => {
    expect(valueToFraction(0, 0.5, 2)).toBe(0)
    expect(valueToFraction(5, 0.5, 2)).toBe(1)
  })

  it('is safe when the range is degenerate', () => {
    expect(valueToFraction(1, 1, 1)).toBe(0)
  })
})

describe('sliderMath.fractionToValue', () => {
  it('inverts valueToFraction and snaps', () => {
    expect(fractionToValue(0, 0.5, 2, 0.05)).toBe(0.5)
    expect(fractionToValue(1, 0.5, 2, 0.05)).toBe(2.0)
    expect(fractionToValue(0.5, 0.5, 2, 0.05)).toBe(1.25)
  })

  it('round-trips a snapped value through both directions', () => {
    const min = 0.5
    const max = 2
    const step = 0.05
    for (const v of [0.5, 0.85, 1.0, 1.4, 1.95, 2.0]) {
      const f = valueToFraction(v, min, max)
      expect(fractionToValue(f, min, max, step)).toBeCloseTo(v, 10)
    }
  })
})
