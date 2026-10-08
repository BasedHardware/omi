/**
 * The `.omichunk` container: the byte layout a compacted run of Rewind frames is
 * stored in.
 *
 * macOS stores the same thing as an MP4, because AVFoundation is a muxer-first
 * API — `AVAssetWriter` wants a container and hands you one. WebCodecs is the
 * opposite: `VideoEncoder` emits bare `EncodedVideoChunk`s and `VideoDecoder`
 * accepts them back, so an MP4 here would mean writing a muxer and a demuxer to
 * put bytes into a box structure and immediately take them out again. This
 * format is what is left when that round trip is removed.
 *
 * Two properties are worth the custom format:
 *
 *  - **Frame N is record N.** MP4 seeking is by presentation time, so reaching a
 *    frame means converting an index to a time and trusting the demuxer to land
 *    on the same frame. Here the index is the addressing scheme.
 *  - **A chunk is self-describing.** Each record carries the capture timestamp
 *    that its JPEG's filename used to carry. `rebuildIndex.ts` exists because
 *    Windows can re-create `rewind_frames` rows from `<day>/<ts>.jpg` after a
 *    database wipe; compaction would have silently taken that recovery away from
 *    every frame it packed, so the timestamps travel with the pixels.
 *
 * The format is versioned and read defensively: a truncated or corrupt chunk is
 * a throw at parse, never a partial frame list, because the compactor treats
 * "reads back exactly" as the precondition for deleting the JPEGs.
 *
 * Deliberately free of `Buffer`. This module is imported by BOTH the main
 * process (which writes and verifies chunks) and the renderer (which encodes
 * and decodes them), and `Buffer` does not exist in the renderer — an earlier
 * version used it and threw `ReferenceError: Buffer is not defined` the first
 * time a real encode ran. `Uint8Array` + `DataView` + `TextEncoder` are the
 * shared vocabulary, and a Node `Buffer` passed in is already a `Uint8Array`.
 */

export const CHUNK_MAGIC = 'OMICHNK\0'
export const CHUNK_FORMAT_VERSION = 1

/** Header: magic(8) version(2) codecLen(2) descLen(4) frameCount(4) width(2) height(2). */
const HEADER_BYTES = 24
/** Per record: flags(1) pad(3) byteLength(4) captureTsMs(8). */
const RECORD_HEADER_BYTES = 16

const KEY_FRAME_FLAG = 0x01

/**
 * A chunk holding more frames than this is refused at both ends. The compactor
 * never builds one (a 60s window at the fastest supported cadence is far below
 * it); the guard exists so a corrupt header cannot make the parser allocate
 * against a garbage count before it has read a single record.
 */
export const MAX_FRAMES_PER_CHUNK = 4096

/** Same reasoning for a single record's length: no real encoded frame is 64 MB. */
export const MAX_RECORD_BYTES = 64 * 1024 * 1024

export type ChunkFrame = {
  /** Wall-clock capture time, epoch ms — the identity `<ts>.jpg` used to carry. */
  captureTsMs: number
  isKeyFrame: boolean
  data: Uint8Array
}

export type ChunkContents = {
  /** WebCodecs codec string, e.g. `avc1.42001f`. */
  codec: string
  /** Decoder description (`avcC` for H.264); empty when the codec needs none. */
  description: Uint8Array
  width: number
  height: number
  frames: ChunkFrame[]
}

const UTF8_ENCODER = new TextEncoder()
const UTF8_DECODER = new TextDecoder('utf-8')

/** ASCII bytes compared without decoding, so the magic check allocates nothing. */
function matchesMagic(bytes: Uint8Array): boolean {
  for (let i = 0; i < CHUNK_MAGIC.length; i++) {
    if (bytes[i] !== CHUNK_MAGIC.charCodeAt(i)) return false
  }
  return true
}

/**
 * Serialize a chunk. Throws rather than emitting something unreadable: every
 * caller is about to treat these bytes as durable, and a chunk that cannot be
 * parsed back is worse than a failed compaction.
 */
export function encodeChunk(contents: ChunkContents): Uint8Array {
  if (contents.frames.length === 0) throw new Error('a chunk must hold at least one frame')
  if (contents.frames.length > MAX_FRAMES_PER_CHUNK) {
    throw new Error(`a chunk may hold at most ${MAX_FRAMES_PER_CHUNK} frames`)
  }
  if (!contents.frames[0].isKeyFrame) {
    // Nothing downstream can decode a chunk that opens on a delta frame: the
    // decoder has no reference picture to apply it to.
    throw new Error('the first frame of a chunk must be a key frame')
  }
  if (!Number.isInteger(contents.width) || contents.width <= 0 || contents.width > 0xffff) {
    throw new Error('chunk width must be a positive 16-bit integer')
  }
  if (!Number.isInteger(contents.height) || contents.height <= 0 || contents.height > 0xffff) {
    throw new Error('chunk height must be a positive 16-bit integer')
  }
  const codecUtf8 = UTF8_ENCODER.encode(contents.codec)
  const codecBytes = codecUtf8.byteLength
  if (codecBytes === 0 || codecBytes > 0xffff) throw new Error('chunk codec string is out of range')
  if (contents.description.byteLength > 0xffffffff) throw new Error('chunk description too large')

  let total = HEADER_BYTES + codecBytes + contents.description.byteLength
  for (const frame of contents.frames) {
    if (frame.data.byteLength === 0) throw new Error('a chunk frame must carry encoded bytes')
    if (frame.data.byteLength > MAX_RECORD_BYTES)
      throw new Error('chunk frame exceeds record limit')
    if (!Number.isSafeInteger(frame.captureTsMs) || frame.captureTsMs < 0) {
      throw new Error('chunk frame timestamp must be a non-negative safe integer')
    }
    total += RECORD_HEADER_BYTES + frame.data.byteLength
  }

  const out = new Uint8Array(total)
  const view = new DataView(out.buffer)
  let at = 0
  for (let i = 0; i < CHUNK_MAGIC.length; i++) out[at + i] = CHUNK_MAGIC.charCodeAt(i)
  at += 8
  view.setUint16(at, CHUNK_FORMAT_VERSION, true)
  at += 2
  view.setUint16(at, codecBytes, true)
  at += 2
  view.setUint32(at, contents.description.byteLength, true)
  at += 4
  view.setUint32(at, contents.frames.length, true)
  at += 4
  view.setUint16(at, contents.width, true)
  at += 2
  view.setUint16(at, contents.height, true)
  at += 2

  out.set(codecUtf8, at)
  at += codecBytes
  out.set(contents.description, at)
  at += contents.description.byteLength

  for (const frame of contents.frames) {
    view.setUint8(at, frame.isKeyFrame ? KEY_FRAME_FLAG : 0)
    at += 4 // flags byte + 3 reserved, already zero
    view.setUint32(at, frame.data.byteLength, true)
    at += 4
    // Epoch ms fits a double exactly for any real date; BigInt keeps the field
    // 64-bit on disk without forcing BigInt on every caller.
    view.setBigInt64(at, BigInt(frame.captureTsMs), true)
    at += 8
    out.set(frame.data, at)
    at += frame.data.byteLength
  }

  return out
}

export class ChunkFormatError extends Error {}

/**
 * Parse a chunk. Every length is validated against the remaining buffer before
 * it is used, so a truncated file raises instead of yielding a short frame list
 * that a caller could mistake for a complete one.
 */
export function decodeChunk(buffer: Uint8Array): ChunkContents {
  if (buffer.byteLength < HEADER_BYTES)
    throw new ChunkFormatError('chunk is shorter than its header')
  if (!matchesMagic(buffer)) throw new ChunkFormatError('not an omi chunk')
  const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength)

  const version = view.getUint16(8, true)
  if (version !== CHUNK_FORMAT_VERSION) {
    throw new ChunkFormatError(`unsupported chunk version ${version}`)
  }
  const codecBytes = view.getUint16(10, true)
  const descBytes = view.getUint32(12, true)
  const frameCount = view.getUint32(16, true)
  const width = view.getUint16(20, true)
  const height = view.getUint16(22, true)

  if (frameCount === 0) throw new ChunkFormatError('chunk declares no frames')
  if (frameCount > MAX_FRAMES_PER_CHUNK)
    throw new ChunkFormatError('chunk declares too many frames')
  if (width === 0 || height === 0) throw new ChunkFormatError('chunk declares an empty frame size')

  let at = HEADER_BYTES
  if (at + codecBytes + descBytes > buffer.byteLength) {
    throw new ChunkFormatError('chunk header runs past end of file')
  }
  const codec = UTF8_DECODER.decode(buffer.subarray(at, at + codecBytes))
  at += codecBytes
  const description = buffer.slice(at, at + descBytes)
  at += descBytes

  const frames: ChunkFrame[] = []
  for (let i = 0; i < frameCount; i++) {
    if (at + RECORD_HEADER_BYTES > buffer.byteLength) {
      throw new ChunkFormatError(`chunk truncated in the header of frame ${i}`)
    }
    const flags = view.getUint8(at)
    const byteLength = view.getUint32(at + 4, true)
    const captureTsMs = Number(view.getBigInt64(at + 8, true))
    at += RECORD_HEADER_BYTES

    if (byteLength === 0) throw new ChunkFormatError(`frame ${i} declares no bytes`)
    if (byteLength > MAX_RECORD_BYTES)
      throw new ChunkFormatError(`frame ${i} exceeds the record limit`)
    if (at + byteLength > buffer.byteLength) {
      throw new ChunkFormatError(`chunk truncated in the body of frame ${i}`)
    }
    frames.push({
      captureTsMs,
      isKeyFrame: (flags & KEY_FRAME_FLAG) !== 0,
      // `slice` copies, so a held frame does not keep the whole chunk alive.
      data: buffer.slice(at, at + byteLength)
    })
    at += byteLength
  }

  if (!frames[0].isKeyFrame) throw new ChunkFormatError('chunk does not open on a key frame')

  return { codec, description, width, height, frames }
}

/**
 * Read only what is needed to re-associate a chunk with the database: the
 * per-frame capture timestamps, in order.
 *
 * This is the path `rebuildIndex.ts` takes after a database wipe, where the
 * pixels are wanted but not yet needed. It walks the record headers and skips
 * every payload, so recovering a day of chunks does not pull a day of encoded
 * video through memory.
 */
export function readChunkTimestamps(buffer: Uint8Array): number[] {
  const contents = decodeChunkHeaderOnly(buffer)
  return contents.timestamps
}

export function decodeChunkHeaderOnly(buffer: Uint8Array): {
  codec: string
  width: number
  height: number
  timestamps: number[]
} {
  if (buffer.byteLength < HEADER_BYTES)
    throw new ChunkFormatError('chunk is shorter than its header')
  if (!matchesMagic(buffer)) throw new ChunkFormatError('not an omi chunk')
  const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength)
  const version = view.getUint16(8, true)
  if (version !== CHUNK_FORMAT_VERSION)
    throw new ChunkFormatError(`unsupported chunk version ${version}`)

  const codecBytes = view.getUint16(10, true)
  const descBytes = view.getUint32(12, true)
  const frameCount = view.getUint32(16, true)
  const width = view.getUint16(20, true)
  const height = view.getUint16(22, true)
  if (frameCount === 0 || frameCount > MAX_FRAMES_PER_CHUNK) {
    throw new ChunkFormatError('chunk declares an unusable frame count')
  }

  let at = HEADER_BYTES
  if (at + codecBytes + descBytes > buffer.byteLength) {
    throw new ChunkFormatError('chunk header runs past end of file')
  }
  const codec = UTF8_DECODER.decode(buffer.subarray(at, at + codecBytes))
  at += codecBytes + descBytes

  const timestamps: number[] = []
  for (let i = 0; i < frameCount; i++) {
    if (at + RECORD_HEADER_BYTES > buffer.byteLength) {
      throw new ChunkFormatError(`chunk truncated in the header of frame ${i}`)
    }
    const byteLength = view.getUint32(at + 4, true)
    timestamps.push(Number(view.getBigInt64(at + 8, true)))
    at += RECORD_HEADER_BYTES + byteLength
    if (at > buffer.byteLength)
      throw new ChunkFormatError(`chunk truncated in the body of frame ${i}`)
  }
  return { codec, width, height, timestamps }
}
