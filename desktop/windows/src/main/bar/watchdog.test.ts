import { describe, it, expect } from 'vitest'
import { evaluatePeekWatchdog, nextInteractivity, type WatchdogInput } from './watchdog'

/** A baseline "nothing holds the pill, cursor is away" input. */
function base(over: Partial<WatchdogInput> = {}): WatchdogInput {
  return {
    suspended: false,
    activityHold: false,
    gestureActive: false,
    cursorInFootprint: false,
    outsideSince: null,
    now: 1000,
    graceMs: 600,
    ...over
  }
}

describe('evaluatePeekWatchdog — retract grace', () => {
  it('(a) an active summon gesture pins the pill open even with the cursor away and no keepAlive (Bug B)', () => {
    // Cursor outside, no activity hold, but the key is physically held: the pill
    // must NOT start the retract grace no matter how much time passes.
    let s = evaluatePeekWatchdog(base({ gestureActive: true, outsideSince: null }))
    expect(s.retract).toBe(false)
    expect(s.outsideSince).toBe(null)
    // Even carrying a stale outsideSince, an active gesture resets it to null.
    s = evaluatePeekWatchdog(base({ gestureActive: true, outsideSince: 0, now: 100000 }))
    expect(s.retract).toBe(false)
    expect(s.outsideSince).toBe(null)
  })

  it('(b) a tap (gesture no longer active) retracts after the normal grace', () => {
    // First outside tick just stamps the clock, never retracts.
    let s = evaluatePeekWatchdog(base({ now: 1000, outsideSince: null }))
    expect(s.retract).toBe(false)
    expect(s.outsideSince).toBe(1000)
    // Before the grace elapses: still open.
    s = evaluatePeekWatchdog(base({ now: 1000 + 599, outsideSince: 1000 }))
    expect(s.retract).toBe(false)
    // At/after the grace: retract.
    s = evaluatePeekWatchdog(base({ now: 1000 + 600, outsideSince: 1000 }))
    expect(s.retract).toBe(true)
  })

  it('(c) gesture end with no busy hold retracts only after the grace, not instantly', () => {
    // The moment the hold clears, outsideSince is null — the first tick stamps
    // it, and only a full graceMs later does retract fire.
    const stamp = evaluatePeekWatchdog(base({ now: 5000, outsideSince: null }))
    expect(stamp.retract).toBe(false)
    expect(stamp.outsideSince).toBe(5000)
    expect(evaluatePeekWatchdog(base({ now: 5300, outsideSince: 5000 })).retract).toBe(false)
    expect(evaluatePeekWatchdog(base({ now: 5600, outsideSince: 5000 })).retract).toBe(true)
  })

  it('the E2E suspend hold, the renderer activity hold, and the cursor each pin the pill open', () => {
    for (const hold of [{ suspended: true }, { activityHold: true }, { cursorInFootprint: true }]) {
      const s = evaluatePeekWatchdog(base({ ...hold, outsideSince: 0, now: 100000 }))
      expect(s.retract).toBe(false)
      expect(s.outsideSince).toBe(null)
    }
  })
})

describe('nextInteractivity — main-driven hit-testing (Bug A)', () => {
  it('enables hit-testing the moment the cursor is over the pill', () => {
    expect(nextInteractivity({ cursorOverPill: true, interactive: false, suspended: false })).toBe(
      true
    )
  })

  it('disables hit-testing the moment the cursor leaves the pill', () => {
    expect(nextInteractivity({ cursorOverPill: false, interactive: true, suspended: false })).toBe(
      false
    )
  })

  it('freezes the current state while the E2E screenshot hold is active', () => {
    // A parked cursor during a screenshot run must not flip hit-testing either way.
    expect(nextInteractivity({ cursorOverPill: false, interactive: true, suspended: true })).toBe(
      true
    )
    expect(nextInteractivity({ cursorOverPill: true, interactive: false, suspended: true })).toBe(
      false
    )
  })
})
