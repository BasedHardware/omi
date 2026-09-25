// Recovery after a database wipe. The pixels are on disk either way; the
// question is whether anything can still find them.
//
// This is the reason each chunk record carries its capture timestamp. Without
// it a compacted frame would be exactly the case rebuildIndex.ts was written to
// prevent: intact bytes that nothing references, which the sweep then deletes.
import { describe, expect, it } from 'vitest'
import { encodeChunk } from './chunkFormat'
import { REBUILT_CHUNK_FRAME_INDEXED, selectChunkFramesToRebuild } from './chunkRebuild'

const PATH = '2026-08-17/1781329148845-1781329208845.omichunk'

function chunkOf(count: number, startTs = 1_781_329_148_845, width = 1280, height = 720) {
  return {
    relativePath: PATH,
    bytes: encodeChunk({
      codec: 'avc1.42001f',
      description: new Uint8Array([1, 100]),
      width,
      height,
      frames: Array.from({ length: count }, (_, i) => ({
        captureTsMs: startTs + i * 1000,
        isKeyFrame: i === 0,
        data: new Uint8Array([i + 1, 7])
      }))
    })
  }
}

describe('recovering rows from a chunk', () => {
  it('recovers one row per frame, at the right offset and time', () => {
    const targets = selectChunkFramesToRebuild(chunkOf(12), new Set())
    expect(targets).toHaveLength(12)
    expect(targets.map((t) => t.chunkOffset)).toEqual([...Array(12).keys()])
    expect(targets[0].ts).toBe(1_781_329_148_845)
    expect(targets[11].ts).toBe(1_781_329_148_845 + 11_000)
    expect(targets.every((t) => t.chunkPath === PATH)).toBe(true)
  })

  it('recovers the frame geometry the viewer needs', () => {
    // The OCR backfill only ever fills text, never width/height, so if these
    // were not recovered here nothing else would supply them.
    const targets = selectChunkFramesToRebuild(chunkOf(4, 1_000_000_000_000, 2560, 1440), new Set())
    expect(targets[0].width).toBe(2560)
    expect(targets[0].height).toBe(1440)
  })

  it('inserts nothing on a second run', () => {
    // Idempotence, as for the JPEG rebuild: a re-run must not duplicate rows.
    const chunk = chunkOf(10)
    const all = new Set(selectChunkFramesToRebuild(chunk, new Set()).map((t) => t.chunkOffset))
    expect(selectChunkFramesToRebuild(chunk, all)).toHaveLength(0)
  })

  it('finishes a partially recovered chunk rather than skipping it whole', () => {
    // Checked per offset, not per chunk: a run interrupted halfway must be able
    // to complete, which a chunk-level "already seen" check would prevent.
    const chunk = chunkOf(10)
    const targets = selectChunkFramesToRebuild(chunk, new Set([0, 1, 2, 3]))
    expect(targets.map((t) => t.chunkOffset)).toEqual([4, 5, 6, 7, 8, 9])
  })
})

describe('what it refuses to invent', () => {
  it('recovers nothing from a corrupt chunk', () => {
    // Rows for frames that may not decode would trade unreachable pixels for
    // broken ones, and the user cannot tell the difference from the UI.
    const chunk = { relativePath: PATH, bytes: new Uint8Array([1, 2, 3, 4, 5]) }
    expect(selectChunkFramesToRebuild(chunk, new Set())).toEqual([])
  })

  it('recovers nothing from a truncated chunk', () => {
    const full = chunkOf(10)
    const cut = { relativePath: PATH, bytes: full.bytes.subarray(0, full.bytes.byteLength - 5) }
    expect(selectChunkFramesToRebuild(cut, new Set())).toEqual([])
  })

  it('skips a record whose timestamp is not a real time', () => {
    const chunk = chunkOf(3)
    // Zero the second record's timestamp in place.
    const view = new DataView(chunk.bytes.buffer, chunk.bytes.byteOffset, chunk.bytes.byteLength)
    const recordAt = 24 + new TextEncoder().encode('avc1.42001f').byteLength + 2
    const secondRecordAt = recordAt + 16 + 2
    view.setBigInt64(secondRecordAt + 8, 0n, true)
    const targets = selectChunkFramesToRebuild(chunk, new Set())
    expect(targets.map((t) => t.chunkOffset)).toEqual([0, 2])
  })
})

describe('how recovered rows are marked', () => {
  it('marks them already indexed, unlike the JPEG rebuild', () => {
    // Not an oversight. The OCR backfill reads `image_path`, which is '' for a
    // chunk-backed row, and its missing-file handling marks the frame indexed
    // with empty text anyway — so indexed=0 reaches the identical end state
    // after spending a run of bounded OCR batches that cannot succeed.
    expect(REBUILT_CHUNK_FRAME_INDEXED).toBe(1)
  })
})
