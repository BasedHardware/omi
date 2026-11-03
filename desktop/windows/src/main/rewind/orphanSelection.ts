/**
 * Pure selection logic for the orphaned-JPEG sweep (kept db-free so it's unit
 * testable, mirroring retentionSelection.ts vs retentionRunner.ts). The impure
 * runner lives in orphanSweep.ts.
 */

const DAY_MS = 24 * 60 * 60 * 1000

/** Never delete a file younger than this — it could be an in-flight insert. */
export const ORPHAN_GRACE_MS = 60_000

export type SweepFile = { filename: string; fullPath: string; mtimeMs: number }

/** Parse the capture-ms embedded in a `<tsMs>.jpg` filename, or null if it isn't one. */
export function parseFrameTs(filename: string): number | null {
  const m = /^(\d+)\.jpg$/i.exec(filename)
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

/**
 * The DB-query window whose rows form the keep-set for a day dir. Derived from the
 * ACTUAL file timestamps present (min−1d … max+1d), NOT the dir's local-midnight
 * name: on a UTC-offset change between capture and sweep (DST fall-back's 25-hour
 * day, or westward TZ travel) a frame's ts can land past local-midnight+24h yet
 * still live in that day-dir, so a name-derived window would miss its row and the
 * sweep would false-delete a VALID file. Padding a full day each side provably
 * covers every file in the dir; over-covering only adds paths to the keep-set
 * (harmless), under-covering deletes (data loss). Returns null when no file has a
 * parseable ts (nothing to bound → skip the query).
 */
export function deriveKeepSetWindow(
  fileTsValues: number[]
): { fromMs: number; toMs: number } | null {
  if (fileTsValues.length === 0) return null
  return {
    fromMs: Math.min(...fileTsValues) - DAY_MS,
    toMs: Math.max(...fileTsValues) + DAY_MS
  }
}

/**
 * Given the JPEG files in a day dir, the set of image paths the DB knows for that
 * day, now, and the grace window → the fullPaths safe to delete. A file is deleted
 * only when it has NO DB row AND its most-recent age signal (filename ts or mtime,
 * whichever is newer) is older than the grace window, so an in-flight insert is
 * never raced.
 *
 * `retireBeforeMs` is the defense-in-depth bound (the sign-out index-reset
 * incident): an unindexed file YOUNGER than the retention cutoff is kept, because
 * its row may have been lost to an index reset rather than to retention -- such a
 * file is recoverable via the disk rebuild (rebuildIndex.ts) and only the index
 * itself retires files through normal retention. Pass
 * `retentionCutoff(nowMs, retentionDays)`. The parameter is REQUIRED so no caller
 * can silently drop the bound and get back the grace-only sweep that caused the
 * sign-out deletions; the only sanctioned degenerate form is
 * `retentionCutoff(nowMs, 0)` (retentionDays <= 0 clamps to nowMs), which keeps
 * every current file and so behaves grace-only.
 */
export function selectOrphanFiles(args: {
  files: SweepFile[]
  dbImagePaths: Set<string>
  nowMs: number
  graceMs: number
  retireBeforeMs: number
}): string[] {
  const { files, dbImagePaths, nowMs, graceMs, retireBeforeMs } = args
  const orphans: string[] = []
  for (const f of files) {
    if (dbImagePaths.has(f.fullPath)) continue // has a live row — keep
    const ts = parseFrameTs(f.filename)
    // Treat the file as young if EITHER signal says so (conservative).
    const newestSignal = ts == null ? f.mtimeMs : Math.max(f.mtimeMs, ts)
    if (nowMs - newestSignal < graceMs) continue // possible in-flight insert, keep
    if (newestSignal >= retireBeforeMs) {
      // Unindexed but younger than retention: possibly an index-reset victim,
      // not garbage. Leave it for the disk rebuild to re-associate. Inclusive
      // (>=) on purpose: normal retention deletes only rows with ts < cutoff,
      // so a file whose newest signal sits exactly AT the cutoff is still
      // inside retention and the sweep must treat it the same way.
      continue
    }
    orphans.push(f.fullPath)
  }
  return orphans
}
