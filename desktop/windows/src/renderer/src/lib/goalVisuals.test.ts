import { describe, it, expect } from 'vitest'
import { progressColor, isCompleted, progressPct, progressLabel } from './goalVisuals'

const GREEN = '#22C55E'
const LIME = '#84CC16'
const YELLOW = '#FBBF24'
const ORANGE = '#F97316'
const NEUTRAL = 'rgba(255, 255, 255, 0.3)'

describe('progressColor', () => {
  it('returns the exact color at each bucket boundary', () => {
    const cases: Array<[number, string]> = [
      [0, NEUTRAL],
      [0.19, NEUTRAL],
      [0.2, ORANGE],
      [0.39, ORANGE],
      [0.4, YELLOW],
      [0.59, YELLOW],
      [0.6, LIME],
      [0.79, LIME],
      [0.8, GREEN],
      [1.0, GREEN]
    ]
    for (const [fraction, color] of cases) {
      expect(progressColor(fraction), `${fraction}`).toBe(color)
    }
  })
})

describe('isCompleted', () => {
  it('is complete when archived (is_active === false)', () => {
    expect(isCompleted({ is_active: false, target_value: 10, current_value: 0 })).toBe(true)
  })
  it('is complete when progress reaches the target', () => {
    expect(isCompleted({ target_value: 10, current_value: 10 })).toBe(true)
    expect(isCompleted({ target_value: 10, current_value: 12 })).toBe(true)
  })
  it('is not complete below target with no archive flag', () => {
    expect(isCompleted({ target_value: 10, current_value: 4 })).toBe(false)
  })
  it('is not complete with no positive target', () => {
    expect(isCompleted({ target_value: 0, current_value: 5 })).toBe(false)
  })
})

describe('progressPct', () => {
  it('clamps current/target into 0–100', () => {
    expect(progressPct({ target_value: 10, current_value: 4 })).toBe(40)
    expect(progressPct({ target_value: 10, current_value: 0 })).toBe(0)
  })
  it('reports 100 for a completed goal', () => {
    expect(progressPct({ target_value: 10, current_value: 15 })).toBe(100)
    expect(progressPct({ is_active: false, target_value: 10, current_value: 0 })).toBe(100)
  })
})

describe('progressLabel', () => {
  it('shows current / target with an optional unit', () => {
    expect(progressLabel({ target_value: 24, current_value: 6, unit: 'books' })).toBe(
      '6 / 24 books'
    )
    expect(progressLabel({ target_value: 24, current_value: 6 })).toBe('6 / 24')
  })
  it('falls back to a percentage with no target', () => {
    expect(progressLabel({ target_value: 0, current_value: 0 })).toBe('0%')
  })
})
