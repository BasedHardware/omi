// Pure PCM primitives shared by the AudioWorklet capture path and its unit tests.
// No Web Audio / DOM globals here so the logic is node-testable in isolation.

/** Convert a Web Audio Float32 buffer to 16-bit little-endian PCM. BYTE-IDENTICAL
 *  to lib/audio.ts floatTo16BitPCM — the asymmetric scaling (0x8000 negative /
 *  0x7fff positive) matches the int16 range exactly. Keep the two in lockstep or
 *  the worklet lane drifts audibly from the ScriptProcessor lane. */
export function floatTo16BitPCM(f32: Float32Array): Int16Array {
  const i16 = new Int16Array(f32.length)
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]))
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return i16
}

/** One-shot linear-interpolation resampler: reinterpret `f32` sampled at
 *  `fromRate` as `toRate`. Output length is round(len·toRate/fromRate). Used for
 *  whole buffers (tests, offline); the streaming capture path uses
 *  StreamingResampler in pcmWorkletCore.ts, which keeps phase across quanta. */
export function linearResample(f32: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate || f32.length === 0) return f32
  const ratio = fromRate / toRate // input samples advanced per output sample
  const outLen = Math.round(f32.length / ratio)
  const out = new Float32Array(outLen)
  const last = f32.length - 1
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio
    const i0 = Math.floor(pos)
    const i1 = i0 < last ? i0 + 1 : last
    const frac = pos - i0
    out[i] = f32[i0] * (1 - frac) + f32[i1] * frac
  }
  return out
}
