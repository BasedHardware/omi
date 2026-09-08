import { describe, it, expect } from 'vitest'
import { floatTo16BitPCM, linearResample } from './pcmCore'
import { floatTo16BitPCM as canonicalFloatTo16BitPCM } from '../audio'

const SR = 16000

describe('floatTo16BitPCM', () => {
  it('is byte-identical to the canonical lib/audio.ts implementation', () => {
    // Dense sweep across [-1.2, 1.2] to hit both scaling branches + clamping.
    const n = 5000
    const f = new Float32Array(n)
    for (let i = 0; i < n; i++) f[i] = (i / n) * 2.4 - 1.2
    const a = floatTo16BitPCM(f)
    const b = canonicalFloatTo16BitPCM(f)
    expect(Array.from(a)).toEqual(Array.from(b))
  })

  it('matches the canonical output on edge samples (±1, clipping, -0)', () => {
    const edges = new Float32Array([-1, 1, -1.5, 1.5, -0, 0, 0.5, -0.5, 1 / 0x7fff, -1 / 0x8000])
    expect(Array.from(floatTo16BitPCM(edges))).toEqual(Array.from(canonicalFloatTo16BitPCM(edges)))
  })

  it('applies the asymmetric int16 scaling at the rails', () => {
    const out = floatTo16BitPCM(new Float32Array([1, -1, 2, -2]))
    expect(out[0]).toBe(32767) // +1 * 0x7fff
    expect(out[1]).toBe(-32768) // -1 * 0x8000
    expect(out[2]).toBe(32767) // clamped +1
    expect(out[3]).toBe(-32768) // clamped -1
  })
})

/** Dominant frequency (Hz) via a coarse zero-crossing count — enough to prove a
 *  resampled sine kept its pitch without pulling in an FFT dependency. */
function dominantHz(f32: Float32Array, rate: number): number {
  let crossings = 0
  for (let i = 1; i < f32.length; i++) {
    if (f32[i - 1] < 0 && f32[i] >= 0) crossings++
  }
  const seconds = f32.length / rate
  return crossings / seconds
}

function sine(samples: number, freq: number, rate: number): Float32Array {
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i++) out[i] = Math.sin((2 * Math.PI * freq * i) / rate)
  return out
}

describe('linearResample', () => {
  it('returns the input untouched when rates match', () => {
    const f = sine(1000, 440, SR)
    expect(linearResample(f, SR, SR)).toBe(f)
  })

  it('downsamples 48k → 16k with the expected length', () => {
    const f = sine(4800, 440, 48000)
    const out = linearResample(f, 48000, 16000)
    expect(out.length).toBe(1600) // 4800 * 16000/48000
  })

  it('upsamples 8k → 16k with the expected length', () => {
    const f = sine(800, 300, 8000)
    const out = linearResample(f, 8000, 16000)
    expect(out.length).toBe(1600)
  })

  it('preserves the tone frequency across a 48k → 16k downsample', () => {
    const f = sine(48000, 440, 48000) // 1s
    const out = linearResample(f, 48000, 16000)
    expect(dominantHz(out, 16000)).toBeCloseTo(440, -1) // within ~10 Hz
  })

  it('handles an empty buffer', () => {
    expect(linearResample(new Float32Array(0), 48000, 16000).length).toBe(0)
  })
})
