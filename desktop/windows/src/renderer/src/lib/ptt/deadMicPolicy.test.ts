import { describe, it, expect, vi, beforeEach } from 'vitest'

// The silent-mic escalation policy (A7b): consecutive dead-mic PTT turns rebuild
// the capture stack at 2 and escalate the hint + distinct telemetry at 3, resetting
// on any non-dead turn. trackEvent is mocked so importing analytics never pulls in
// firebase and the fallback payloads are asserted directly.
const { trackEvent } = vi.hoisted(() => ({ trackEvent: vi.fn() }))
vi.mock('../analytics', () => ({ trackEvent }))

import {
  DeadMicPolicy,
  applyDeadMicTurn,
  DEAD_MIC_REBUILD_TURNS,
  DEAD_MIC_ESCALATE_TURNS,
  type DeadMicHint
} from './deadMicPolicy'

beforeEach(() => {
  trackEvent.mockClear()
})

describe('DeadMicPolicy (macOS PTTSilentMicRecoveryPolicy parity)', () => {
  it('uses the macOS thresholds (2 → rebuild, 3 → escalate)', () => {
    expect(DEAD_MIC_REBUILD_TURNS).toBe(2)
    expect(DEAD_MIC_ESCALATE_TURNS).toBe(3)
  })

  it('returns rebuild on the 2nd consecutive dead turn, escalate on the 3rd', () => {
    const p = new DeadMicPolicy()
    expect(p.record(true)).toBe('none') // 1
    expect(p.record(true)).toBe('rebuild') // 2
    expect(p.record(true)).toBe('escalate') // 3
    expect(p.count).toBe(3)
  })

  it('resets the counter on any non-dead turn', () => {
    const p = new DeadMicPolicy()
    p.record(true)
    p.record(true)
    expect(p.count).toBe(2)
    expect(p.record(false)).toBe('none') // a good/silent/too-short turn resets
    expect(p.count).toBe(0)
    expect(p.record(true)).toBe('none') // counting restarts from 1
    expect(p.count).toBe(1)
  })

  it('fires none for dead turns past the escalate tier (no repeated telemetry)', () => {
    const p = new DeadMicPolicy()
    p.record(true)
    p.record(true)
    p.record(true)
    expect(p.record(true)).toBe('none') // 4th dead turn — action already spent
    expect(p.count).toBe(4)
  })
})

describe('applyDeadMicTurn effects', () => {
  const mkFx = (): { rebuild: ReturnType<typeof vi.fn>; showHint: ReturnType<typeof vi.fn> } => ({
    rebuild: vi.fn(),
    showHint: vi.fn()
  })

  it('turn 1: shows the base dead-mic hint only (no rebuild, no telemetry)', () => {
    const p = new DeadMicPolicy()
    const fx = mkFx()
    applyDeadMicTurn(p, true, fx)
    expect(fx.rebuild).not.toHaveBeenCalled()
    expect(trackEvent).not.toHaveBeenCalled()
    expect(fx.showHint).toHaveBeenCalledWith<[DeadMicHint]>('dead-mic')
  })

  it('turn 2: rebuilds the capture stack + emits degraded silent_mic telemetry', () => {
    const p = new DeadMicPolicy()
    const fx = mkFx()
    applyDeadMicTurn(p, true, fx) // 1
    fx.rebuild.mockClear()
    trackEvent.mockClear()
    applyDeadMicTurn(p, true, fx) // 2
    expect(fx.rebuild).toHaveBeenCalledTimes(1)
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'rebuilt',
      reason: 'local_heal',
      outcome: 'degraded'
    })
    expect(fx.showHint).toHaveBeenLastCalledWith('dead-mic') // still base at 2
  })

  it('turn 3: escalates the hint + emits a distinct exhausted event (no rebuild)', () => {
    const p = new DeadMicPolicy()
    const fx = mkFx()
    applyDeadMicTurn(p, true, fx) // 1
    applyDeadMicTurn(p, true, fx) // 2
    fx.rebuild.mockClear()
    trackEvent.mockClear()
    applyDeadMicTurn(p, true, fx) // 3
    expect(fx.rebuild).not.toHaveBeenCalled()
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'none',
      reason: 'local_heal',
      outcome: 'exhausted'
    })
    expect(fx.showHint).toHaveBeenLastCalledWith('dead-mic-escalated')
  })

  it('a good turn resets: no hint, no telemetry, and the ladder restarts', () => {
    const p = new DeadMicPolicy()
    const fx = mkFx()
    applyDeadMicTurn(p, true, fx) // 1
    applyDeadMicTurn(p, true, fx) // 2 → rebuild
    trackEvent.mockClear()
    fx.rebuild.mockClear()
    fx.showHint.mockClear()

    applyDeadMicTurn(p, false, fx) // good turn resets
    expect(fx.showHint).not.toHaveBeenCalled()
    expect(fx.rebuild).not.toHaveBeenCalled()
    expect(trackEvent).not.toHaveBeenCalled()

    applyDeadMicTurn(p, true, fx) // back to turn 1
    expect(fx.showHint).toHaveBeenLastCalledWith('dead-mic')
    expect(fx.rebuild).not.toHaveBeenCalled()
  })

  it('keeps showing the escalated hint on dead turns past the tier', () => {
    const p = new DeadMicPolicy()
    const fx = mkFx()
    applyDeadMicTurn(p, true, fx) // 1
    applyDeadMicTurn(p, true, fx) // 2
    applyDeadMicTurn(p, true, fx) // 3
    applyDeadMicTurn(p, true, fx) // 4
    expect(fx.showHint).toHaveBeenLastCalledWith('dead-mic-escalated')
  })
})
