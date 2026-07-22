import { describe, it, expect } from 'vitest'
import { SpeechHysteresis, Float32Reblocker } from './speechTicker'

describe('SpeechHysteresis', () => {
  it('emits start only when crossing the positive threshold from silence', () => {
    const h = new SpeechHysteresis(0.3, 0.25)
    expect(h.feed(0.1)).toBeNull()
    expect(h.feed(0.29)).toBeNull() // just under positive
    expect(h.feed(0.3)).toBe('start') // >= positive
    expect(h.feed(0.9)).toBeNull() // already speaking
  })

  it('stays speaking until it dips below the (lower) negative threshold', () => {
    const h = new SpeechHysteresis(0.3, 0.25)
    h.feed(0.5) // start
    expect(h.feed(0.26)).toBeNull() // between negative and positive → still speaking
    expect(h.feed(0.25)).toBeNull() // == negative is NOT below → still speaking
    expect(h.feed(0.24)).toBe('end') // below negative → end
  })

  it('does not flap on a single noisy frame in the hysteresis band', () => {
    const h = new SpeechHysteresis(0.3, 0.25)
    h.feed(0.8) // start
    // A dip into the band and back out produces no transitions.
    expect(h.feed(0.27)).toBeNull()
    expect(h.feed(0.9)).toBeNull()
    expect(h.feed(0.28)).toBeNull()
  })

  it('re-triggers start after an end', () => {
    const h = new SpeechHysteresis(0.3, 0.25)
    expect(h.feed(0.5)).toBe('start')
    expect(h.feed(0.1)).toBe('end')
    expect(h.feed(0.5)).toBe('start')
  })

  it('reset() returns to the not-speaking state', () => {
    const h = new SpeechHysteresis()
    h.feed(0.9)
    h.reset()
    expect(h.feed(0.9)).toBe('start') // would be null if still speaking
  })
})

describe('Float32Reblocker', () => {
  it('emits fixed-size frames and carries the remainder', () => {
    const r = new Float32Reblocker(512)
    expect(r.push(new Int16Array(300))).toEqual([]) // not enough yet
    const out = r.push(new Int16Array(800)) // total 1100 → two 512 frames, 76 left
    expect(out.length).toBe(2)
    expect(out.every((f) => f.length === 512)).toBe(true)
    expect(r.push(new Int16Array(512 - 76))).toHaveLength(1) // completes the third
  })

  it('reblocks a 4096-chunk into exactly eight 512-frames', () => {
    const r = new Float32Reblocker(512)
    const out = r.push(new Int16Array(4096))
    expect(out.length).toBe(8)
  })

  it('normalizes int16 to [-1,1)', () => {
    const r = new Float32Reblocker(4)
    const out = r.push(new Int16Array([0, 16384, -32768, 32767]))
    expect(out).toHaveLength(1)
    expect(out[0][0]).toBeCloseTo(0, 6)
    expect(out[0][1]).toBeCloseTo(0.5, 6)
    expect(out[0][2]).toBeCloseTo(-1, 6)
    expect(out[0][3]).toBeCloseTo(0.99997, 4)
  })

  it('preserves sample order across chunk boundaries', () => {
    const r = new Float32Reblocker(4)
    r.push(new Int16Array([1, 2])) // buffered
    const out = r.push(new Int16Array([3, 4, 5, 6])) // total 6 → one frame [1,2,3,4], 2 left
    expect(out).toHaveLength(1)
    expect(Array.from(out[0]).map((v) => Math.round(v * 32768))).toEqual([1, 2, 3, 4])
  })

  it('grows its buffer for an oversized push without dropping samples', () => {
    const r = new Float32Reblocker(512)
    const out = r.push(new Int16Array(512 * 10)) // 10 frames in one push
    expect(out.length).toBe(10)
  })

  it('reset() discards the carried remainder', () => {
    const r = new Float32Reblocker(512)
    r.push(new Int16Array(300))
    r.reset()
    expect(r.push(new Int16Array(300))).toEqual([]) // 300 (not 600) → still short
  })
})
