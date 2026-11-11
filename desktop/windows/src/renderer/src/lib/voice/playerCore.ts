// Pure jitter-buffered PCM player core (Phase 6). DOM-free so the math is
// exhaustively testable in node; the AudioWorklet processor (playerWorklet.ts)
// hosts one instance and calls pull() from process(), the renderer-side wrapper
// (pcmPlayer.ts) feeds enqueue()/clear().
//
// Semantics (Gemini Live 24kHz downlink, but rate-agnostic):
//  - enqueue() appends decoded Float32 samples.
//  - Playback does not START until `cushionSamples` are buffered (~150ms) so
//    network jitter doesn't cause immediate underruns; once started, samples
//    flow until the queue truly empties (a mid-stream dip plays what's left —
//    re-cushioning only re-arms after a full drain).
//  - clear() drops everything instantly (barge-in: the provider interrupted the
//    turn; stale audio must never keep playing over the user).
//  - pull() fills an output frame, zero-padding underruns, and reports 'drained'
//    exactly once per burst — the echo gate's release timer keys off that.

export type PullResult = {
  /** True if any real (non-padding) samples were written this frame. */
  wroteAudio: boolean
  /** True exactly once, on the frame where a playing burst ran out of samples. */
  drained: boolean
}

export class PlayerCore {
  private chunks: Float32Array[] = []
  private offset = 0 // read offset into chunks[0]
  private queued = 0
  private started = false // cushion reached; actively playing this burst

  constructor(private readonly cushionSamples: number) {}

  get queuedSamples(): number {
    return this.queued
  }

  get playing(): boolean {
    return this.started
  }

  enqueue(samples: Float32Array): void {
    if (samples.length === 0) return
    this.chunks.push(samples)
    this.queued += samples.length
    if (!this.started && this.queued >= this.cushionSamples) this.started = true
  }

  /** End-of-turn flush: the producer says no more audio is coming for this
   *  burst, so play whatever is queued even if it never reached the cushion —
   *  otherwise a sub-cushion tail would be withheld until the NEXT turn tops
   *  the buffer (stale audio at the start of the next reply) or lost. */
  flush(): void {
    if (!this.started && this.queued > 0) this.started = true
  }

  /** Drop all buffered audio and stop the current burst (barge-in). Returns
   *  true if audio was actually playing/buffered (callers may emit 'drained'). */
  clear(): boolean {
    const wasActive = this.started || this.queued > 0
    this.chunks = []
    this.offset = 0
    this.queued = 0
    this.started = false
    return wasActive
  }

  /** Fill `out` from the queue (zero-padding any shortfall). */
  pull(out: Float32Array): PullResult {
    if (!this.started) {
      out.fill(0)
      return { wroteAudio: false, drained: false }
    }
    let wrote = 0
    while (wrote < out.length && this.chunks.length > 0) {
      const head = this.chunks[0]
      const avail = head.length - this.offset
      const take = Math.min(avail, out.length - wrote)
      out.set(head.subarray(this.offset, this.offset + take), wrote)
      wrote += take
      this.offset += take
      if (this.offset >= head.length) {
        this.chunks.shift()
        this.offset = 0
      }
    }
    if (wrote < out.length) out.fill(0, wrote)
    this.queued -= wrote
    const drained = this.queued === 0
    if (drained) this.started = false // next burst re-cushions
    return { wroteAudio: wrote > 0, drained }
  }
}

// --- Playback level metering (the orb's speaking-pose amplitude tap) ---------

/** Post cadence in render quanta: 6 × 128 samples at 24kHz ≈ 32ms ≈ 31Hz —
 *  matches the orb's ~30Hz amplitude sampling, so a finer cadence would only
 *  burn IPC without smoother dots. */
export const LEVEL_POST_QUANTA = 6

/**
 * Aggregates per-quantum output peaks into throttled level posts so the orb's
 * speaking pose can animate with the reply's REAL speech dynamics. Pure and
 * worklet-free (the worklet stays thin — this is the node-tested math).
 *
 * The returned value is the orb's canonical amplitude unit: linear 0..1 peak of
 * the recent window (exactly what the mic lanes emit — hub pcmPeakLevel /
 * capture-window time-domain peak), so the adaptive mapper downstream needs no
 * special casing. Returns `null` when there is nothing to post: between
 * cadence windows, and while no real audio is flowing — except ONE trailing 0
 * when a burst ends (drain or barge-in clear) so the consumer sees the dots
 * come to rest instead of holding the last loud frame.
 */
export class PlaybackLevelMeter {
  private peak = 0
  private quanta = 0
  private audible = false

  /** Observe one pulled output frame. `wroteAudio` is PullResult.wroteAudio —
   *  zero-padded underrun/idle frames must not read as playback. */
  observe(frame: Float32Array, wroteAudio: boolean): number | null {
    if (!wroteAudio) {
      if (!this.audible) return null
      this.audible = false
      this.peak = 0
      this.quanta = 0
      return 0
    }
    this.audible = true
    for (let i = 0; i < frame.length; i++) {
      const a = Math.abs(frame[i])
      if (a > this.peak) this.peak = a
    }
    this.quanta += 1
    if (this.quanta < LEVEL_POST_QUANTA) return null
    const level = this.peak
    this.peak = 0
    this.quanta = 0
    return level
  }
}

/** 16-bit little-endian PCM bytes → Float32 [-1, 1). The Gemini downlink wire
 *  format (inlineData base64 → bytes → here). */
export function pcm16BytesToFloat32(bytes: Uint8Array): Float32Array {
  const samples = Math.floor(bytes.byteLength / 2)
  const view = new DataView(bytes.buffer, bytes.byteOffset, samples * 2)
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i++) out[i] = view.getInt16(i * 2, true) / 32768
  return out
}
