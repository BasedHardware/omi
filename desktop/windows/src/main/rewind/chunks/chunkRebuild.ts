/**
 * Re-creating `rewind_frames` rows from chunk files after a database wipe.
 *
 * The chunk half of `rebuildIndex.ts`, and the reason each chunk record carries
 * its capture timestamp. Windows can recover JPEG-backed frames because the
 * filename *is* the timestamp (`<day>/<ts>.jpg`); without this, compaction would
 * have quietly taken that ability away from every frame it packed — the pixels
 * would still be on disk, intact and unreachable, and the orphan sweep would
 * eventually delete them.
 *
 * The same shape as its JPEG sibling: only INSERTs, never deletes, idempotent,
 * fail-open per file, and it reads only the record headers rather than pulling a
 * day of encoded video through memory.
 */

import { decodeChunkHeaderOnly } from './chunkFormat'

export type ChunkRebuildTarget = {
  chunkPath: string
  chunkOffset: number
  ts: number
  width: number
  height: number
}

export type ChunkOnDisk = {
  relativePath: string
  bytes: Uint8Array
}

/**
 * Rows that should exist for a chunk but do not.
 *
 * Pure: the caller supplies the chunk bytes and the offsets already present, so
 * the selection can be tested without a filesystem or a database.
 *
 * `known` is the set of `chunk_offset` values the database already has for this
 * chunk. Skipping them is what makes a re-run insert nothing, and it is checked
 * per offset rather than per chunk so a partially-recovered chunk finishes
 * rather than being skipped whole.
 */
export function selectChunkFramesToRebuild(
  chunk: ChunkOnDisk,
  known: ReadonlySet<number>
): ChunkRebuildTarget[] {
  let header
  try {
    header = decodeChunkHeaderOnly(chunk.bytes)
  } catch {
    // A corrupt or truncated chunk yields no rows. Inventing rows for frames
    // that may not decode would trade unreachable pixels for broken ones.
    return []
  }
  const targets: ChunkRebuildTarget[] = []
  header.timestamps.forEach((ts, offset) => {
    if (known.has(offset)) return
    if (!Number.isSafeInteger(ts) || ts <= 0) return
    targets.push({
      chunkPath: chunk.relativePath,
      chunkOffset: offset,
      ts,
      width: header.width,
      height: header.height
    })
  })
  return targets
}

/**
 * Rebuilt chunk rows are inserted as already-indexed, which is the opposite of
 * what `rebuildIndex.ts` does for JPEGs, and the difference is not an oversight.
 *
 * A rebuilt JPEG row is marked `indexed = 0` because the OCR backfill really can
 * re-read the file and recover its text. A chunk-backed row cannot: the backfill
 * reads `image_path`, which is `''` here, and its handling for a missing file is
 * to mark the frame indexed with empty text so it stops retrying
 * (`ocrService.ts`). So `indexed = 0` and `indexed = 1` reach the identical end
 * state — empty text — and the only difference is whether the app first spends a
 * run of bounded OCR batches discovering that, which on a large recovery is many
 * passes that cannot succeed.
 *
 * What is genuinely lost is the OCR text, and it is lost because it lived only in
 * the wiped database; it was never written into a chunk. The pixels come back,
 * and they are browsable. Making these frames searchable again would mean
 * teaching OCR to decode chunks, which needs a renderer and is its own change.
 */
export const REBUILT_CHUNK_FRAME_INDEXED = 1
