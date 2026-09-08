// The load-bearing SQL for the Rewind embedding store — the privacy-critical
// deletes, the backfill work-query, and the paged similarity scan — as ONE
// importable source that both `db.ts` and the SQL tests execute.
//
// This module exists for the same reason `rewindEmbeddingSchema.ts` does, and it
// closes the same hole one level deeper. `db.ts` pulls in better-sqlite3 (Electron
// ABI) and cannot load under plain-node vitest, so `rewindEmbeddingSql.test.ts`
// used to RE-DECLARE these statements "verbatim" and drive them through
// node:sqlite. A re-declared copy is not the code — it drifts, silently, and the
// drift already happened twice:
//   * the work-query test filtered `ocr_text != ''` while production had moved to
//     `LENGTH(TRIM(ocr_text)) >= MIN_EMBED_TEXT_LEN` — so the min-length floor that
//     keeps the backfill from stalling was never actually exercised;
//   * the paged-scan test lacked the `LENGTH(v.vec) = <blob bytes>` guard that
//     production added to stop a partial write truncating the scan.
// Neither divergence turned a test red. Both are impossible now: the statement
// lives in exactly one place, and the test runs THAT.
//
// Pure by construction — no electron / better-sqlite3 import — so the test can
// load it. It depends only on the pure policy constants (`MIN_EMBED_TEXT_LEN`,
// `EMBED_BLOB_BYTES`).
import { MIN_EMBED_TEXT_LEN } from '../rewind/embedQueue'
import { EMBED_BLOB_BYTES } from '../rewind/embedVector'

// Qualified `rewind_frames` projection. It lives here — not in db.ts — because the
// backfill work-query below hydrates full frames with it, and the SQL test must be
// able to import the IDENTICAL projection production runs (it cannot import db.ts).
// db.ts imports this back for its FTS keyword search, which projects the same set.
export const REWIND_COLUMNS_QUALIFIED =
  'rewind_frames.id, rewind_frames.ts, rewind_frames.app, rewind_frames.window_title AS windowTitle, ' +
  'rewind_frames.process_name AS processName, rewind_frames.ocr_text AS ocrText, ' +
  'rewind_frames.image_path AS imagePath, rewind_frames.width, rewind_frames.height, rewind_frames.indexed'

// --- Retention / privacy: the orphan GC ---
// A vector is derived from the user's screen. There is no FK/CASCADE
// (foreign_keys is off), so these two DELETES are the ONLY thing that makes
// "delete my history" reach the vectors. Run the mapping delete first, then the
// vector delete, so the vector GC sees the truth (see dropOrphanedEmbeddingsOn).

/** Drop mapping rows whose frame is gone. */
export const DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL =
  'DELETE FROM rewind_embeddings WHERE frame_id NOT IN (SELECT id FROM rewind_frames)'

/**
 * Drop any vector no live mapping references.
 *
 * `WHERE hash IS NOT NULL` in the subquery is NOT optional. `hash` is nullable;
 * SQLite's `x NOT IN (<set containing NULL>)` evaluates to NULL (never true) for
 * every row, so a single NULL-hash mapping would make this DELETE match NOTHING —
 * every retired vector would then orphan and survive "delete my history". The
 * guard keeps the NULL out of the set. (See the mutation-checked test.)
 */
export const DROP_ORPHANED_EMBEDDING_VECTORS_SQL = `DELETE FROM rewind_embedding_vectors
      WHERE hash NOT IN (SELECT hash FROM rewind_embeddings WHERE hash IS NOT NULL)`

/**
 * The backfill work-query: frames that have embeddable OCR text but no vector yet,
 * newest first. `excludeCount` is the number of `?` placeholders for ids the
 * caller has given up on this launch (bind them, then `limit`, in that order).
 *
 * The `LENGTH(TRIM(ocr_text)) >= MIN_EMBED_TEXT_LEN` floor MUST match the queue's
 * accept guard: without it, too-short frames (lock screen, video, blank desktop)
 * are returned here, refused by the queue, never earn an embedding row, and so are
 * returned forever — stalling the backfill at the head of the newest-first page.
 */
export function rewindFramesNeedingEmbeddingSql(excludeCount: number): string {
  const notIn = excludeCount
    ? `AND rewind_frames.id NOT IN (${Array.from({ length: excludeCount }, () => '?').join(',')})`
    : ''
  return `SELECT ${REWIND_COLUMNS_QUALIFIED} FROM rewind_frames
           LEFT JOIN rewind_embeddings ON rewind_embeddings.frame_id = rewind_frames.id
          WHERE rewind_frames.indexed = 1
            AND rewind_frames.ocr_text IS NOT NULL
            AND LENGTH(TRIM(rewind_frames.ocr_text)) >= ${MIN_EMBED_TEXT_LEN}
            AND rewind_embeddings.frame_id IS NULL
            ${notIn}
          ORDER BY rewind_frames.ts DESC
          LIMIT ?`
}

/**
 * One page of the disk-based similarity scan: unique content vectors that some
 * live frame still references, ordered by hash for stable paging.
 *
 * `blobBytes` is the expected vector BLOB size. Production passes `EMBED_BLOB_BYTES`
 * (a 3072-dim vector is 12288 bytes); the guard rejects NULL / partially-written
 * vectors IN THE SQL, because `scanTopKBySimilarity` treats a short page as
 * end-of-store and a `.filter()` after the fetch would silently truncate the scan.
 * It is a parameter, not a baked constant, only so the SQL test can drive it with
 * small toy vectors — the guard shape is identical either way.
 */
export function searchEmbeddingPageSql(blobBytes: number = EMBED_BLOB_BYTES): string {
  return `SELECT v.hash AS hash, v.vec AS vec FROM rewind_embedding_vectors v
      WHERE EXISTS (SELECT 1 FROM rewind_embeddings e WHERE e.hash = v.hash)
        AND v.vec IS NOT NULL AND LENGTH(v.vec) = ${blobBytes}
      ORDER BY v.hash
      LIMIT ? OFFSET ?`
}
