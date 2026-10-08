/**
 * The load-bearing SQL for chunk-backed frames, as one importable source that
 * both `db.ts` and the SQL tests execute.
 *
 * Same reasoning as `rewindEmbeddingSql.ts`, which records what happens without
 * it: `db.ts` pulls in better-sqlite3 and cannot load under plain-node vitest,
 * so a test that wants to run this SQL has to either import it from here or
 * re-declare it, and a re-declared copy drifts silently. These statements are
 * the ones that decide whether a JPEG may be deleted, so they are the last
 * place in this feature where a drifting copy would be acceptable.
 *
 * Pure by construction: no electron, no better-sqlite3, no I/O.
 */

/**
 * Frames that may be compacted.
 *
 * Every clause is a safety property, not an optimisation:
 *
 *  - `chunk_path IS NULL` — not already compacted. Compaction is idempotent
 *    only because of this.
 *  - `image_path != ''` — a row whose JPEG was already surrendered has nothing
 *    left to pack.
 *  - `indexed = 1` — OCR has already run. The backlog sweep in `ocrService.ts`
 *    reads `image_path` for `indexed = 0` frames and, when the file is missing,
 *    marks the frame indexed with *empty text* rather than failing. Compacting
 *    an un-OCR'd frame would therefore not error; it would quietly cost that
 *    frame its searchable text forever. This clause is the whole reason the
 *    compactor cannot simply take the oldest frames.
 *  - `ts <= ?` — older than the compaction delay, bound by the caller.
 *
 * Ordered by `ts` so the planner's grouping sees frames in capture order, and
 * by `id` after it so two frames sharing a millisecond order deterministically.
 *
 * The `id` tiebreak is not observable in a test: with it removed SQLite happens
 * to return same-`ts` rows in rowid order, which is the same answer. It is kept
 * because "happens to" is not a contract — the plan can change with the
 * indexes — and because the planner turns this order directly into chunk
 * offsets, so a reordering here silently mis-addresses frames. The planner
 * re-sorts defensively for the same reason, and that sort IS tested.
 */
export const COMPACTABLE_FRAMES_SQL = `SELECT id, ts, width, height, image_path AS imagePath
     FROM rewind_frames
    WHERE chunk_path IS NULL
      AND image_path != ''
      AND indexed = 1
      AND ts <= ?
    ORDER BY ts, id
    LIMIT ?`

/**
 * Point one frame at its position inside a chunk and surrender its JPEG path.
 *
 * `image_path` is set to `''` rather than NULL because the column is `NOT NULL`
 * and existing readers compare it as a string. macOS carries the identical
 * compromise for the same reason, and says so:
 * "`imagePath` is NOT NULL in SQLite, whereas video-backed screenshots carry
 * nil in the model" (`RewindAbandonedVideoChunkRecovery.swift`).
 *
 * The `chunk_path IS NULL` guard makes this safe to re-run: a second pass over
 * a frame another run already claimed updates nothing instead of re-pointing it
 * at a different chunk.
 */
export const CLAIM_FRAME_INTO_CHUNK_SQL = `UPDATE rewind_frames
        SET chunk_path = ?, chunk_offset = ?, image_path = ''
      WHERE id = ?
        AND chunk_path IS NULL`

/** Frames a chunk owns, in offset order — the read side of the claim above. */
export const FRAMES_IN_CHUNK_SQL = `SELECT id, ts, chunk_offset AS chunkOffset
     FROM rewind_frames
    WHERE chunk_path = ?
    ORDER BY chunk_offset`

/**
 * Chunks that no longer back any frame.
 *
 * Retention deletes `rewind_frames` rows by age; a chunk file becomes garbage
 * the moment its last row goes. This is the query the sweep uses to find them,
 * and it is deliberately driven from the tombstone-free direction: it asks
 * which distinct `chunk_path` values are still referenced and leaves the caller
 * to diff that against the directory, so a chunk file the database has never
 * heard of is also collected.
 */
export const REFERENCED_CHUNK_PATHS_SQL =
  'SELECT DISTINCT chunk_path FROM rewind_frames WHERE chunk_path IS NOT NULL'

/**
 * Tombstone a chunk and drop every frame that pointed into it.
 *
 * This is macOS's `abandonVideoChunk` (`RewindAbandonedVideoChunkRecovery.swift`)
 * with the same two-statement shape and the same idempotence: recording the
 * tombstone first means a crash between the two statements still leaves the
 * chunk quarantined, and re-running finishes the delete.
 */
export const TOMBSTONE_CHUNK_SQL =
  'INSERT OR IGNORE INTO rewind_abandoned_chunks (chunk_path) VALUES (?)'

export const DELETE_FRAMES_IN_CHUNK_SQL = 'DELETE FROM rewind_frames WHERE chunk_path = ?'

/**
 * Whether a chunk has been tombstoned.
 *
 * The claim path checks this before pointing any frame at a chunk, which is
 * what stops a compaction that was abandoned mid-flight from being resurrected
 * by a later run that still holds the old plan in memory.
 */
export const IS_CHUNK_ABANDONED_SQL =
  'SELECT EXISTS(SELECT 1 FROM rewind_abandoned_chunks WHERE chunk_path = ?) AS abandoned'

/** Bytes reclaimed so far, for the status surface. */
export const CHUNK_BACKED_FRAME_COUNT_SQL =
  'SELECT COUNT(*) AS n FROM rewind_frames WHERE chunk_path IS NOT NULL'
