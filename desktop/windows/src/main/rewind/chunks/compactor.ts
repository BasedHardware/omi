/**
 * The pass that replaces a run of JPEGs with one chunk.
 *
 * The ordering below is the entire safety argument, so it is worth stating
 * plainly: **the chunk is durable and has been read back before a single
 * database row is touched, and a row is touched before its JPEG is deleted.**
 * Every prefix of that sequence is a safe place to crash.
 *
 *   write chunk -> read it back and verify -> claim frame -> delete its JPEG
 *
 *   - crash after write:  an unreferenced chunk file. The sweep collects it.
 *   - crash after verify: same.
 *   - crash mid-claim:    claimed frames read from a chunk that provably holds
 *                         them; unclaimed frames still have their JPEGs. The
 *                         chunk holds a superset of what points into it, which
 *                         is harmless.
 *   - crash after claim, before delete: an orphaned JPEG. The existing orphan
 *                         sweep collects it.
 *
 * This is the part that differs most from macOS, and the difference is the
 * point. `VideoChunkEncoder` encodes live, as frames arrive, so its database
 * rows necessarily exist while the chunk is still being written — which is why
 * it needs a sidecar journal of abandoned writers, a quarantine table, and a
 * generation/reservation ownership model to keep a stale finaliser from
 * clearing a newer writer's state. Compacting after the fact makes almost all
 * of that unnecessary: nothing references a chunk until it is finished. What is
 * kept from that design is the tombstone, because a chunk can still be found
 * corrupt at *read* time long after it was written, and something has to stop
 * the UI retrying it forever.
 */

import { ChunkFormatError, decodeChunk } from './chunkFormat'
import { chunkRelativePath } from './chunkPaths'
import {
  planChunks,
  plannedJpegBytes,
  type CompactableFrame,
  type PlannedChunk
} from './compactionPlan'

/** Frames considered per pass. One pass is roughly one chunk's worth of work. */
export const COMPACTION_BATCH_FRAMES = 600

export type CompactorDeps = {
  nowMs: () => number
  listCompactable: (olderThanMs: number, limit: number) => CompactableFrame[]
  readJpeg: (absolutePath: string) => Promise<Uint8Array>
  /** Encode a run into chunk bytes. Brokered to a renderer; may reject. */
  encode: (input: {
    width: number
    height: number
    frames: { captureTsMs: number; jpeg: Uint8Array }[]
  }) => Promise<Uint8Array>
  writeChunk: (relativePath: string, bytes: Uint8Array) => Promise<void>
  readChunk: (relativePath: string) => Promise<Uint8Array>
  removeChunk: (relativePath: string) => Promise<void>
  claimFrame: (id: number, relativePath: string, offset: number) => boolean
  deleteJpeg: (absolutePath: string) => Promise<void>
  log: (message: string) => void
}

export type CompactionResult = {
  chunksWritten: number
  framesCompacted: number
  bytesReclaimed: number
  /** Runs that were planned but not written, with why. */
  skipped: { chunk: string; reason: string }[]
}

/**
 * Read every source JPEG for a planned chunk.
 *
 * All-or-nothing: a run with a missing file is abandoned rather than compacted
 * without it, because dropping a frame here would renumber every offset after
 * it while the database still expects the original positions.
 */
async function loadSources(
  chunk: PlannedChunk,
  deps: CompactorDeps
): Promise<{ frames: { captureTsMs: number; jpeg: Uint8Array }[]; bytes: number } | null> {
  const frames: { captureTsMs: number; jpeg: Uint8Array }[] = []
  let bytes = 0
  for (const frame of chunk.frames) {
    let jpeg: Uint8Array
    try {
      jpeg = await deps.readJpeg(frame.imagePath)
    } catch {
      return null
    }
    if (jpeg.byteLength === 0) return null
    bytes += jpeg.byteLength
    frames.push({ captureTsMs: frame.tsMs, jpeg })
  }
  return { frames, bytes }
}

/**
 * Confirm a written chunk reads back as the frames it was built from.
 *
 * This is the precondition for deleting anything. It re-reads from disk rather
 * than checking the buffer that was just written, so it also catches a write
 * that never landed, landed short, or landed somewhere else.
 */
function verifyChunk(
  bytes: Uint8Array,
  chunk: PlannedChunk
): { ok: true } | { ok: false; reason: string } {
  let parsed
  try {
    parsed = decodeChunk(bytes)
  } catch (e) {
    const why = e instanceof ChunkFormatError ? e.message : String(e)
    return { ok: false, reason: `chunk did not read back: ${why}` }
  }
  if (parsed.frames.length !== chunk.frames.length) {
    return {
      ok: false,
      reason: `chunk holds ${parsed.frames.length} frames, planned ${chunk.frames.length}`
    }
  }
  for (let i = 0; i < chunk.frames.length; i++) {
    if (parsed.frames[i].captureTsMs !== chunk.frames[i].tsMs) {
      // Offsets are the addressing scheme; a shifted timestamp means frame i in
      // the file is not frame i in the plan, and every read would be wrong.
      return { ok: false, reason: `frame ${i} came back with the wrong capture time` }
    }
  }
  if (parsed.width !== chunk.width || parsed.height !== chunk.height) {
    return { ok: false, reason: 'chunk came back with the wrong geometry' }
  }
  return { ok: true }
}

/** Compact one batch. Safe to call repeatedly; each pass takes what is left. */
export async function compactOnce(deps: CompactorDeps): Promise<CompactionResult> {
  const now = deps.nowMs()
  const candidates = deps.listCompactable(now, COMPACTION_BATCH_FRAMES)
  const plan = planChunks(candidates, now)
  const result: CompactionResult = {
    chunksWritten: 0,
    framesCompacted: 0,
    bytesReclaimed: 0,
    skipped: []
  }
  if (plan.length === 0) return result

  for (const chunk of plan) {
    const first = chunk.frames[0]
    const last = chunk.frames[chunk.frames.length - 1]
    const relativePath = chunkRelativePath(chunk.day, first.tsMs, last.tsMs)

    const sources = await loadSources(chunk, deps)
    if (!sources) {
      result.skipped.push({ chunk: relativePath, reason: 'a source frame could not be read' })
      continue
    }

    let encoded: Uint8Array
    try {
      encoded = await deps.encode({
        width: chunk.width,
        height: chunk.height,
        frames: sources.frames
      })
    } catch (e) {
      result.skipped.push({ chunk: relativePath, reason: `encode failed: ${(e as Error).message}` })
      continue
    }

    try {
      await deps.writeChunk(relativePath, encoded)
    } catch (e) {
      result.skipped.push({ chunk: relativePath, reason: `write failed: ${(e as Error).message}` })
      continue
    }

    let readBack: Uint8Array
    try {
      readBack = await deps.readChunk(relativePath)
    } catch (e) {
      await deps.removeChunk(relativePath).catch(() => undefined)
      result.skipped.push({
        chunk: relativePath,
        reason: `re-read failed: ${(e as Error).message}`
      })
      continue
    }

    const verified = verifyChunk(readBack, chunk)
    if (!verified.ok) {
      // Nothing points at it yet, so removing the file is the whole cleanup.
      await deps.removeChunk(relativePath).catch(() => undefined)
      result.skipped.push({ chunk: relativePath, reason: verified.reason })
      continue
    }

    // Past this line the chunk is durable and proven to hold these frames.
    let claimed = 0
    for (let offset = 0; offset < chunk.frames.length; offset++) {
      const frame = chunk.frames[offset]
      // Capture the path first: the claim clears `image_path`.
      const jpegPath = frame.imagePath
      if (!deps.claimFrame(frame.id, relativePath, offset)) continue
      claimed++
      await deps.deleteJpeg(jpegPath).catch(() => undefined)
      result.bytesReclaimed += sources.frames[offset].jpeg.byteLength
    }

    if (claimed === 0) {
      // Every frame was claimed by someone else between planning and now. The
      // file is unreferenced; take it back rather than leaving it for the sweep.
      await deps.removeChunk(relativePath).catch(() => undefined)
      result.skipped.push({ chunk: relativePath, reason: 'every frame was already claimed' })
      continue
    }

    result.chunksWritten++
    result.framesCompacted += claimed
    deps.log(
      `rewind: compacted ${claimed} frames into ${relativePath} ` +
        `(${Math.round(sources.bytes / 1024)} KB of JPEGs -> ${Math.round(encoded.byteLength / 1024)} KB)`
    )
  }

  if (result.skipped.length > 0) {
    // Never silent: a compactor that quietly does nothing is indistinguishable
    // from one that is working, and this one deliberately skips a lot.
    deps.log(
      `rewind: skipped ${result.skipped.length} chunk(s): ` +
        result.skipped.map((s) => `${s.chunk} (${s.reason})`).join('; ')
    )
  }
  return result
}

/** What a pass would reclaim, without doing it. Used by the settings surface. */
export function estimateReclaimable(
  frames: CompactableFrame[],
  nowMs: number,
  sizeOf: (frame: CompactableFrame) => number
): { frames: number; bytes: number } {
  const plan = planChunks(frames, nowMs)
  return {
    frames: plan.reduce((n, c) => n + c.frames.length, 0),
    bytes: plannedJpegBytes(plan, sizeOf)
  }
}
