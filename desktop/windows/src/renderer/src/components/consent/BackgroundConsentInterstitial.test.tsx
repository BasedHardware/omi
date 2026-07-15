// @vitest-environment jsdom
//
// Guards the existing-user "Background & privacy" interstitial after the decision
// to PRE-CHECK launch-at-login (Mac-parity default) instead of silently migrating
// the OS setting. The silent migration was scrapped because Windows cannot tell an
// explicit prior OFF from a plain default OFF; here the user actively confirms.
//
// These use the REAL preferences + backgroundConsent modules (only window.omi is
// stubbed) so the mic/continuous-listening default and its recordingConsentedAt
// stamping are covered too — that's the regression guard proving the default flip
// touched ONLY launch-at-login.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import { BackgroundConsentInterstitial } from './BackgroundConsentInterstitial'
import { getPreferences, setPreferences } from '../../lib/preferences'

const setLaunchAtLogin = vi.fn()
const getLoginItemSettings = vi.fn()

// Seed an existing, onboarded user who has NOT yet acknowledged the interstitial,
// so shouldShowBackgroundConsent() is true and the modal renders.
beforeEach(() => {
  localStorage.clear()
  setPreferences({
    onboardingCompletedAt: Date.now(),
    backgroundConsentAt: undefined,
    continuousRecording: undefined,
    recordingConsentedAt: undefined
  })
  setLaunchAtLogin.mockReset().mockResolvedValue(undefined)
  // Packaged-build state: launch-at-login is writable, currently off at the OS.
  getLoginItemSettings.mockReset().mockResolvedValue({ openAtLogin: false, supported: true })
  ;(window as unknown as { omi: unknown }).omi = { setLaunchAtLogin, getLoginItemSettings }
})

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// Let the BackgroundConsentControls getLoginItemSettings effect settle.
const flush = async (): Promise<void> => {
  await act(async () => {
    await Promise.resolve()
  })
}

describe('BackgroundConsentInterstitial', () => {
  it('pre-checks launch-at-login, leaving continuous-listening at the user’s existing value (off)', async () => {
    const { getByRole } = render(<BackgroundConsentInterstitial />)
    await flush()

    expect(getByRole('switch', { name: 'Launch at login' }).getAttribute('aria-checked')).toBe(
      'true'
    )
    // The mic default is NOT touched by this change: an existing user whose
    // continuous-listening was off stays off (pre-checking only launch-at-login).
    expect(getByRole('switch', { name: 'Continuous listening' }).getAttribute('aria-checked')).toBe(
      'false'
    )
  })

  it('confirming as-is enables launch-at-login and stamps consent without turning the mic on', async () => {
    const { getByText } = render(<BackgroundConsentInterstitial />)
    await flush()

    fireEvent.click(getByText('Got it'))

    expect(setLaunchAtLogin).toHaveBeenCalledExactlyOnceWith(true)
    const prefs = getPreferences()
    expect(typeof prefs.backgroundConsentAt).toBe('number')
    // Mic stayed off → no always-on recording, no recording-consent stamp.
    expect(prefs.continuousRecording).toBe(false)
    expect(prefs.recordingConsentedAt).toBeUndefined()
  })

  it('respects an explicit uncheck — confirming with the box off persists launchAtLogin:false', async () => {
    const { getByRole, getByText } = render(<BackgroundConsentInterstitial />)
    await flush()

    fireEvent.click(getByRole('switch', { name: 'Launch at login' })) // user unchecks it
    expect(getByRole('switch', { name: 'Launch at login' }).getAttribute('aria-checked')).toBe(
      'false'
    )

    fireEvent.click(getByText('Got it'))
    expect(setLaunchAtLogin).toHaveBeenCalledExactlyOnceWith(false)
  })

  // Regression guard: the change must not alter the mic default or its consent
  // stamping. A user whose continuous-listening was already ON keeps it on and
  // still stamps recordingConsentedAt, exactly as before the launch-at-login flip.
  it('preserves an already-on mic and still stamps recordingConsentedAt', async () => {
    setPreferences({ continuousRecording: true })
    const { getByRole, getByText } = render(<BackgroundConsentInterstitial />)
    await flush()

    expect(getByRole('switch', { name: 'Continuous listening' }).getAttribute('aria-checked')).toBe(
      'true'
    )

    fireEvent.click(getByText('Got it'))

    const prefs = getPreferences()
    expect(prefs.continuousRecording).toBe(true)
    expect(typeof prefs.recordingConsentedAt).toBe('number')
    // Launch-at-login still pre-checked and enabled on confirm.
    expect(setLaunchAtLogin).toHaveBeenCalledExactlyOnceWith(true)
  })
})
