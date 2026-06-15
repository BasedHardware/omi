// Framing for the win-ocr-helper stdio protocol.
// Request : [uint32 LE length][1 byte opcode][payload]
// Response: [uint32 LE length][UTF-8 JSON]

export const OP_OCR = 1
export const OP_WINDOW = 2

/** Build a length-prefixed, opcode-tagged request frame. */
export function encodeRequest(opcode: number, payload: Buffer): Buffer {
  const header = Buffer.alloc(4)
  header.writeUInt32LE(payload.length + 1, 0)
  return Buffer.concat([header, Buffer.from([opcode]), payload])
}

/** Streaming decoder for length-prefixed JSON response frames. Buffers partial
 * chunks and invokes `onFrame(jsonString)` once per complete frame. */
export class FrameDecoder {
  private buf = Buffer.alloc(0)
  constructor(private readonly onFrame: (json: string) => void) {}

  push(chunk: Buffer): void {
    this.buf = Buffer.concat([this.buf, chunk])
    for (;;) {
      if (this.buf.length < 4) return
      const len = this.buf.readUInt32LE(0)
      if (this.buf.length < 4 + len) return
      const json = this.buf.subarray(4, 4 + len).toString('utf8')
      this.buf = this.buf.subarray(4 + len)
      this.onFrame(json)
    }
  }
}
