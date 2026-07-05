import { describe, it, expect } from 'vitest'
import { revealStep } from './reveal'

// revealStep is the pure core of the smooth reveal: given how much text is
// still hidden and how long since the previous frame, decide how many chars
// to show this frame. Adaptive cadence: base ~5ms/char (~200 cps) but it
// accelerates with the backlog so it never trails the stream by much.
describe('revealStep', () => {
  it('reveals nothing when no text remains', () => {
    expect(revealStep(0, 16)).toBe(0)
    expect(revealStep(-3, 16)).toBe(0)
  })

  it('keeps a steady base rate with a small backlog (~4 chars per 16ms frame)', () => {
    // base = 16/5 = 3.2 -> ceil 4; catchUp = 10/8 = 1.25 (does not dominate)
    expect(revealStep(10, 16)).toBe(4)
  })

  it('accelerates to drain a large backlog in ~8 frames', () => {
    // catchUp = 800/8 = 100 dominates over the base rate
    expect(revealStep(800, 16)).toBe(100)
    // at that pace the backlog empties in CATCH_UP_FRAMES frames
    expect(Math.ceil(800 / revealStep(800, 16))).toBe(8)
  })

  it('never reveals more than what remains', () => {
    // base = 3.2 -> 4, but only 2 chars are left
    expect(revealStep(2, 16)).toBe(2)
  })

  it('always progresses at least 1 char when text remains, even with zero or negative dt', () => {
    expect(revealStep(5, 0)).toBeGreaterThanOrEqual(1)
    expect(revealStep(5, -50)).toBeGreaterThanOrEqual(1)
  })

  it('a late frame reveals proportionally more, not less', () => {
    // base = 140/5 = 28 vs the on-time 4 (catchUp = 100/8 = 12.5 does not dominate)
    expect(revealStep(100, 140)).toBe(28)
  })

  it('the reveal loop always drains regardless of backlog size', () => {
    for (const backlog of [1, 7, 42, 999, 10_000]) {
      let remaining = backlog
      let frames = 0
      while (remaining > 0) {
        const step = revealStep(remaining, 16)
        expect(step).toBeGreaterThanOrEqual(1)
        expect(step).toBeLessThanOrEqual(remaining)
        remaining -= step
        frames += 1
        expect(frames).toBeLessThan(10_000)
      }
      expect(remaining).toBe(0)
    }
  })
})
