// The AudioWorklet processor's logic, kept free of the AudioWorkletProcessor /
// registerProcessor globals so it is unit-testable under node. pcmWorklet.ts is a
// thin shell that feeds render quanta into a PcmFramer and posts the frames back.

import { floatTo16BitPCM } from './pcmCore'

export type PcmWorkletOptions = {
  /** Hardware/context sample rate feeding process() (ctx.sampleRate). */
  inputRate: number
  /** Rate the backend expects (16000). */
  targetRate: number
  /** Samples per emitted Int16 frame (4096 — preserves the ScriptProcessor
   *  cadence the PTT ring and PCM_PENDING_MAX_BYTES budgets were tuned against). */
  frameSamples: number
}

/** Streaming linear resampler that keeps fractional phase across calls, so
 *  chunking the input into 128-sample render quanta produces the same stream as
 *  resampling the whole signal at once (no per-quantum boundary reset). */
export class StreamingResampler {
  private readonly step: number // input samples advanced per output sample
  private hist = 0 // last input sample of the previous quantum (virtual index 0)
  private frac = 0 // fractional read position into the current virtual buffer

  constructor(fromRate: number, toRate: number) {
    this.step = fromRate / toRate
  }

  /** Resample one quantum. Virtual buffer V = [hist, ...input]; we read at
   *  positions frac, frac+step, … up to the last interpolatable point, then carry
   *  the leftover phase (and the final input sample) into the next call. */
  process(input: Float32Array): Float32Array {
    const n = input.length
    if (n === 0) return input
    const step = this.step
    const at = (i: number): number => (i <= 0 ? this.hist : input[i - 1])
    const out: number[] = []
    let p = this.frac
    while (p < n) {
      const i = Math.floor(p)
      const f = p - i
      out.push(at(i) * (1 - f) + at(i + 1) * f)
      p += step
    }
    this.hist = input[n - 1]
    this.frac = p - n // shift origin: next virtual index 0 == current input[n-1]
    return Float32Array.from(out)
  }
}

/** Resamples (only when inputRate ≠ targetRate) and re-blocks the stream into
 *  fixed frameSamples Int16 frames. Exact frame sizes — the resample block size is
 *  decoupled from the emit size via an output FIFO — so cadence never drifts. */
export class PcmFramer {
  private readonly resampler: StreamingResampler | null
  private readonly frameSamples: number
  private fifo: Float32Array
  private fifoLen = 0

  constructor(opts: PcmWorkletOptions) {
    this.frameSamples = opts.frameSamples
    this.resampler =
      opts.inputRate === opts.targetRate
        ? null
        : new StreamingResampler(opts.inputRate, opts.targetRate)
    this.fifo = new Float32Array(opts.frameSamples * 4)
  }

  /** Push one render quantum; return every complete Int16 frame it completed. */
  push(quantum: Float32Array): Int16Array[] {
    const samples = this.resampler ? this.resampler.process(quantum) : quantum
    this.append(samples)
    const frames: Int16Array[] = []
    while (this.fifoLen >= this.frameSamples) {
      frames.push(floatTo16BitPCM(this.fifo.subarray(0, this.frameSamples)))
      this.fifo.copyWithin(0, this.frameSamples, this.fifoLen)
      this.fifoLen -= this.frameSamples
    }
    return frames
  }

  private append(s: Float32Array): void {
    if (this.fifoLen + s.length > this.fifo.length) {
      const grown = new Float32Array(Math.max(this.fifo.length * 2, this.fifoLen + s.length))
      grown.set(this.fifo.subarray(0, this.fifoLen))
      this.fifo = grown
    }
    this.fifo.set(s, this.fifoLen)
    this.fifoLen += s.length
  }
}
