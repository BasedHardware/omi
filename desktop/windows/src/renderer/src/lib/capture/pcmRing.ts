// Fixed-capacity rolling Int16 buffer — the pre-roll ring, generalized out of
// lib/ptt/capture.ts (createGraph's `ring`/`ringSamples` + backfillFromRing) so
// PTT and the VAD pre-speech pad can share one implementation.
//
// Eviction matches the PTT ring exactly: a whole leading chunk is dropped only
// when doing so still leaves at least `capacity` samples retained, so the ring
// holds between `capacity` and `capacity + oldest-chunk` samples.

export class PcmRing {
  private chunks: Int16Array[] = []
  private samples = 0

  /** @param capacity retained-sample floor (e.g. PRE_ROLL_MS/1000 * 16000). */
  constructor(private readonly capacity: number) {}

  /** Number of samples currently retained. */
  get length(): number {
    return this.samples
  }

  push(chunk: Int16Array): void {
    if (chunk.length === 0) return
    this.chunks.push(chunk)
    this.samples += chunk.length
    while (this.chunks.length > 0 && this.samples - this.chunks[0].length >= this.capacity) {
      this.samples -= this.chunks.shift()!.length
    }
  }

  /** Concatenate and REMOVE the most-recent `sampleCount` samples (default: all
   *  retained), trimmed to the sample so nothing older than the window leaks —
   *  mirrors backfillFromRing's trailing-window trim. Empties the ring. */
  drain(sampleCount = this.samples): Int16Array {
    const want = Math.min(Math.max(0, Math.round(sampleCount)), this.samples)
    const out = new Int16Array(want)
    if (want > 0) {
      let remaining = want
      let writeEnd = want
      for (let i = this.chunks.length - 1; i >= 0 && remaining > 0; i--) {
        const chunk = this.chunks[i]
        const take = Math.min(chunk.length, remaining)
        const slice = take === chunk.length ? chunk : chunk.subarray(chunk.length - take)
        out.set(slice, writeEnd - take)
        writeEnd -= take
        remaining -= take
      }
    }
    this.clear()
    return out
  }

  clear(): void {
    this.chunks = []
    this.samples = 0
  }
}
