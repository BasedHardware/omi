/**
 * ADTS AAC frame extraction for Bee audio — port of the buffering logic in
 * macOS Connections/BeeDeviceConnection.swift. One notification can complete
 * several frames, and all of them must drain immediately: returning only the
 * first shifted audio roughly a frame (~64 ms) late per notification.
 */

const ADTS_MIN_FRAME_LENGTH = 7

export class AdtsFrameExtractor {
  private buffer = new Uint8Array(0)

  get bufferedByteCount(): number {
    return this.buffer.length
  }

  clear(): void {
    this.buffer = new Uint8Array(0)
  }

  /** Appends payload bytes and drains every complete ADTS frame. */
  push(payload: Uint8Array): Uint8Array[] {
    if (payload.length > 0) {
      const merged = new Uint8Array(this.buffer.length + payload.length)
      merged.set(this.buffer, 0)
      merged.set(payload, this.buffer.length)
      this.buffer = merged
    }
    const frames: Uint8Array[] = []
    for (;;) {
      const frame = this.nextFrame()
      if (frame === null) break
      frames.push(frame)
    }
    return frames
  }

  private nextFrame(): Uint8Array | null {
    for (;;) {
      // Drop non-sync leading bytes one at a time (syncword FF Fx).
      while (
        this.buffer.length >= 2 &&
        !(this.buffer[0] === 0xff && (this.buffer[1] & 0xf0) === 0xf0)
      ) {
        this.buffer = this.buffer.subarray(1)
      }
      if (this.buffer.length < 6) return null

      const frameLength =
        ((this.buffer[3] & 0x03) << 11) | (this.buffer[4] << 3) | ((this.buffer[5] & 0xe0) >> 5)
      if (frameLength < ADTS_MIN_FRAME_LENGTH) {
        // False sync: a real header can never describe a frame shorter than
        // its own header. Advancing one byte guards both permanent silence
        // and unbounded buffering.
        this.buffer = this.buffer.subarray(1)
        continue
      }
      if (this.buffer.length < frameLength) return null
      const frame = this.buffer.slice(0, frameLength)
      this.buffer = this.buffer.subarray(frameLength)
      return frame
    }
  }
}
