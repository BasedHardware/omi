import { describe, it, expect } from 'vitest'
import { StreamingResampler, PcmFramer } from './pcmWorkletCore'

const QUANTUM = 128 // AudioWorklet render-quantum size

function sine(samples: number, freq: number, rate: number, offset = 0): Float32Array {
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i++) out[i] = Math.sin((2 * Math.PI * freq * (i + offset)) / rate)
  return out
}

function dominantHz(f32: Float32Array, rate: number): number {
  let crossings = 0
  for (let i = 1; i < f32.length; i++) if (f32[i - 1] < 0 && f32[i] >= 0) crossings++
  return crossings / (f32.length / rate)
}

describe('StreamingResampler', () => {
  it('produces ~toRate/fromRate output samples across many quanta', () => {
    const r = new StreamingResampler(48000, 16000)
    const totalIn = QUANTUM * 100 // 12800 input samples
    let outLen = 0
    for (let off = 0; off < totalIn; off += QUANTUM) {
      outLen += r.process(sine(QUANTUM, 440, 48000, off)).length
    }
    // 12800 / 3 ≈ 4266.67; streaming keeps phase so we land within a sample or two.
    expect(outLen).toBeGreaterThanOrEqual(4265)
    expect(outLen).toBeLessThanOrEqual(4268)
  })

  it('keeps phase across quanta (no per-block reset): tone survives chunked resampling', () => {
    const r = new StreamingResampler(48000, 16000)
    const chunks: Float32Array[] = []
    const totalIn = 48000 // 1s
    for (let off = 0; off < totalIn; off += QUANTUM) {
      chunks.push(r.process(sine(Math.min(QUANTUM, totalIn - off), 440, 48000, off)))
    }
    let len = 0
    for (const c of chunks) len += c.length
    const merged = new Float32Array(len)
    let w = 0
    for (const c of chunks) {
      merged.set(c, w)
      w += c.length
    }
    expect(dominantHz(merged, 16000)).toBeCloseTo(440, -1)
  })

  it('is a passthrough-length identity when up/down cancel (rate equal handled by framer)', () => {
    const r = new StreamingResampler(16000, 16000) // step 1
    const out = r.process(sine(QUANTUM, 200, 16000))
    expect(out.length).toBe(QUANTUM)
  })

  // Faithful copy of the ORIGINAL allocating implementation (closure + growing
  // number[] + Float32Array.from). The zero-allocation rewrite must be bit-for-bit
  // identical to this, quantum for quantum, or the capture stream has drifted.
  function referenceResample(
    fromRate: number,
    toRate: number,
    quanta: Float32Array[]
  ): Float32Array[] {
    const step = fromRate / toRate
    let hist = 0
    let frac = 0
    return quanta.map((input) => {
      const n = input.length
      if (n === 0) return input
      const at = (i: number): number => (i <= 0 ? hist : input[i - 1])
      const out: number[] = []
      let p = frac
      while (p < n) {
        const i = Math.floor(p)
        const f = p - i
        out.push(at(i) * (1 - f) + at(i + 1) * f)
        p += step
      }
      hist = input[n - 1]
      frac = p - n
      return Float32Array.from(out)
    })
  }

  it('REGRESSION: zero-alloc process() is bit-identical to the original algorithm', () => {
    // A deterministic pseudo-random signal chunked into varied quanta, across the
    // rate pairs the capture path actually hits (down), plus an upsample edge case.
    let seed = 0x9e3779b9
    const rnd = (): number => {
      seed = (seed * 1664525 + 1013904223) >>> 0
      return (seed / 0xffffffff) * 2 - 1
    }
    for (const [from, to] of [
      [48000, 16000],
      [44100, 16000],
      [16000, 16000],
      [8000, 16000] // upsample: output longer than input (exercises scratch growth)
    ] as const) {
      const quanta: Float32Array[] = []
      // Mix full 128-sample quanta with the odd short/empty tail the framer can pass.
      for (const len of [128, 128, 128, 37, 0, 128, 91, 128, 128, 5]) {
        quanta.push(Float32Array.from({ length: len }, rnd))
      }
      const expected = referenceResample(from, to, quanta)
      const r = new StreamingResampler(from, to)
      quanta.forEach((q, k) => {
        const got = r.process(q)
        expect(got.length).toBe(expected[k].length)
        for (let j = 0; j < got.length; j++) {
          // Exact equality: same operations in the same order ⇒ same float bits.
          expect(Object.is(got[j], expected[k][j])).toBe(true)
        }
      })
    }
  })

  it('returns independently-owned buffers (scratch never aliases a prior return)', () => {
    const r = new StreamingResampler(48000, 16000)
    const first = r.process(sine(QUANTUM, 440, 48000, 0))
    const firstCopy = Float32Array.from(first)
    // Several more quanta reuse the internal scratch; the first return must be intact.
    for (let off = QUANTUM; off < QUANTUM * 20; off += QUANTUM) {
      r.process(sine(QUANTUM, 440, 48000, off))
    }
    expect(Array.from(first)).toEqual(Array.from(firstCopy))
  })
})

describe('PcmFramer', () => {
  it('emits exactly frameSamples-sized Int16 frames at the native rate (no resample)', () => {
    const framer = new PcmFramer({ inputRate: 16000, targetRate: 16000, frameSamples: 4096 })
    const frames: Int16Array[] = []
    // Feed 4096*2 samples in 128-sample quanta → exactly 2 frames.
    for (let i = 0; i < (4096 * 2) / QUANTUM; i++) {
      for (const f of framer.push(sine(QUANTUM, 300, 16000, i * QUANTUM))) frames.push(f)
    }
    expect(frames.length).toBe(2)
    expect(frames.every((f) => f.length === 4096)).toBe(true)
    expect(frames[0]).toBeInstanceOf(Int16Array)
  })

  it('buffers a partial frame until it completes', () => {
    const framer = new PcmFramer({ inputRate: 16000, targetRate: 16000, frameSamples: 4096 })
    // 4095 samples → no frame yet.
    let count = framer.push(new Float32Array(4095)).length
    expect(count).toBe(0)
    // one more sample completes it.
    count = framer.push(new Float32Array(1)).length
    expect(count).toBe(1)
  })

  it('resamples 48k → 16k and still emits exact 4096-sample frames', () => {
    const framer = new PcmFramer({ inputRate: 48000, targetRate: 16000, frameSamples: 4096 })
    const frames: Int16Array[] = []
    // 48000 in-samples (1s) → ~16000 out-samples → 3 full frames (+ remainder).
    for (let off = 0; off < 48000; off += QUANTUM) {
      for (const f of framer.push(sine(Math.min(QUANTUM, 48000 - off), 440, 48000, off)))
        frames.push(f)
    }
    expect(frames.length).toBe(3)
    expect(frames.every((f) => f.length === 4096)).toBe(true)
  })

  it('produces a non-silent frame from real signal (Int16 conversion wired)', () => {
    const framer = new PcmFramer({ inputRate: 16000, targetRate: 16000, frameSamples: 4096 })
    let frame: Int16Array | undefined
    for (let i = 0; i < 4096 / QUANTUM; i++) {
      const out = framer.push(
        sine(QUANTUM, 300, 16000, i * QUANTUM).map((s) => s * 0.9) as Float32Array
      )
      if (out.length) frame = out[0]
    }
    expect(frame).toBeDefined()
    expect(Math.max(...Array.from(frame!).map(Math.abs))).toBeGreaterThan(10000)
  })
})
