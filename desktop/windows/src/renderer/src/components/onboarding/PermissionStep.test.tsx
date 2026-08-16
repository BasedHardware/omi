// @vitest-environment jsdom
// The shared permission-step machinery, tested directly. The per-step suites
// (MicPermissionStep, ScreenPermissionStep) cover the wiring; these pin the state
// transitions every step inherits.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, act } from '@testing-library/react'
import { PermissionStep } from './PermissionStep'

// Distinct card vs button copy, so an assertion can tell which one it matched.
const statusText = {
  idle: 'Idle',
  waiting: 'Waiting',
  granted: 'Granted',
  denied: 'Denied'
} as const
const buttonLabel = {
  idle: 'Act',
  waiting: 'Acting',
  granted: 'Done',
  denied: 'Retry'
} as const

type Overrides = Partial<React.ComponentProps<typeof PermissionStep>>

const renderStep = (overrides: Overrides = {}): void => {
  render(
    <PermissionStep
      stepIndex={5}
      totalSteps={14}
      eyebrow="PERMISSION"
      title="Test permission"
      icon={<span />}
      cardLabel="Thing"
      statusText={statusText}
      buttonLabel={buttonLabel}
      onActivate={async () => {}}
      onContinue={vi.fn()}
      {...overrides}
    />
  )
}

const tick = async (ms = 0): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('PermissionStep', () => {
  it('auto-advances a grant the user clicked for', async () => {
    const onContinue = vi.fn()
    renderStep({ onContinue })

    fireEvent.click(screen.getByText('Act'))
    await tick(350)

    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  // A permission that was already granted before the step opened must be CONFIRMED, not
  // silently consumed: onboarding may not flash a screen the user never interacted with.
  it('confirms a detected grant and waits for Continue', async () => {
    const onContinue = vi.fn()
    const onGranted = vi.fn()
    renderStep({ onContinue, onGranted, checkGranted: async () => true })
    await tick(5000)

    expect(screen.getByText('Granted')).toBeTruthy()
    expect(onContinue).not.toHaveBeenCalled()
    // Detection is not consent — the grant side effects wait for the user too.
    expect(onGranted).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('Continue'))
    expect(onGranted).toHaveBeenCalledTimes(1)
    expect(onContinue).toHaveBeenCalledTimes(1)
  })

  it('fires the grant side effects exactly once, whichever route the user took', async () => {
    const onGranted = vi.fn()
    renderStep({ onGranted, checkGranted: async () => false })

    fireEvent.click(screen.getByText('Act'))
    await tick(2000)

    expect(onGranted).toHaveBeenCalledTimes(1)
  })

  // The poll used to race an in-flight request: a 'granted' read could land while
  // onActivate's rejection was still in the air, marking the step granted on the way to
  // a refusal. A detected grant may only ever speak from a standing start.
  it('does not let a poll preempt an in-flight request that is about to fail', async () => {
    const onContinue = vi.fn()
    let reject: (e: Error) => void = () => {}
    renderStep({
      onContinue,
      onActivate: () => new Promise<void>((_res, rej) => (reject = rej)),
      checkGranted: async () => true
    })

    fireEvent.click(screen.getByText('Act'))
    await tick(2000) // polls fire while the request hangs

    expect(screen.queryByText('Granted')).toBeNull()
    expect(screen.getByText('Waiting')).toBeTruthy()

    await act(async () => reject(new Error('blocked')))
    await tick(2000)

    expect(screen.getByText('Denied')).toBeTruthy()
    expect(onContinue).not.toHaveBeenCalled()
  })

  it('stops polling on denial — a refusal is never rescued into a grant', async () => {
    const onContinue = vi.fn()
    const checkGranted = vi.fn().mockResolvedValue(false)
    renderStep({
      onContinue,
      onActivate: async () => {
        throw new Error('blocked')
      },
      checkGranted
    })

    fireEvent.click(screen.getByText('Act'))
    await tick()
    expect(screen.getByText('Denied')).toBeTruthy()

    checkGranted.mockResolvedValue(true)
    const callsAtDenial = checkGranted.mock.calls.length
    await tick(5000)

    expect(checkGranted.mock.calls.length).toBe(callsAtDenial)
    expect(screen.queryByText('Granted')).toBeNull()
    expect(onContinue).not.toHaveBeenCalled()
  })

  // M1: the orphaned 350ms timer used to fire onContinue() *after* Skip had already
  // advanced the wizard, landing the user two steps on and skipping one entirely.
  it('cancels the pending auto-advance on unmount', async () => {
    const onContinue = vi.fn()
    renderStep({ onContinue })

    fireEvent.click(screen.getByText('Act'))
    await tick(100)
    cleanup()
    await tick(5000)

    expect(onContinue).not.toHaveBeenCalled()
  })

  it('hides Skip once the user has granted, so it cannot race the advance', async () => {
    renderStep({ onSkip: vi.fn() })
    expect(screen.getByText('Skip')).toBeTruthy()

    fireEvent.click(screen.getByText('Act'))
    await tick()

    expect(screen.queryByText('Skip')).toBeNull()
  })

  // …but a DETECTED grant keeps Skip: it is the user's only way to decline something
  // that is already on (screen capture ships enabled).
  it('keeps Skip available on a detected grant', async () => {
    renderStep({ onSkip: vi.fn(), checkGranted: async () => true })
    await tick(2000)

    expect(screen.getByText('Granted')).toBeTruthy()
    expect(screen.getByText('Skip')).toBeTruthy()
  })

  it('offers Back when the step supports it', async () => {
    const onBack = vi.fn()
    renderStep({ onBack })

    fireEvent.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
