import { describe, it, expect, vi } from 'vitest'
import { scheduleStartupSteps, DEFAULT_STEP_GAP_MS, type StartupStep } from './startupScheduler'

// A manual timer: records (cb, ms) instead of scheduling, so tests drive
// execution deterministically without real timers.
function makeManualTimer() {
  const scheduled: { cb: () => void; ms: number }[] = []
  const setTimerFn = (cb: () => void, ms: number): unknown => {
    scheduled.push({ cb, ms })
    return 0
  }
  // Run pending callbacks in scheduled-delay order (stable for equal delays),
  // matching how a real timer queue fires.
  const flush = (): void => {
    scheduled
      .map((s, i) => ({ ...s, i }))
      .sort((a, b) => a.ms - b.ms || a.i - b.i)
      .forEach((s) => s.cb())
  }
  return { scheduled, setTimerFn, flush }
}

describe('scheduleStartupSteps', () => {
  it('runs every step exactly once, in order', () => {
    const order: string[] = []
    const steps: StartupStep[] = ['a', 'b', 'c', 'd'].map((name) => ({
      name,
      run: () => order.push(name)
    }))
    const { setTimerFn, flush } = makeManualTimer()
    scheduleStartupSteps(steps, 24, setTimerFn)
    expect(order).toEqual([]) // nothing runs synchronously
    flush()
    expect(order).toEqual(['a', 'b', 'c', 'd'])
  })

  it('spaces steps by gapMs, first step at delay 0', () => {
    const { scheduled, setTimerFn } = makeManualTimer()
    scheduleStartupSteps(
      [
        { name: 'a', run: () => {} },
        { name: 'b', run: () => {} },
        { name: 'c', run: () => {} }
      ],
      30,
      setTimerFn
    )
    expect(scheduled.map((s) => s.ms)).toEqual([0, 30, 60])
  })

  it('isolates a throwing step so the rest still run', () => {
    const order: string[] = []
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const steps: StartupStep[] = [
      { name: 'ok1', run: () => order.push('ok1') },
      {
        name: 'boom',
        run: () => {
          throw new Error('kaboom')
        }
      },
      { name: 'ok2', run: () => order.push('ok2') }
    ]
    const { setTimerFn, flush } = makeManualTimer()
    scheduleStartupSteps(steps, 24, setTimerFn)
    flush()
    expect(order).toEqual(['ok1', 'ok2'])
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('boom'))
    warn.mockRestore()
  })

  it('defaults the gap when omitted', () => {
    const { scheduled, setTimerFn } = makeManualTimer()
    scheduleStartupSteps(
      [
        { name: 'a', run: () => {} },
        { name: 'b', run: () => {} }
      ],
      undefined,
      setTimerFn
    )
    expect(scheduled.map((s) => s.ms)).toEqual([0, DEFAULT_STEP_GAP_MS])
  })

  it('handles an empty step list without scheduling anything', () => {
    const { scheduled, setTimerFn } = makeManualTimer()
    scheduleStartupSteps([], 24, setTimerFn)
    expect(scheduled).toEqual([])
  })
})
