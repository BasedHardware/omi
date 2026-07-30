import { describe, it, expect } from 'vitest'
import { PcmRing } from './pcmRing'

/** Int16Array [start, start+len). */
function seq(start: number, len: number): Int16Array {
  const out = new Int16Array(len)
  for (let i = 0; i < len; i++) out[i] = start + i
  return out
}

describe('PcmRing', () => {
  it('retains everything below capacity', () => {
    const ring = new PcmRing(100)
    ring.push(seq(0, 30))
    ring.push(seq(30, 40))
    expect(ring.length).toBe(70)
    expect(Array.from(ring.drain())).toEqual(Array.from(seq(0, 70)))
  })

  it('evicts whole leading chunks only when the floor is still met (PTT parity)', () => {
    const ring = new PcmRing(100)
    ring.push(seq(0, 60)) // 60
    ring.push(seq(60, 60)) // 120 → dropping the 60-chunk leaves 60 (< 100), so keep both
    expect(ring.length).toBe(120)
    ring.push(seq(120, 60)) // 180 → dropping the first 60 leaves 120 (>= 100), evict it
    expect(ring.length).toBe(120)
    // Order preserved, oldest chunk gone.
    expect(Array.from(ring.drain())).toEqual(Array.from(seq(60, 120)))
  })

  it('drains the most-recent N samples, trimmed to the sample', () => {
    const ring = new PcmRing(1000)
    ring.push(seq(0, 50))
    ring.push(seq(50, 50)) // total 100
    const out = ring.drain(30) // last 30 samples → 70..99
    expect(Array.from(out)).toEqual(Array.from(seq(70, 30)))
  })

  it('trims across a chunk boundary when the window splits a chunk', () => {
    const ring = new PcmRing(1000)
    ring.push(seq(0, 40))
    ring.push(seq(40, 40)) // total 80
    const out = ring.drain(60) // last 60 → 20..79 (partial of chunk0 + all chunk1)
    expect(Array.from(out)).toEqual(Array.from(seq(20, 60)))
  })

  it('empties the ring on drain', () => {
    const ring = new PcmRing(1000)
    ring.push(seq(0, 40))
    ring.drain()
    expect(ring.length).toBe(0)
    expect(ring.drain().length).toBe(0)
  })

  it('clamps a request larger than what is retained', () => {
    const ring = new PcmRing(1000)
    ring.push(seq(0, 10))
    expect(Array.from(ring.drain(9999))).toEqual(Array.from(seq(0, 10)))
  })

  it('ignores empty pushes', () => {
    const ring = new PcmRing(100)
    ring.push(new Int16Array(0))
    expect(ring.length).toBe(0)
  })

  it('clear() drops retained audio', () => {
    const ring = new PcmRing(100)
    ring.push(seq(0, 50))
    ring.clear()
    expect(ring.length).toBe(0)
  })
})
