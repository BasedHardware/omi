import { describe, it, expect } from 'vitest'
import { RateLimitDegradedTracker } from './rateLimitDegraded'

/** A tracker with a controllable clock. Defaults require ≥2 distinct keys unless a
 *  test overrides them. */
function makeTracker(
  overrides?: Partial<{ threshold: number; windowMs: number; minDistinctKeys: number }>
) {
  let clock = 1_000
  const changes: boolean[] = []
  const tracker = new RateLimitDegradedTracker({
    threshold: overrides?.threshold ?? 3,
    windowMs: overrides?.windowMs ?? 20_000,
    minDistinctKeys: overrides?.minDistinctKeys ?? 2,
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
  it('stays healthy below the count threshold', () => {
    const { tracker, changes } = makeTracker({ threshold: 3 })
    expect(tracker.record429('a')).toBe(false)
    expect(tracker.record429('b')).toBe(false)
    expect(tracker.isDegraded()).toBe(false)
    expect(changes).toEqual([])
  })

  it('a single endpoint retry-looping does NOT trip (one distinct key)', () => {
    const { tracker, changes } = makeTracker({ threshold: 3, minDistinctKeys: 2 })
    // Five 429s, all the same key — a retry loop on one path, not an account storm.
    for (let i = 0; i < 5; i++) tracker.record429('GET /v1/action-items')
    expect(tracker.isDegraded()).toBe(false)
    expect(changes).toEqual([])
  })

  it('flips to degraded once threshold 429s land across ≥2 distinct keys in the window', () => {
    const { tracker, changes } = makeTracker({ threshold: 3, windowMs: 20_000, minDistinctKeys: 2 })
    tracker.record429('GET /v1/action-items')
    tracker.record429('GET /v1/action-items')
    expect(tracker.record429('DELETE /v1/action-items/:id')).toBe(true) // 3rd, 2nd distinct key
    expect(tracker.isDegraded()).toBe(true)
    expect(changes).toEqual([true])
  })

  it('does not count 429s that have aged out of the window', () => {
    const { tracker, changes, advance } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429('a')
    advance(21_000) // first 429 ages out
    tracker.record429('b')
    tracker.record429('c')
    expect(tracker.isDegraded()).toBe(false) // only 2 within window
    expect(changes).toEqual([])
  })

  it('does not re-fire onChange while already degraded (debounced)', () => {
    const { tracker, changes } = makeTracker({ threshold: 3 })
    tracker.record429('a')
    tracker.record429('b')
    tracker.record429('c') // → degraded
    expect(tracker.record429('d')).toBe(false)
    expect(tracker.record429('e')).toBe(false)
    expect(changes).toEqual([true]) // exactly one transition
  })

  it('a success during an active storm does NOT clear (anti-flicker)', () => {
    const { tracker, changes } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429('a')
    tracker.record429('b')
    tracker.record429('c') // → degraded, 429s still fresh
    expect(tracker.recordSuccess()).toBe(false)
    expect(tracker.isDegraded()).toBe(true)
    expect(changes).toEqual([true])
  })

  it('clears to healthy on a success once the storm has aged out', () => {
    const { tracker, changes, advance } = makeTracker({ threshold: 3, windowMs: 20_000 })
    tracker.record429('a')
    tracker.record429('b')
    tracker.record429('c') // → degraded
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
    const { tracker, changes, advance } = makeTracker({
      threshold: 2,
      windowMs: 10_000,
      minDistinctKeys: 2
    })
    tracker.record429('a')
    tracker.record429('b') // degraded
    advance(11_000)
    tracker.recordSuccess() // healthy
    tracker.record429('a')
    tracker.record429('b') // degraded again
    expect(changes).toEqual([true, false, true])
  })

  it('minDistinctKeys:1 lets a single-key burst trip (count-only mode)', () => {
    const { tracker } = makeTracker({ threshold: 3, minDistinctKeys: 1 })
    tracker.record429('same')
    tracker.record429('same')
    expect(tracker.record429('same')).toBe(true)
    expect(tracker.isDegraded()).toBe(true)
  })

  it('injected onChange is optional (no throw without it)', () => {
    const tracker = new RateLimitDegradedTracker({
      threshold: 1,
      windowMs: 1000,
      minDistinctKeys: 1,
      now: () => 0
    })
    expect(() => tracker.record429('x')).not.toThrow()
    expect(tracker.isDegraded()).toBe(true)
  })
})
