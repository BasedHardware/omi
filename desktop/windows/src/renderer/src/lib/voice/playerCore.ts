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

/** 16-bit little-endian PCM bytes → Float32 [-1, 1). The Gemini downlink wire
 *  format (inlineData base64 → bytes → here). */
export function pcm16BytesToFloat32(bytes: Uint8Array): Float32Array {
  const samples = Math.floor(bytes.byteLength / 2)
  const view = new DataView(bytes.buffer, bytes.byteOffset, samples * 2)
  const out = new Float32Array(samples)
  for (let i = 0; i < samples; i++) out[i] = view.getInt16(i * 2, true) / 32768
  return out
}
