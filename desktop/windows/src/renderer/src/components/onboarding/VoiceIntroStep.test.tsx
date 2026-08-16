// @vitest-environment jsdom
// Regression suite for the onboarding voice step (step 10).
//
// THE BUG (reported from a real run): "when I clicked my hotkey in the onboarding
// to talk to Omi, the Continue button never popped up until I did it a couple
// times." Verified against the built app by driving the real global chord with
// Win32 keybd_event: a TAP produces `gesture END kind=tap` and NO
// `overlay:voiceCaptured`, so Continue — gated on that event — never appeared. A
// HOLD (>=350ms) produced exactly one voiceCaptured and revealed Continue. The
// step, meanwhile, told the user to "Press your shortcut", and its only
// hold-instruction branch was behind `overlay:visibility.active`, which is never
// true for the non-focusable peek pill. So the screen only ever asked for the one
// gesture that cannot satisfy its own gate.
//
// Locked down here:
//   1. The step asks the user to HOLD the configured chord (never "press").
//   2. A capture reveals Continue.
//   3. A summon with no capture (i.e. a tap) is called out instead of sitting silent.
//   4. A failed capture (dead mic / transcription error) says so AND unlocks Continue.
//   5. A blocked Windows mic says so AND unlocks Continue.
//   6. Nothing at all: Continue unlocks after the fallback timeout. The gate can
//      never be a dead end.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, act } from '@testing-library/react'
import { VoiceIntroStep, VOICE_STEP_FALLBACK_MS, VOICE_STEP_NUDGE_MS } from './VoiceIntroStep'

const getMicPermissionState = vi.fn()

vi.mock('../../lib/preferences', () => ({
  getPreferences: () => ({ overlayShortcut: 'Shift+Space' })
}))

// The overlay bridge, with hand-held emitters for the three signals the step
// listens to. Mirrors the real preload: subscribe → unsubscribe fn.
type Emitters = {
  voiceCaptured: () => void
  voiceFailed: (message: string) => void
  summoned: () => void
  setEnabled: ReturnType<typeof vi.fn>
}

function installOverlayBridge(): Emitters {
  const captured: (() => void)[] = []
  const failed: ((m: string) => void)[] = []
  const summoned: (() => void)[] = []
  const setEnabled = vi.fn()
  const sub = <T,>(list: T[], cb: T): (() => void) => {
    list.push(cb)
    return () => {
      const i = list.indexOf(cb)
      if (i >= 0) list.splice(i, 1)
    }
  }
  ;(window as unknown as { omiOverlay: unknown }).omiOverlay = {
    setEnabled,
    onVoiceCaptured: (cb: () => void) => sub(captured, cb),
    onVoiceFailed: (cb: (m: string) => void) => sub(failed, cb),
    onSummoned: (cb: () => void) => sub(summoned, cb),
    onVisibilityChange: () => () => {}
  }
  ;(window as unknown as { omi: unknown }).omi = { getMicPermissionState }
  return {
    voiceCaptured: () => captured.forEach((c) => c()),
    voiceFailed: (m) => failed.forEach((c) => c(m)),
    summoned: () => summoned.forEach((c) => c()),
    setEnabled
  }
}

let bridge: Emitters

const renderStep = (): { onContinue: ReturnType<typeof vi.fn> } => {
  const onContinue = vi.fn()
  render(<VoiceIntroStep stepIndex={10} totalSteps={14} onContinue={onContinue} onSkip={vi.fn()} />)
  return { onContinue }
}

const tick = async (ms = 0): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

const continueButton = (): HTMLElement | null =>
  screen.queryAllByRole('button').find((b) => b.textContent === 'Continue') ?? null

beforeEach(() => {
  vi.useFakeTimers()
  getMicPermissionState.mockReset().mockResolvedValue('granted')
  bridge = installOverlayBridge()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('VoiceIntroStep', () => {
  // THE ROOT CAUSE. A tap cannot record — only a hold can — so the instruction
  // must say hold, and must name the user's actual chord.
  it('tells the user to HOLD the configured chord, never to press it', async () => {
    renderStep()
    await tick()

    expect(screen.getByText(/Hold Shift \+ Space/)).toBeTruthy()
    expect(screen.queryByText(/Press your shortcut/i)).toBeNull()
    // The dead branch that could never render (the peek pill is non-focusable, so
    // overlay `active` is never true, and Space never reaches the bar anyway).
    expect(screen.queryByText(/Hold the Space key/i)).toBeNull()
    expect(bridge.setEnabled).toHaveBeenCalledWith(true)
  })

  it('has no Continue button before a capture', async () => {
    renderStep()
    await tick()
    expect(continueButton()).toBeNull()
  })

  it('reveals Continue when a capture completes', async () => {
    const { onContinue } = renderStep()
    await tick()

    await act(async () => bridge.voiceCaptured())
    const btn = continueButton()
    expect(btn).not.toBeNull()

    btn!.click()
    expect(onContinue).toHaveBeenCalled()
  })

  // The reported experience: the hotkey fires (the bar peeks) but the press was a
  // tap, so no capture follows. The step used to sit there saying nothing.
  it('nudges the user to keep holding when the hotkey fires but no capture follows', async () => {
    renderStep()
    await act(async () => bridge.summoned())

    expect(screen.queryByText(/Keep the keys held down/i)).toBeNull()
    await tick(VOICE_STEP_NUDGE_MS)
    expect(screen.getByText(/Keep the keys held down/i)).toBeTruthy()
  })

  it('does not nudge when the hold actually captured', async () => {
    renderStep()
    await act(async () => {
      bridge.summoned()
      bridge.voiceCaptured()
    })
    await tick(VOICE_STEP_NUDGE_MS)

    expect(screen.queryByText(/Keep the keys held down/i)).toBeNull()
    expect(continueButton()).not.toBeNull()
  })

  // A mic failure cancels the PTT machine, so captureEnded/voiceCaptured NEVER
  // fires. Without this the user is stuck behind a gate nothing can open.
  it('surfaces a failed capture and unlocks Continue', async () => {
    renderStep()
    await tick()

    await act(async () => bridge.voiceFailed('Microphone unavailable'))
    expect(screen.getByText('Microphone unavailable')).toBeTruthy()
    expect(continueButton()).not.toBeNull()
  })

  it('says so and unlocks Continue when Windows is blocking the mic', async () => {
    getMicPermissionState.mockResolvedValue('denied')
    renderStep()
    await tick()

    expect(screen.getByText(/blocking Omi’s microphone/i)).toBeTruthy()
    expect(continueButton()).not.toBeNull()
  })

  // The escape hatch that cannot fail: whatever went wrong — a detector that never
  // fires, a bar that never mounted, a hotkey another app stole — the user gets out.
  it('unlocks Continue after the fallback timeout when nothing at all happens', async () => {
    const { onContinue } = renderStep()
    await tick(VOICE_STEP_FALLBACK_MS - 1000)
    expect(continueButton()).toBeNull()

    await tick(1000)
    const btn = continueButton()
    expect(btn).not.toBeNull()
    expect(screen.getByText(/Can’t get it to work\?/i)).toBeTruthy()

    btn!.click()
    expect(onContinue).toHaveBeenCalled()
  })
})
