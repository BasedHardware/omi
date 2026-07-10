import { describe, it, expect } from 'vitest'
import { shouldShowBackgroundConsent } from './backgroundConsent'
import type { Preferences } from './preferences'

const base = {} as Preferences

describe('shouldShowBackgroundConsent', () => {
  it('shows for an onboarded user who has not acknowledged yet', () => {
    expect(shouldShowBackgroundConsent({ ...base, onboardingCompletedAt: 123 })).toBe(true)
  })

  it('does not show once acknowledged', () => {
    expect(
      shouldShowBackgroundConsent({ ...base, onboardingCompletedAt: 123, backgroundConsentAt: 456 })
    ).toBe(false)
  })

  it('does not show to a user still in onboarding (they consent inline)', () => {
    expect(shouldShowBackgroundConsent({ ...base })).toBe(false)
    expect(shouldShowBackgroundConsent({ ...base, onboardingStep: 4 })).toBe(false)
  })
})
