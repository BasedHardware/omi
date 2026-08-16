// @vitest-environment jsdom
// Windows has no OS consent prompt for desktop capture, so this step must be an
// honest local opt-in: it flips the Rewind capture setting, never fakes an OS
// round-trip, and never polls a permission that doesn't exist.
//
// THE PRIVACY REGRESSION: Rewind capture defaults to ON, but this step hard-coded an
// "Off" card with a "Turn on" button. So the screen was ALREADY being recorded while the
// step said it was off, "Turn on" was a no-op, and Skip walked past — leaving capture
// running while the user believed they had declined. The card now reads the real setting,
// and Skip is an explicit "no" that turns capture off.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, act } from '@testing-library/react'
import { ScreenPermissionStep } from './ScreenPermissionStep'

const rewindGetSettings = vi.fn()
const rewindSetSettings = vi.fn()
const permissionsQuery = vi.fn()

/** The shape the main process actually returns (rewindSettings.ts). */
const settings = (captureEnabled: boolean): Record<string, unknown> => ({
  captureEnabled,
  intervalMs: 1000,
  retentionDays: 14,
  excludedApps: []
})

beforeEach(() => {
  vi.useFakeTimers()
  rewindGetSettings.mockReset().mockResolvedValue(settings(false))
  rewindSetSettings.mockReset().mockImplementation(async (next) => next)
  permissionsQuery.mockReset().mockResolvedValue({ state: 'denied' })
  Object.defineProperty(navigator, 'permissions', {
    configurable: true,
    value: { query: permissionsQuery }
  })
  ;(window as unknown as { omi: unknown }).omi = { rewindGetSettings, rewindSetSettings }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const tick = async (ms = 0): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('ScreenPermissionStep', () => {
  it('turns on Rewind capture and advances — without polling any OS permission', async () => {
    const onContinue = vi.fn()
    render(<ScreenPermissionStep stepIndex={5} totalSteps={14} onContinue={onContinue} />)
    await tick()

    fireEvent.click(screen.getByText('Turn on'))
    await tick()

    expect(rewindSetSettings).toHaveBeenCalledWith(settings(true))
    // There is no Windows screen permission — the step must not invent one.
    expect(permissionsQuery).not.toHaveBeenCalled()

    await tick(350)
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('reports a failed opt-in instead of claiming it is on', async () => {
    rewindSetSettings.mockRejectedValue(new Error('disk full'))
    const onContinue = vi.fn()
    render(<ScreenPermissionStep stepIndex={5} totalSteps={14} onContinue={onContinue} />)
    await tick()

    fireEvent.click(screen.getByText('Turn on'))
    await tick(3000)

    expect(screen.getByText("Couldn't turn on")).toBeTruthy()
    expect(onContinue).not.toHaveBeenCalled()
  })

  describe('when capture is already on (the shipped default)', () => {
    beforeEach(() => {
      rewindGetSettings.mockResolvedValue(settings(true))
    })

    it('says On — it must not show Off while the screen is being recorded', async () => {
      const onContinue = vi.fn()
      render(<ScreenPermissionStep stepIndex={5} totalSteps={14} onContinue={onContinue} />)
      await tick(2000)

      expect(screen.getAllByText('On').length).toBeGreaterThan(0)
      expect(screen.queryByText('Off')).toBeNull()
      expect(screen.queryByText('Turn on')).toBeNull()
      // Detected, not consented — the user confirms, the step does not run off.
      expect(screen.getByText('Continue')).toBeTruthy()
      expect(onContinue).not.toHaveBeenCalled()
    })

    it('Skip means NO: it turns capture off rather than leaving it recording', async () => {
      const onSkip = vi.fn()
      render(
        <ScreenPermissionStep stepIndex={5} totalSteps={14} onContinue={vi.fn()} onSkip={onSkip} />
      )
      await tick(2000)

      fireEvent.click(screen.getByText('Skip'))
      await tick()

      expect(rewindSetSettings).toHaveBeenCalledWith(settings(false))
      expect(onSkip).toHaveBeenCalledTimes(1)
    })

    it('still advances on Skip when the decline write fails (never traps the user)', async () => {
      rewindSetSettings.mockRejectedValue(new Error('disk full'))
      const onSkip = vi.fn()
      render(
        <ScreenPermissionStep stepIndex={5} totalSteps={14} onContinue={vi.fn()} onSkip={onSkip} />
      )
      await tick(2000)

      fireEvent.click(screen.getByText('Skip'))
      await tick()

      expect(onSkip).toHaveBeenCalledTimes(1)
    })
  })
})
