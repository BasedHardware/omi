// @vitest-environment jsdom
// Regression suite for the onboarding mic permission step.
//
// Two bugs are locked down here:
//
// 1. FALSE GRANT. The step read `navigator.permissions.query({name:'microphone'})` as
//    truth. Electron registers no permission-check handler, so Chromium answers
//    'granted' unconditionally — including on a fresh profile with the mic blocked by
//    Windows. The step therefore marked itself granted on mount, wrote
//    `continuousRecording: true`, and auto-advanced, without ever calling getUserMedia
//    or asking the OS. It now reads the REAL state from main (the Capability Access
//    Manager registry), and a state it merely DETECTED never auto-advances — it renders
//    a confirmed card and waits for Continue.
//
// 2. FALSE DENIAL RESCUE. A denial kept polling and got rescued back into "Granted"
//    within a second. A poll may confirm a grant; it may never overturn a refusal.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, act } from '@testing-library/react'
import { MicPermissionStep } from './MicPermissionStep'

const getUserMedia = vi.fn()
const getMicPermissionState = vi.fn()
const permissionsQuery = vi.fn()
const openMicPrivacySettings = vi.fn()
const setPreferences = vi.fn()

vi.mock('../../lib/preferences', () => ({
  setPreferences: (patch: unknown) => setPreferences(patch)
}))

/** A getUserMedia stream whose tracks we can assert were released. */
const fakeStream = (): MediaStream =>
  ({ getTracks: () => [{ stop: vi.fn() }] }) as unknown as MediaStream

const renderStep = (
  onContinue = vi.fn(),
  onSkip?: () => void
): { onContinue: ReturnType<typeof vi.fn> } => {
  render(
    <MicPermissionStep stepIndex={7} totalSteps={14} onContinue={onContinue} onSkip={onSkip} />
  )
  return { onContinue }
}

beforeEach(() => {
  vi.useFakeTimers()
  getUserMedia.mockReset()
  // The Windows default for an app that has never asked: consent not recorded.
  getMicPermissionState.mockReset().mockResolvedValue('unknown')
  openMicPrivacySettings.mockReset()
  setPreferences.mockReset()
  // Chromium's answer is a lie on Windows — always 'granted'. Wired up exactly as the
  // real runtime behaves, so any regression back to it fails these tests loudly.
  permissionsQuery.mockReset().mockResolvedValue({ state: 'granted' })
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia }
  })
  Object.defineProperty(navigator, 'permissions', {
    configurable: true,
    value: { query: permissionsQuery }
  })
  ;(window as unknown as { omi: unknown }).omi = { openMicPrivacySettings, getMicPermissionState }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

/** Let pending promises settle and drive `ms` of timers (poll + auto-advance). */
const tick = async (ms = 0): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('MicPermissionStep', () => {
  // THE C1 REGRESSION. With the OS consent unset, the step must sit and wait for the
  // user — no grant claim, no preference write, no auto-advance. Chromium says 'granted'
  // throughout (see the mock above); trusting it is exactly the bug.
  it('does NOT self-grant or self-skip when Windows has never recorded a consent', async () => {
    const { onContinue } = renderStep()
    await tick(5000)

    expect(screen.getByText('Not granted yet')).toBeTruthy()
    expect(screen.queryByText('Granted')).toBeNull()
    expect(onContinue).not.toHaveBeenCalled()
    expect(setPreferences).not.toHaveBeenCalled()
    expect(getUserMedia).not.toHaveBeenCalled()
  })

  it('never consults navigator.permissions — Electron answers granted unconditionally', async () => {
    renderStep()
    await tick(5000)
    expect(permissionsQuery).not.toHaveBeenCalled()
  })

  it('treats a Windows Deny as not-granted without prompting', async () => {
    getMicPermissionState.mockResolvedValue('denied')
    const { onContinue } = renderStep()
    await tick(5000)

    expect(screen.queryByText('Granted')).toBeNull()
    expect(onContinue).not.toHaveBeenCalled()
  })

  it('does NOT claim granted and does NOT advance when Windows denies the mic', async () => {
    const err = new Error('Permission denied')
    err.name = 'NotAllowedError'
    getUserMedia.mockRejectedValue(err)
    getMicPermissionState.mockResolvedValue('denied')

    const { onContinue } = renderStep()
    await tick()

    fireEvent.click(screen.getByText('Grant access'))
    await tick()

    expect(screen.queryByText('Granted')).toBeNull()
    expect(screen.getByText('Blocked by Windows')).toBeTruthy()
    expect(setPreferences).not.toHaveBeenCalled()

    // Well past both the old 1s blind advance and the new 350ms one.
    await tick(3000)
    expect(onContinue).not.toHaveBeenCalled()
  })

  it('offers a recovery path into Windows privacy settings after a denial', async () => {
    const err = new Error('Permission denied')
    err.name = 'NotAllowedError'
    getUserMedia.mockRejectedValue(err)
    getMicPermissionState.mockResolvedValue('denied')

    renderStep()
    await tick()
    fireEvent.click(screen.getByText('Grant access'))
    await tick()

    fireEvent.click(screen.getByText('Open Windows Settings'))
    expect(openMicPrivacySettings).toHaveBeenCalled()
  })

  it('grants, enables continuous recording, and advances after 350ms', async () => {
    getUserMedia.mockResolvedValue(fakeStream())

    const { onContinue } = renderStep()
    await tick()

    fireEvent.click(screen.getByText('Grant access'))
    await tick()

    expect(screen.getAllByText('Granted').length).toBeGreaterThan(0)
    expect(setPreferences).toHaveBeenCalledWith({ continuousRecording: true })
    // Mac parity: the advance waits ~350ms, it isn't synchronous.
    expect(onContinue).not.toHaveBeenCalled()

    await tick(350)
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  // M1: the auto-advance timer used to outlive the step. Leaving (Skip/Back) within the
  // 350ms window let the orphaned timer fire onContinue() *after* the step had already
  // advanced — landing the user two steps on and skipping one entirely.
  it('cancels the pending auto-advance when the step goes away', async () => {
    getUserMedia.mockResolvedValue(fakeStream())
    const { onContinue } = renderStep()
    await tick()

    fireEvent.click(screen.getByText('Grant access'))
    await tick()
    cleanup() // the user skipped / went back before the 350ms landed

    await tick(5000)
    expect(onContinue).not.toHaveBeenCalled()
  })

  // M2: a refusal is the user's answer. Polling stops, and a later 'granted' read cannot
  // silently rewrite it — the user re-asks with "Try again".
  it('does not let a poll rescue an explicit denial into a grant', async () => {
    const err = new Error('Permission denied')
    err.name = 'NotAllowedError'
    getUserMedia.mockRejectedValue(err)
    getMicPermissionState.mockResolvedValue('denied')

    const { onContinue } = renderStep()
    await tick()
    fireEvent.click(screen.getByText('Grant access'))
    await tick()
    expect(screen.getByText('Blocked by Windows')).toBeTruthy()

    // The OS flips to allowed underneath us (Windows Settings, another app, whatever).
    getMicPermissionState.mockResolvedValue('granted')
    await tick(5000)

    expect(screen.getByText('Blocked by Windows')).toBeTruthy()
    expect(screen.queryByText('Granted')).toBeNull()
    expect(onContinue).not.toHaveBeenCalled()
    expect(setPreferences).not.toHaveBeenCalled()
  })

  it('grants on Try again after the user allows the mic in Windows Settings', async () => {
    const err = new Error('Permission denied')
    err.name = 'NotAllowedError'
    getUserMedia.mockRejectedValue(err)
    getMicPermissionState.mockResolvedValue('denied')

    const { onContinue } = renderStep()
    await tick()
    fireEvent.click(screen.getByText('Grant access'))
    await tick()

    // Allowed in Windows Settings; back in the app, the user re-asks.
    getMicPermissionState.mockResolvedValue('granted')
    getUserMedia.mockResolvedValue(fakeStream())
    fireEvent.click(screen.getByText('Try again'))
    await tick()

    expect(screen.getAllByText('Granted').length).toBeGreaterThan(0)
    expect(setPreferences).toHaveBeenCalledWith({ continuousRecording: true })
    await tick(350)
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('stops polling once unmounted (no leaked interval)', async () => {
    renderStep()
    await tick(1000)
    const callsWhileMounted = getMicPermissionState.mock.calls.length
    expect(callsWhileMounted).toBeGreaterThan(0)

    cleanup()
    await tick(5000)
    expect(getMicPermissionState.mock.calls.length).toBe(callsWhileMounted)
  })

  describe('when Windows already allows the mic', () => {
    beforeEach(() => {
      getMicPermissionState.mockResolvedValue('granted')
      getUserMedia.mockResolvedValue(fakeStream())
    })

    // C1's other half: an already-granted step must CONFIRM and wait. It used to flash
    // past — the product owner never got to read it.
    it('confirms the grant and waits for Continue instead of flashing past', async () => {
      const { onContinue } = renderStep()
      await tick(5000)

      expect(screen.getAllByText('Granted').length).toBeGreaterThan(0)
      expect(screen.getByText('Continue')).toBeTruthy()
      expect(onContinue).not.toHaveBeenCalled()
      expect(getUserMedia).not.toHaveBeenCalled()
    })

    // M3: `continuousRecording: true` starts always-on mic streaming to /v4/listen. It
    // must ride on the user's own acceptance, never on a grant we merely observed.
    it('writes continuousRecording only once the user presses Continue', async () => {
      const { onContinue } = renderStep()
      await tick(5000)
      expect(setPreferences).not.toHaveBeenCalled()

      fireEvent.click(screen.getByText('Continue'))
      expect(setPreferences).toHaveBeenCalledExactlyOnceWith({ continuousRecording: true })
      expect(onContinue).toHaveBeenCalledTimes(1)
    })

    it('never opts into always-on recording when the user skips the step', async () => {
      const onSkip = vi.fn()
      renderStep(vi.fn(), onSkip)
      await tick(5000)

      fireEvent.click(screen.getByText('Skip'))
      expect(onSkip).toHaveBeenCalledTimes(1)
      expect(setPreferences).not.toHaveBeenCalled()
    })
  })
})
