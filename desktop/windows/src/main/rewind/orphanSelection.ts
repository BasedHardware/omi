/**
 * Pure selection logic for the orphaned-JPEG sweep (kept db-free so it's unit
 * testable, mirroring retentionSelection.ts vs retentionRunner.ts). The impure
 * runner lives in orphanSweep.ts.
 */

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
 * Given the JPEG files in a day dir, the set of image paths the DB knows for that
 * day, now, and the grace window → the fullPaths safe to delete. A file is deleted
 * only when it has NO DB row AND its most-recent age signal (filename ts or mtime,
 * whichever is newer) is older than the grace window, so an in-flight insert is
 * never raced.
 */
export function selectOrphanFiles(args: {
  files: SweepFile[]
  dbImagePaths: Set<string>
  nowMs: number
  graceMs: number
}): string[] {
  const { files, dbImagePaths, nowMs, graceMs } = args
  const orphans: string[] = []
  for (const f of files) {
    if (dbImagePaths.has(f.fullPath)) continue // has a live row — keep
    const ts = parseFrameTs(f.filename)
    // Treat the file as young if EITHER signal says so (conservative).
    const newestSignal = ts == null ? f.mtimeMs : Math.max(f.mtimeMs, ts)
    if (nowMs - newestSignal >= graceMs) orphans.push(f.fullPath)
  }
  return orphans
}
