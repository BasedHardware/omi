import { describe, it, expect } from 'vitest'
import { RateLimitDegradedTracker } from './rateLimitDegraded'

/** A tracker with a controllable clock. */
function makeTracker(overrides?: Partial<{ threshold: number; windowMs: number }>) {
  let clock = 1_000
  const changes: boolean[] = []
  const tracker = new RateLimitDegradedTracker({
    threshold: overrides?.threshold ?? 3,
    windowMs: overrides?.windowMs ?? 20_000,
    now: () => clock,
    onChange: (d) => changes.push(d)
  })
  return {
    tracker,
    changes,
    advance: (ms: number) => {
      clock += ms
    }
  }
}

describe('RateLimitDegradedTracker', () => {
  it('stays healthy below the threshold', () => {
    const { tracker, changes } = makeTracker({ threshold: 3 })
    expect(tracker.record429()).toBe(false)
    expect(tracker.record429()).toBe(false)
    expect(tracker.isDegraded()).toBe(false)
    expect(changes).toEqual([])
  })

  it('flips to degraded once threshold 429s land within the window', () => {
    const { tracker, changes } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429()
    tracker.record429()
    expect(tracker.record429()).toBe(true) // 3rd within window → transition
    expect(tracker.isDegraded()).toBe(true)
    expect(changes).toEqual([true])
  })

  it('does not count 429s that have aged out of the window', () => {
    const { tracker, changes, advance } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429()
    advance(21_000) // first 429 ages out
    tracker.record429()
    tracker.record429()
    expect(tracker.isDegraded()).toBe(false) // only 2 within window
    expect(changes).toEqual([])
  })

  it('does not re-fire onChange while already degraded (debounced)', () => {
    const { tracker, changes } = makeTracker({ threshold: 3 })
    tracker.record429()
    tracker.record429()
    tracker.record429() // → degraded
    expect(tracker.record429()).toBe(false)
    expect(tracker.record429()).toBe(false)
    expect(changes).toEqual([true]) // exactly one transition
  })

  it('a success during an active storm does NOT clear (anti-flicker)', () => {
    const { tracker, changes } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429()
    tracker.record429()
    tracker.record429() // → degraded, 429s still fresh
    expect(tracker.recordSuccess()).toBe(false)
    expect(tracker.isDegraded()).toBe(true)
    expect(changes).toEqual([true])
  })

  it('clears to healthy on a success once the storm has aged out', () => {
    const { tracker, changes, advance } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429()
    tracker.record429()
    tracker.record429() // → degraded
    advance(21_000) // all 429s age out
    expect(tracker.recordSuccess()).toBe(true) // → healthy
    expect(tracker.isDegraded()).toBe(false)
    expect(changes).toEqual([true, false])
  })

  it('a success while healthy never fires onChange', () => {
    const { tracker, changes } = makeTracker()
    expect(tracker.recordSuccess()).toBe(false)
    expect(changes).toEqual([])
  })

  it('can cycle degraded → healthy → degraded again', () => {
    const { tracker, changes, advance } = makeTracker({ threshold: 2, windowMs: 10_000 })
    tracker.record429()
    tracker.record429() // degraded
    advance(11_000)
    tracker.recordSuccess() // healthy
    tracker.record429()
    tracker.record429() // degraded again
    expect(changes).toEqual([true, false, true])
  })

  it('injected onChange is optional (no throw without it)', () => {
    const tracker = new RateLimitDegradedTracker({ threshold: 1, windowMs: 1000, now: () => 0 })
    expect(() => tracker.record429()).not.toThrow()
    expect(tracker.isDegraded()).toBe(true)
  })
})
