import { describe, it, expect } from 'vitest'
import { tweenHeights } from './heightTween'

describe('tweenHeights', () => {
  it('returns a sequence ending exactly at the target', () => {
    const seq = tweenHeights(100, 300, 8)
    expect(seq[seq.length - 1]).toBe(300)
  })

  it('starts strictly after the source (does not re-emit the current height)', () => {
    const seq = tweenHeights(100, 300, 8)
    expect(seq[0]).toBeGreaterThan(100)
  })

  it('is monotonically increasing when growing', () => {
    const seq = tweenHeights(100, 300, 8)
    for (let i = 1; i < seq.length; i++) expect(seq[i]).toBeGreaterThanOrEqual(seq[i - 1])
  })

  it('is monotonically decreasing when shrinking', () => {
    const seq = tweenHeights(400, 120, 8)
    for (let i = 1; i < seq.length; i++) expect(seq[i]).toBeLessThanOrEqual(seq[i - 1])
    expect(seq[seq.length - 1]).toBe(120)
  })

  it('returns a single target step when from === to', () => {
    expect(tweenHeights(200, 200, 8)).toEqual([200])
  })

  it('returns just the target when steps <= 1', () => {
    expect(tweenHeights(100, 300, 1)).toEqual([300])
  })

  it('produces integer heights only', () => {
    const seq = tweenHeights(100, 333, 6)
    for (const h of seq) expect(Number.isInteger(h)).toBe(true)
  })
})
