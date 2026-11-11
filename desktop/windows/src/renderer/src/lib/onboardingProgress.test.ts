import { describe, it, expect } from 'vitest'
import { clampOnboardingStep } from './onboardingProgress'

describe('clampOnboardingStep', () => {
  const TOTAL = 14 // last valid step is 13

  it('resumes at a valid saved step', () => {
    expect(clampOnboardingStep(5, TOTAL)).toBe(5)
    expect(clampOnboardingStep(0, TOTAL)).toBe(0)
    expect(clampOnboardingStep(13, TOTAL)).toBe(13)
  })

  it('treats a missing/invalid value as the first step', () => {
    expect(clampOnboardingStep(undefined, TOTAL)).toBe(0)
    expect(clampOnboardingStep(null, TOTAL)).toBe(0)
    expect(clampOnboardingStep(NaN, TOTAL)).toBe(0)
    expect(clampOnboardingStep('3' as unknown, TOTAL)).toBe(0)
  })

  it('clamps an out-of-range saved step (step list shrank between versions)', () => {
    expect(clampOnboardingStep(99, TOTAL)).toBe(13)
    expect(clampOnboardingStep(-4, TOTAL)).toBe(0)
  })

  it('floors a fractional value', () => {
    expect(clampOnboardingStep(4.9, TOTAL)).toBe(4)
  })

  it('handles a single-step wizard without going negative', () => {
    expect(clampOnboardingStep(5, 1)).toBe(0)
    expect(clampOnboardingStep(0, 0)).toBe(0)
  })
})
