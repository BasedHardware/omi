// The container is the boundary the compactor trusts when it decides to delete
// a JPEG, so the properties pinned here are the ones that make that decision
// safe: an exact round trip, and a hard failure on anything less than exact.
import { describe, expect, it } from 'vitest'
import {
  CHUNK_FORMAT_VERSION,
  MAX_FRAMES_PER_CHUNK,
  decodeChunk,
  decodeChunkHeaderOnly,
  encodeChunk,
  readChunkTimestamps,
  type ChunkContents
} from './chunkFormat'

function bytes(...values: number[]): Uint8Array {
  return new Uint8Array(values)
}

/** DataView over a chunk, for the cases that corrupt one specific field. */
function fieldsOf(chunk: Uint8Array): DataView {
  return new DataView(chunk.buffer, chunk.byteOffset, chunk.byteLength)
}

/** Byte offset of frame 0's record header: header + codec + description. */
function firstRecordAt(codec = 'avc1.42001f', descBytes = 6): number {
  return 24 + new TextEncoder().encode(codec).byteLength + descBytes
}

function sample(overrides: Partial<ChunkContents> = {}): ChunkContents {
  return {
    codec: 'avc1.42001f',
    description: bytes(1, 100, 0, 31, 255, 225),
    width: 1280,
    height: 720,
    frames: [
      { captureTsMs: 1_781_329_148_845, isKeyFrame: true, data: bytes(9, 8, 7, 6, 5) },
      { captureTsMs: 1_781_329_149_899, isKeyFrame: false, data: bytes(4, 3) },
      { captureTsMs: 1_781_329_150_950, isKeyFrame: false, data: bytes(2, 1, 0, 42) }
    ],
    ...overrides
  }
}

describe('chunk container round trip', () => {
  it('returns every field byte-for-byte', () => {
    const original = sample()
    const decoded = decodeChunk(encodeChunk(original))

    expect(decoded.codec).toBe(original.codec)
    expect([...decoded.description]).toEqual([...original.description])
    expect(decoded.width).toBe(1280)
    expect(decoded.height).toBe(720)
    expect(decoded.frames).toHaveLength(3)
    decoded.frames.forEach((frame, i) => {
      expect(frame.captureTsMs).toBe(original.frames[i].captureTsMs)
      expect(frame.isKeyFrame).toBe(original.frames[i].isKeyFrame)
      expect([...frame.data]).toEqual([...original.frames[i].data])
    })
  })

  it('keeps millisecond timestamps exact past 2^32', () => {
    // The field is 64-bit precisely so epoch ms does not wrap. A 32-bit field
    // would have silently truncated every timestamp after 1970-02-19.
    const ts = 1_781_329_148_845
    expect(ts).toBeGreaterThan(2 ** 32)
    const decoded = decodeChunk(encodeChunk(sample()))
    expect(decoded.frames[0].captureTsMs).toBe(ts)
  })

  it('does not alias the input buffer', () => {
    // A decoded frame that pointed into the file buffer would keep the whole
    // chunk alive for as long as one frame was held.
    const buffer = encodeChunk(sample())
    const decoded = decodeChunk(buffer)
    buffer.fill(0)
    expect([...decoded.frames[0].data]).toEqual([9, 8, 7, 6, 5])
  })

  it('handles a codec that needs no description', () => {
    const decoded = decodeChunk(encodeChunk(sample({ codec: 'vp8', description: bytes() })))
    expect(decoded.codec).toBe('vp8')
    expect(decoded.description).toHaveLength(0)
    expect(decoded.frames).toHaveLength(3)
  })
})

describe('what encoding refuses to produce', () => {
  it('refuses a chunk that opens on a delta frame', () => {
    // Nothing can decode it: there is no reference picture for frame 0.
    const frames = sample().frames.map((f) => ({ ...f, isKeyFrame: false }))
    expect(() => encodeChunk(sample({ frames }))).toThrow(/key frame/)
  })

  it('refuses an empty chunk', () => {
    expect(() => encodeChunk(sample({ frames: [] }))).toThrow(/at least one frame/)
  })

  it('refuses a frame carrying no bytes', () => {
    const frames = [{ captureTsMs: 1, isKeyFrame: true, data: bytes() }]
    expect(() => encodeChunk(sample({ frames }))).toThrow(/encoded bytes/)
  })

  it('refuses a zero or oversized frame geometry', () => {
    expect(() => encodeChunk(sample({ width: 0 }))).toThrow(/width/)
    expect(() => encodeChunk(sample({ height: 70_000 }))).toThrow(/height/)
  })

  it('refuses a negative timestamp', () => {
    const frames = [{ captureTsMs: -1, isKeyFrame: true, data: bytes(1) }]
    expect(() => encodeChunk(sample({ frames }))).toThrow(/non-negative/)
  })
})

describe('what decoding refuses to accept', () => {
  it('rejects a file that is not a chunk, on the magic bytes', () => {
    // Asserting the MESSAGE, not just the error type. Arbitrary bytes also fail
    // the version check a few lines later, so a type-only assertion passed even
    // with the magic check deleted — it was proving the wrong guard.
    expect(() => decodeChunk(new TextEncoder().encode('this is a jpeg, honestly'))).toThrow(
      /not an omi chunk/
    )
  })

  it('rejects a file whose bytes would otherwise pass the version check', () => {
    // The sharper case: a payload carrying a valid-looking version field at
    // offset 8, so only the magic can reject it.
    const impostor = encodeChunk(sample())
    impostor.set(new TextEncoder().encode('NOTAOMI\0'), 0)
    expect(() => decodeChunk(impostor)).toThrow(/not an omi chunk/)
    expect(() => decodeChunkHeaderOnly(impostor)).toThrow(/not an omi chunk/)
  })

  it('rejects a future format version', () => {
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint16(8, CHUNK_FORMAT_VERSION + 1, true)
    expect(() => decodeChunk(buffer)).toThrow(/unsupported chunk version/)
  })

  it('rejects a chunk truncated inside a frame body', () => {
    // The property that matters: it throws rather than returning the frames it
    // managed to read, which a caller could mistake for the whole chunk.
    const buffer = encodeChunk(sample())
    expect(() => decodeChunk(buffer.subarray(0, buffer.byteLength - 2))).toThrow(/truncated/)
  })

  it('rejects a chunk truncated inside a record header', () => {
    const buffer = encodeChunk(sample())
    expect(() => decodeChunk(buffer.subarray(0, buffer.byteLength - 6))).toThrow(/truncated/)
  })

  it('rejects a header whose declared frame count is absurd', () => {
    // Without the ceiling this allocates against a garbage count before a
    // single record has been read.
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint32(16, MAX_FRAMES_PER_CHUNK + 1, true)
    expect(() => decodeChunk(buffer)).toThrow(/too many frames/)
  })

  it('rejects a header whose declared record length runs past the file', () => {
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint32(firstRecordAt() + 4, 0xff_ff_ff, true)
    expect(() => decodeChunk(buffer)).toThrow(/truncated/)
  })

  it('rejects a chunk whose first frame lost its key flag', () => {
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint8(firstRecordAt(), 0)
    expect(() => decodeChunk(buffer)).toThrow(/key frame/)
  })

  it('rejects a chunk declaring no frames', () => {
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint32(16, 0, true)
    expect(() => decodeChunk(buffer)).toThrow(/declares no frames/)
  })

  it('rejects a chunk declaring an empty frame size', () => {
    // A zero-sized video track cannot be configured on a decoder, so this would
    // surface as an opaque WebCodecs failure at read time instead of here.
    const zeroWidth = encodeChunk(sample())
    fieldsOf(zeroWidth).setUint16(20, 0, true)
    expect(() => decodeChunk(zeroWidth)).toThrow(/empty frame size/)

    const zeroHeight = encodeChunk(sample())
    fieldsOf(zeroHeight).setUint16(22, 0, true)
    expect(() => decodeChunk(zeroHeight)).toThrow(/empty frame size/)
  })

  it('rejects a header whose codec and description run past the file', () => {
    // Without this the codec string and decoder description would be read from
    // whatever bytes happened to follow, and the record walk would start at a
    // bogus offset.
    const buffer = encodeChunk(sample())
    fieldsOf(buffer).setUint32(12, 0xff_ff, true) // description length
    expect(() => decodeChunk(buffer)).toThrow(/runs past end of file/)
  })
})

describe('header-only scan', () => {
  it('reads every timestamp without touching a payload', () => {
    const original = sample()
    expect(readChunkTimestamps(encodeChunk(original))).toEqual(
      original.frames.map((f) => f.captureTsMs)
    )
  })

  it('reports geometry and codec for recovery', () => {
    const header = decodeChunkHeaderOnly(encodeChunk(sample()))
    expect(header.codec).toBe('avc1.42001f')
    expect(header.width).toBe(1280)
    expect(header.height).toBe(720)
    expect(header.timestamps).toHaveLength(3)
  })

  it('refuses a truncated chunk rather than reporting a short frame list', () => {
    // Recovery uses this to re-create database rows. A short list here would
    // silently drop frames that are actually still in the file.
    const buffer = encodeChunk(sample())
    expect(() => readChunkTimestamps(buffer.subarray(0, buffer.byteLength - 3))).toThrow(
      /truncated/
    )
  })

  it('refuses a header declaring an unusable frame count', () => {
    // The scan builds a timestamp array from this number, so it needs the same
    // ceiling the full parse has rather than trusting the file.
    const tooMany = encodeChunk(sample())
    fieldsOf(tooMany).setUint32(16, MAX_FRAMES_PER_CHUNK + 1, true)
    expect(() => readChunkTimestamps(tooMany)).toThrow(/unusable frame count/)

    const none = encodeChunk(sample())
    fieldsOf(none).setUint32(16, 0, true)
    expect(() => readChunkTimestamps(none)).toThrow(/unusable frame count/)
  })
})
