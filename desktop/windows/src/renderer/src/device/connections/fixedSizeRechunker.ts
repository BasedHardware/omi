/**
 * Re-buffers variable-length input into exact fixed-size chunks; PLAUD audio
 * ships downstream in exact 80-byte chunks with the final partial flushed at
 * stream end (macOS PlaudDeviceConnection.swift).
 */

export class FixedSizeRechunker {
  private buffer = new Uint8Array(0)

  constructor(private readonly chunkSize: number) {}

  push(data: Uint8Array): Uint8Array[] {
    if (data.length > 0) {
      const merged = new Uint8Array(this.buffer.length + data.length)
      merged.set(this.buffer, 0)
      merged.set(data, this.buffer.length)
      this.buffer = merged
    }
    const chunks: Uint8Array[] = []
    while (this.buffer.length >= this.chunkSize) {
      chunks.push(this.buffer.slice(0, this.chunkSize))
      this.buffer = this.buffer.subarray(this.chunkSize)
    }
    return chunks
  }

  /** Returns the trailing partial chunk (or null) and resets. */
  flush(): Uint8Array | null {
    if (this.buffer.length === 0) return null
    const tail = this.buffer.slice()
    this.buffer = new Uint8Array(0)
    return tail
  }
}
