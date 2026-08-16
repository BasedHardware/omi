import { describe, it, expect } from 'vitest'
import { backfillFromRing } from './pttGraph'

// backfillFromRing seeds a hold with the most recent `ms` of pre-roll from the
// warm graph's ring, back to key-down. It must preserve chronological order and
// trim the OLDEST included chunk to the sample so nothing before the window leaks.

const SAMPLE_RATE = 16000
const msToSamples = (ms: number): number => Math.round((ms / 1000) * SAMPLE_RATE)

function chunk(value: number, len: number): Int16Array {
  return new Int16Array(len).fill(value)
}

function concat(chunks: Int16Array[]): Int16Array {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const out = new Int16Array(total)
  let off = 0
  for (const c of chunks) {
    out.set(c, off)
    off += c.length
  }
  return out
}

describe('backfillFromRing', () => {
  // Four 80-sample chunks (5ms each), oldest → newest, tagged 1/2/3/4.
  const ring = [chunk(1, 80), chunk(2, 80), chunk(3, 80), chunk(4, 80)]
  const ringSamples = 320

  it('returns nothing for a zero window', () => {
    expect(backfillFromRing(ring, ringSamples, 0)).toEqual([])
  })

  it('returns whole chunks in chronological order when the window is aligned', () => {
    // 10ms = 160 samples = the two newest chunks.
    const out = concat(backfillFromRing(ring, ringSamples, 10))
    expect(msToSamples(10)).toBe(160)
    expect(out.length).toBe(160)
    expect(Array.from(out.slice(0, 80)).every((v) => v === 3)).toBe(true)
    expect(Array.from(out.slice(80)).every((v) => v === 4)).toBe(true)
  })

  it('trims the oldest included chunk to the sample and keeps order', () => {
    // 7.5ms = 120 samples = last 40 of chunk 3, then all of chunk 4.
    const parts = backfillFromRing(ring, ringSamples, 7.5)
    const out = concat(parts)
    expect(msToSamples(7.5)).toBe(120)
    expect(out.length).toBe(120)
    expect(Array.from(out.slice(0, 40)).every((v) => v === 3)).toBe(true)
    expect(Array.from(out.slice(40)).every((v) => v === 4)).toBe(true)
  })

  it('caps at what the ring holds and returns everything in order', () => {
    const out = concat(backfillFromRing(ring, ringSamples, 1000))
    expect(out.length).toBe(320)
    expect(Array.from(out.slice(0, 80)).every((v) => v === 1)).toBe(true)
    expect(Array.from(out.slice(240)).every((v) => v === 4)).toBe(true)
  })
})
