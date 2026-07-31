// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest'
import { shouldShowBackgroundConsent, persistBackgroundConsent } from './backgroundConsent'
import { getPreferences, setPreferences, type Preferences } from './preferences'

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

describe('persistBackgroundConsent', () => {
  beforeEach(() => {
    // Clear any consent stamped by a previous case so each assertion is isolated.
    setPreferences({
      continuousRecording: undefined,
      backgroundConsentAt: undefined,
      recordingConsentedAt: undefined
    })
  })

  it('stamps consent and records recordingConsentedAt when listening stays on', () => {
    persistBackgroundConsent({ listening: true, launchAtLogin: true })
    const prefs = getPreferences()
    expect(prefs.continuousRecording).toBe(true)
    expect(typeof prefs.backgroundConsentAt).toBe('number')
    expect(typeof prefs.recordingConsentedAt).toBe('number')
  })

  it('stamps consent but leaves recordingConsentedAt unset when listening is off', () => {
    persistBackgroundConsent({ listening: false, launchAtLogin: false })
    const prefs = getPreferences()
    expect(prefs.continuousRecording).toBe(false)
    expect(typeof prefs.backgroundConsentAt).toBe('number')
    expect(prefs.recordingConsentedAt).toBeUndefined()
  })
})
