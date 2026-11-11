// Even down-sampling for a day of Rewind frames — the macOS `getScreenshotsSampled`
// contract (RewindDatabase.swift), as ONE importable source db.ts runs and the SQL
// test drives. db.ts pulls in better-sqlite3 (Electron ABI) and can't load under
// plain-node vitest, so the step math + statement live here (pure) instead of being
// re-declared "verbatim" in the test, where they would silently drift.
//
// Contract: count the frames in the day; if <= target, return them all ASC; else
// pick every Nth row over the timestamp-ordered list so a busy day collapses to
// ~target EVENLY-SPACED frames (not the newest/oldest N, not paginated). Always
// oldest-first. This is also the row-limit backstop — listRewindFrames has none, so
// a very active historical day would otherwise pull tens of thousands of rows into a
// single IPC round-trip and renderer array.

/** macOS parity: per-day frame budget for the timeline (RewindViewModel 500). */
export const REWIND_SAMPLE_TARGET = 500

/**
 * The index stride that yields ~`target` evenly-spaced rows out of `total`. `1`
 * (take everything) when the day already fits, or for a non-positive target.
 * Matches Mac's `step = totalCount / targetCount` (integer division).
 */
export function rewindSampleStep(total: number, target: number): number {
  if (target <= 0 || total <= target) return 1
  return Math.floor(total / target)
}

/**
 * Count frames in `[from, to]`. Bind `from, to`. Fast: `idx_rewind_frames_ts` makes
 * the BETWEEN an indexed range scan, and COUNT touches only the index.
 */
export const REWIND_DAY_COUNT_SQL =
  'SELECT COUNT(*) AS n FROM rewind_frames WHERE ts BETWEEN ? AND ?'

/**
 * Every `step`-th frame in `[from, to]`, oldest-first, projected with `columns`
 * (the caller's `RewindFrame` projection). Bind `from, to, step`.
 *
 * The row numbering lives in an inner subquery over `id` + `ROW_NUMBER()` only, so
 * the outer projection reads `columns` straight off the base table and every column
 * alias in it stays valid (aliasing inside the CTE would rename the columns out from
 * under the outer select). Picks ids at ordered positions 0, step, 2·step, … via
 * `(rn - 1) % step = 0`.
 */
export function buildRewindSampledSql(columns: string): string {
  return `SELECT ${columns} FROM rewind_frames
           WHERE id IN (
             SELECT id FROM (
               SELECT id, ROW_NUMBER() OVER (ORDER BY ts) AS rn
                 FROM rewind_frames
                WHERE ts BETWEEN ? AND ?
             ) WHERE (rn - 1) % ? = 0
           )
           ORDER BY ts`
}
