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

// Response frames carry small JSON objects (OCR text, window info). A declared
// length far beyond that means the stream has desynced — a corrupt prefix, or
// leftover bytes from a recycled helper. Without a ceiling the decoder keeps
// concatenating every later chunk waiting for bytes that never arrive, so the
// buffer grows without bound in the Electron main process. Cap it and signal a
// protocol error so the supervisor recycles the helper instead of stalling.
const MAX_FRAME_BYTES = 64 * 1024 * 1024

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
      if (len > MAX_FRAME_BYTES) {
        // Drop the poisoned buffer before throwing so a later chunk (e.g. buffered
        // stdout from a dying child) cannot re-concatenate onto it and re-throw.
        this.buf = Buffer.alloc(0)
        throw new Error(`frame too large: ${len} bytes (max ${MAX_FRAME_BYTES})`)
      }
      if (this.buf.length < 4 + len) return
      const json = this.buf.subarray(4, 4 + len).toString('utf8')
      this.buf = this.buf.subarray(4 + len)
      this.onFrame(json)
    }
  }
}
