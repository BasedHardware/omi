// Pure helpers that turn the Silero per-frame probability stream into the
// {speech:boolean} verdict transitions VadGate consumes. No onnx / Web Audio here
// so both pieces are exhaustively node-testable.

/** Two-threshold (hysteresis) speech detector over the model's P(speech) stream.
 *  Matches vad-web's positive/negative threshold design: once speaking, it takes a
 *  dip BELOW the (lower) negative threshold to end — a single noisy frame near the
 *  boundary can't flap the verdict. Emits only on transitions. */
export class SpeechHysteresis {
  private speaking = false

  constructor(
    private readonly positive = 0.3,
    private readonly negative = 0.25
  ) {}

  /** Feed one frame probability; returns the transition it caused, else null. */
  feed(prob: number): 'start' | 'end' | null {
    if (!this.speaking && prob >= this.positive) {
      this.speaking = true
      return 'start'
    }
    if (this.speaking && prob < this.negative) {
      this.speaking = false
      return 'end'
    }
    return null
  }

  reset(): void {
    this.speaking = false
  }
}

/** Re-blocks the variable Int16 pipeline chunks into fixed-size Float32 frames the
 *  model needs, normalizing int16 → [-1,1). Carries a partial frame across pushes. */
export class Float32Reblocker {
  private fifo: Float32Array
  private len = 0

  constructor(private readonly frameSize: number) {
    this.fifo = new Float32Array(frameSize * 4)
  }

  push(i16: Int16Array): Float32Array[] {
    this.ensure(this.len + i16.length)
    for (let k = 0; k < i16.length; k++) this.fifo[this.len + k] = i16[k] / 32768
    this.len += i16.length

    const out: Float32Array[] = []
    let off = 0
    while (this.len - off >= this.frameSize) {
      out.push(this.fifo.slice(off, off + this.frameSize))
      off += this.frameSize
    }
    if (off > 0) {
      this.fifo.copyWithin(0, off, this.len)
      this.len -= off
    }
    return out
  }

  reset(): void {
    this.len = 0
  }

  private ensure(n: number): void {
    if (n <= this.fifo.length) return
    const grown = new Float32Array(Math.max(this.fifo.length * 2, n))
    grown.set(this.fifo.subarray(0, this.len))
    this.fifo = grown
  }
}
