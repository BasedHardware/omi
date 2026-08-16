import { describe, it, expect } from 'vitest'
import {
  evaluatePeekWatchdog,
  nextInteractivity,
  barWatchPlan,
  barGestureSeesOpen,
  clickEdge,
  type WatchdogInput
} from './watchdog'

/** A baseline "nothing holds the pill, cursor is away, already visited" input —
 *  the short post-visit grace path unless a test overrides hasBeenHovered. */
function base(over: Partial<WatchdogInput> = {}): WatchdogInput {
  return {
    suspended: false,
    activityHold: false,
    gestureActive: false,
    cursorInFootprint: false,
    hasBeenHovered: true,
    outsideSince: null,
    now: 1000,
    graceMs: 600,
    lingerMs: 3000,
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

  it('(b) a visited-then-left pill retracts after the short grace', () => {
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

  it('(d) a freshly summoned pill the cursor has NOT reached lingers ~3s, not 600ms', () => {
    // Live bug: on a tap the cursor is at the working position, so the pill is
    // "outside the footprint" from tick zero — it must survive the ~3s the hand
    // needs to travel to it, not vanish at the short 600ms grace.
    const stamp = evaluatePeekWatchdog(base({ hasBeenHovered: false, now: 0, outsideSince: null }))
    expect(stamp.outsideSince).toBe(0)
    expect(stamp.retract).toBe(false)
    // Past the SHORT grace but well inside the linger: still open (the fix).
    expect(
      evaluatePeekWatchdog(base({ hasBeenHovered: false, now: 600, outsideSince: 0 })).retract
    ).toBe(false)
    expect(
      evaluatePeekWatchdog(base({ hasBeenHovered: false, now: 2999, outsideSince: 0 })).retract
    ).toBe(false)
    // Only once the full linger elapses does an untouched pill retract.
    expect(
      evaluatePeekWatchdog(base({ hasBeenHovered: false, now: 3000, outsideSince: 0 })).retract
    ).toBe(true)
  })

  it('the E2E suspend hold, the renderer activity hold, and the cursor each pin the pill open', () => {
    for (const hold of [{ suspended: true }, { activityHold: true }, { cursorInFootprint: true }]) {
      // Even an unvisited pill (the linger path) is trumped by an explicit hold.
      const s = evaluatePeekWatchdog(
        base({ ...hold, hasBeenHovered: false, outsideSince: 0, now: 100000 })
      )
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

describe('barWatchPlan — which halves run per mode (Bug A live gap)', () => {
  it('peek runs BOTH interactivity and the retract grace', () => {
    expect(barWatchPlan('peek')).toEqual({ trackInteractivity: true, runRetract: true })
  })

  it('ptt arms interactivity (so a lingering pill is clickable) but NEVER retracts on the cursor', () => {
    // The Bug A live gap: click-to-expand must work from a ptt-summoned pill, but
    // a ptt pill's lifetime is owned by the gesture/keepAlive — the cursor
    // watchdog must not hide it.
    expect(barWatchPlan('ptt')).toEqual({ trackInteractivity: true, runRetract: false })
  })

  it('expanded and no-mode run neither half (the watch is stopped)', () => {
    expect(barWatchPlan('expanded')).toEqual({ trackInteractivity: false, runRetract: false })
    expect(barWatchPlan(null)).toEqual({ trackInteractivity: false, runRetract: false })
  })
})

describe('barGestureSeesOpen — stuck-window inversion fix', () => {
  it('a clean peek / ptt / expanded presentation reads as OPEN', () => {
    expect(barGestureSeesOpen({ visible: true, mode: 'peek', hiding: false })).toBe(true)
    expect(barGestureSeesOpen({ visible: true, mode: 'ptt', hiding: false })).toBe(true)
    expect(barGestureSeesOpen({ visible: true, mode: 'expanded', hiding: false })).toBe(true)
  })

  it('a window MID-RETRACT (shown but sliding out) is NOT open — a tap must re-present', () => {
    // The live inversion: a tap during the slide-out used to see raw visibility
    // and skip showBar (peek watch never restarted → dead clicks) + toggle shut.
    expect(barGestureSeesOpen({ visible: true, mode: 'peek', hiding: true })).toBe(false)
  })

  it('a shown-but-unpresented window (mode null, e.g. a hide that did not take) is NOT open', () => {
    expect(barGestureSeesOpen({ visible: true, mode: null, hiding: false })).toBe(false)
  })

  it('a hidden window is NOT open', () => {
    expect(barGestureSeesOpen({ visible: false, mode: 'peek', hiding: false })).toBe(false)
    expect(barGestureSeesOpen({ visible: false, mode: null, hiding: false })).toBe(false)
  })
})

describe('clickEdge — main-side pill click detection (touchpad/WM_POINTER fix)', () => {
  it('fires once on the up→down edge after an UP was seen over the pill (armed)', () => {
    // Cursor arrives over the pill with the button up → arm.
    const armed = clickEdge({ buttonDown: false, overPill: true, active: true, armed: false })
    expect(armed).toEqual({ armed: true, expand: false })
    // Next tick the button is down → expand once, disarm.
    const fired = clickEdge({ buttonDown: true, overPill: true, active: true, armed: armed.armed })
    expect(fired).toEqual({ armed: false, expand: true })
  })

  it('does NOT fire for a button ALREADY down when the cursor arrives (needs an up first)', () => {
    // Button already held as the cursor reaches the pill, never armed → ignore.
    const r = clickEdge({ buttonDown: true, overPill: true, active: true, armed: false })
    expect(r).toEqual({ armed: false, expand: false })
  })

  it('does not re-fire while the button stays held after a click', () => {
    // Fire on the edge…
    const fired = clickEdge({ buttonDown: true, overPill: true, active: true, armed: true })
    expect(fired.expand).toBe(true)
    // …then held down across the next ticks: disarmed, no repeat.
    const held = clickEdge({ buttonDown: true, overPill: true, active: true, armed: fired.armed })
    expect(held).toEqual({ armed: false, expand: false })
  })

  it('re-arms after release so a second click fires', () => {
    let s = clickEdge({ buttonDown: true, overPill: true, active: true, armed: true }) // click 1
    expect(s.expand).toBe(true)
    s = clickEdge({ buttonDown: false, overPill: true, active: true, armed: s.armed }) // release
    expect(s).toEqual({ armed: true, expand: false })
    s = clickEdge({ buttonDown: true, overPill: true, active: true, armed: s.armed }) // click 2
    expect(s.expand).toBe(true)
  })

  it('off the pill or inactive: never fires and disarms', () => {
    // Off the pill (even armed + button down) → no fire, disarmed.
    expect(clickEdge({ buttonDown: true, overPill: false, active: true, armed: true })).toEqual({
      armed: false,
      expand: false
    })
    // Inactive (E2E screenshot hold / not collapsed) → no fire, disarmed.
    expect(clickEdge({ buttonDown: true, overPill: true, active: false, armed: true })).toEqual({
      armed: false,
      expand: false
    })
  })
})
