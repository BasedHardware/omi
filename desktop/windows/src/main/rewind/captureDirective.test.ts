import { describe, it, expect } from 'vitest'
import {
  reduceCaptureState,
  computeCaptureDirective,
  pushDelayForTransition,
  shouldApplyLockTransition,
  BATTERY_CAPTURE_INTERVAL_MULTIPLIER,
  RESUME_SETTLE_MS,
  LOCK_DEBOUNCE_MS,
  type CaptureDirectiveState
} from './captureDirective'

const base: CaptureDirectiveState = {
  suspended: false,
  locked: false,
  onBattery: false,
  baseIntervalMs: 1000
}

describe('computeCaptureDirective — battery cadence', () => {
  it('keeps the base interval on AC power', () => {
    expect(computeCaptureDirective(base)).toEqual({ paused: false, intervalMs: 1000 })
  })
  it('multiplies the interval by 3 on battery', () => {
    expect(computeCaptureDirective({ ...base, onBattery: true })).toEqual({
      paused: false,
      intervalMs: 1000 * BATTERY_CAPTURE_INTERVAL_MULTIPLIER
    })
  })
  it('scales an arbitrary base interval by the multiplier on battery', () => {
    expect(computeCaptureDirective({ ...base, baseIntervalMs: 2500, onBattery: true })).toEqual({
      paused: false,
      intervalMs: 2500 * BATTERY_CAPTURE_INTERVAL_MULTIPLIER
    })
  })
})

describe('reduceCaptureState — power transitions', () => {
  it('on-battery → 3× interval, on-ac → base interval', () => {
    const onBattery = reduceCaptureState(base, 'on-battery')
    expect(computeCaptureDirective(onBattery).intervalMs).toBe(3000)
    const backToAc = reduceCaptureState(onBattery, 'on-ac')
    expect(computeCaptureDirective(backToAc).intervalMs).toBe(1000)
  })
})

describe('sleep/lock pause transitions', () => {
  it('suspend → paused, resume → unpaused', () => {
    const suspended = reduceCaptureState(base, 'suspend')
    expect(computeCaptureDirective(suspended).paused).toBe(true)
    const resumed = reduceCaptureState(suspended, 'resume')
    expect(computeCaptureDirective(resumed).paused).toBe(false)
  })
  it('lock-screen → paused, unlock-screen → unpaused', () => {
    const locked = reduceCaptureState(base, 'lock-screen')
    expect(computeCaptureDirective(locked).paused).toBe(true)
    const unlocked = reduceCaptureState(locked, 'unlock-screen')
    expect(computeCaptureDirective(unlocked).paused).toBe(false)
  })
  it('stays paused if either sleep or lock is still active', () => {
    let s = reduceCaptureState(base, 'suspend')
    s = reduceCaptureState(s, 'lock-screen')
    s = reduceCaptureState(s, 'resume') // woke, but still locked
    expect(computeCaptureDirective(s).paused).toBe(true)
    s = reduceCaptureState(s, 'unlock-screen')
    expect(computeCaptureDirective(s).paused).toBe(false)
  })
})

describe('wake-settle asymmetry (resume 1.5s, unlock immediate)', () => {
  it('resume waits the settle delay, unlock restarts immediately', () => {
    expect(pushDelayForTransition('resume')).toBe(RESUME_SETTLE_MS)
    expect(pushDelayForTransition('unlock-screen')).toBe(0)
    expect(pushDelayForTransition('suspend')).toBe(0)
    expect(pushDelayForTransition('lock-screen')).toBe(0)
  })
})

describe('lock/unlock debounce (~1s)', () => {
  it('ignores a repeated identical lock within the window', () => {
    expect(shouldApplyLockTransition('lock-screen', 1000, 'lock-screen', 1500)).toBe(false)
  })
  it('applies a repeated lock once the window has elapsed', () => {
    expect(
      shouldApplyLockTransition('lock-screen', 1000, 'lock-screen', 1000 + LOCK_DEBOUNCE_MS)
    ).toBe(true)
  })
  it('always applies an unlock right after a lock (different event)', () => {
    expect(shouldApplyLockTransition('lock-screen', 1000, 'unlock-screen', 1100)).toBe(true)
  })
  it('never debounces non-lock transitions', () => {
    expect(shouldApplyLockTransition('on-battery', 1000, 'on-battery', 1000)).toBe(true)
  })
})
