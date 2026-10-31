// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockAuthState: { currentUser: { uid: string } | null } = {
  currentUser: { uid: 'user-1' }
}

vi.mock('../../lib/firebase', () => ({
  get auth() {
    return mockAuthState
  },
  onAuthStateChanged: (_auth: unknown, cb: () => void) => {
    cb()
    return () => {}
  }
}))

import { getPreferences, setPreferences } from '../../lib/preferences'
import { MuteReminderHost } from './MuteReminderHost'

interface FakeOscillator {
  type: string
  frequency: { setValueAtTime: ReturnType<typeof vi.fn> }
  connect: ReturnType<typeof vi.fn>
  start: ReturnType<typeof vi.fn>
  stop: ReturnType<typeof vi.fn>
  onended: (() => void) | null
}

function installFakeAudioContext(options?: {
  initialState?: AudioContextState
  resumeImpl?: (ctx: { state: AudioContextState }) => Promise<void>
  throwOnCreateOscillator?: boolean
}) {
  const instances: Array<{
    state: AudioContextState
    currentTime: number
    destination: object
    resume: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    createOscillator: ReturnType<typeof vi.fn>
    createGain: ReturnType<typeof vi.fn>
    osc: FakeOscillator
  }> = []

  class FakeAudioContext {
    state: AudioContextState = options?.initialState ?? 'suspended'
    currentTime = 0
    destination = {}
    osc: FakeOscillator = {
      type: 'sine',
      frequency: { setValueAtTime: vi.fn() },
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      onended: null
    }
    gain = {
      gain: {
        setValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn()
      },
      connect: vi.fn()
    }
    resume = vi.fn(() => {
      if (options?.resumeImpl) {
        return options.resumeImpl(this)
      }
      this.state = 'running'
      return Promise.resolve()
    })
    close = vi.fn(() => {
      this.state = 'closed'
      return Promise.resolve()
    })
    createOscillator = vi.fn(() => {
      if (options?.throwOnCreateOscillator) {
        throw new Error('oscillator creation failed')
      }
      return this.osc
    })
    createGain = vi.fn(() => this.gain)

    constructor() {
      instances.push(this)
    }
  }

  Object.defineProperty(window, 'AudioContext', {
    configurable: true,
    writable: true,
    value: FakeAudioContext
  })

  return instances
}

function triggerHighUrgencyMuteReminder(notifySpy: ReturnType<typeof vi.fn>): void {
  Object.defineProperty(window, 'omi', {
    configurable: true,
    writable: true,
    value: {
      notifyMutedRecordingReminder: notifySpy
    }
  })

  setPreferences({
    onboardingCompletedAt: 1_700_000_000_000,
    continuousRecording: true,
    muteReminderUrgency: 'high',
    muteReminderIntervalMinutes: 60
  })

  render(<MuteReminderHost />)

  act(() => {
    setPreferences({ continuousRecording: false })
  })

  act(() => {
    vi.advanceTimersByTime(60 * 60_000)
  })
}

describe('MuteReminderHost AudioContext lifecycle & defaults (#20215)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    mockAuthState.currentUser = { uid: 'user-1' }
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    localStorage.clear()
    Reflect.deleteProperty(window, 'AudioContext')
    Reflect.deleteProperty(window, 'omi')
  })

  it('defaults muteReminderIntervalMinutes preference to 60 minutes', () => {
    expect(getPreferences().muteReminderUrgency).toBe('standard')
    expect(getPreferences().muteReminderIntervalMinutes).toBe(60)
  })

  it('explicitly resumes a suspended AudioContext and closes it once when oscillator ends', async () => {
    const instances = installFakeAudioContext({ initialState: 'suspended' })
    const notifySpy = vi.fn()

    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      await Promise.resolve()
    })

    expect(notifySpy).toHaveBeenCalledTimes(1)
    expect(instances).toHaveLength(1)
    const ctx = instances[0]
    expect(ctx.resume).toHaveBeenCalledTimes(1)
    expect(ctx.osc.start).toHaveBeenCalledTimes(1)
    expect(ctx.osc.stop).toHaveBeenCalledTimes(1)
    expect(ctx.close).not.toHaveBeenCalled()

    act(() => {
      ctx.osc.onended?.()
    })
    expect(ctx.close).toHaveBeenCalledTimes(1)

    // Advancing past the fallback close timer must not re-close an already closed context.
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(ctx.close).toHaveBeenCalledTimes(1)
  })

  it('closes the AudioContext if resume() hangs under autoplay policy (tray-only launch)', async () => {
    const instances = installFakeAudioContext({
      initialState: 'suspended',
      resumeImpl: () => new Promise<void>(() => {})
    })
    const notifySpy = vi.fn()

    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      vi.advanceTimersByTime(600)
      await Promise.resolve()
    })

    expect(instances).toHaveLength(1)
    const ctx = instances[0]
    expect(ctx.resume).toHaveBeenCalledTimes(1)
    expect(ctx.osc.start).not.toHaveBeenCalled()
    expect(ctx.close).toHaveBeenCalledTimes(1)
  })

  it('closes the AudioContext if resume() rejects or leaves the context suspended', async () => {
    const rejectedInstances = installFakeAudioContext({
      initialState: 'suspended',
      resumeImpl: () => Promise.reject(new Error('NotAllowedError'))
    })
    const notifySpy = vi.fn()

    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      await Promise.resolve()
    })

    expect(rejectedInstances).toHaveLength(1)
    expect(rejectedInstances[0].resume).toHaveBeenCalledTimes(1)
    expect(rejectedInstances[0].osc.start).not.toHaveBeenCalled()
    expect(rejectedInstances[0].close).toHaveBeenCalledTimes(1)

    cleanup()
    localStorage.clear()

    const stillSuspendedInstances = installFakeAudioContext({
      initialState: 'suspended',
      resumeImpl: async () => {
        /* resolves without entering 'running' */
      }
    })
    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      await Promise.resolve()
    })

    expect(stillSuspendedInstances).toHaveLength(1)
    expect(stillSuspendedInstances[0].osc.start).not.toHaveBeenCalled()
    expect(stillSuspendedInstances[0].close).toHaveBeenCalledTimes(1)
  })

  it('closes the AudioContext when node setup throws or onended never fires', async () => {
    const throwingInstances = installFakeAudioContext({
      initialState: 'suspended',
      throwOnCreateOscillator: true
    })
    const notifySpy = vi.fn()

    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      await Promise.resolve()
    })

    expect(throwingInstances).toHaveLength(1)
    expect(throwingInstances[0].resume).toHaveBeenCalledTimes(1)
    expect(throwingInstances[0].close).toHaveBeenCalledTimes(1)

    cleanup()
    localStorage.clear()

    const silentEndInstances = installFakeAudioContext({ initialState: 'running' })
    triggerHighUrgencyMuteReminder(notifySpy)
    await act(async () => {
      await Promise.resolve()
    })

    expect(silentEndInstances).toHaveLength(1)
    expect(silentEndInstances[0].osc.start).toHaveBeenCalledTimes(1)
    expect(silentEndInstances[0].close).not.toHaveBeenCalled()

    // Even if osc.onended never fires, the fallback timer closes the context.
    act(() => {
      vi.advanceTimersByTime(1600)
    })
    expect(silentEndInstances[0].close).toHaveBeenCalledTimes(1)
  })
})
