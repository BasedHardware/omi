/**
 * Pure selection logic for the disk→DB Rewind rebuild (kept db-free so it's unit
 * testable, mirroring orphanSelection.ts vs orphanSweep.ts). The impure runner —
 * fs walk, JPEG decode, INSERT — lives in rebuildIndex.ts.
 *
 * The rebuild is the INVERSE of the orphan sweep: the sweep DELETES a `<ts>.jpg`
 * with no DB row; the rebuild RE-CREATES the missing row so a surviving JPEG isn't
 * orphaned after a whole-DB reset/recovery (PR2b) wiped rewind_frames. It only ever
 * INSERTs — it never deletes and never overwrites an existing row.
 */

import { parseFrameTs, type SweepFile } from './orphanSelection'

/** A `.jpg` file found in a day dir. Same shape the orphan sweep gathers. */
export type DiskFrameFile = SweepFile

/** A row the rebuild will INSERT: the JPEG's path and the ts to record for it. */
export type RebuildTarget = { fullPath: string; ts: number }

/**
 * Given the `.jpg` files in a day dir and the image paths the DB already knows for
 * that day, return the files that need a NEW row — i.e. those whose exact path is
 * NOT already referenced by a row. Idempotent by construction: a file that already
 * has a row is skipped, so a second run over the same dir selects nothing.
 *
 * The ts is derived from the `<ts>.jpg` filename; a file whose name doesn't parse
 * (never produced by the capture path, but a stray file could exist) falls back to
 * its mtime so it still lands somewhere sane on the timeline. Extension filtering
 * and JPEG-decode validation (the real "is this a frame?" gate) happen in the
 * runner — this function assumes the caller already passed only candidate files.
 */
export function selectFramesToReindex(args: {
  files: DiskFrameFile[]
  dbImagePaths: Set<string>
}): RebuildTarget[] {
  const { files, dbImagePaths } = args
  const targets: RebuildTarget[] = []
  for (const f of files) {
    // Skip-existing-row guard — this is what makes the rebuild idempotent and
    // non-destructive (never a second row for a path a row already references).
    if (dbImagePaths.has(f.fullPath)) continue
    const parsed = parseFrameTs(f.filename)
    targets.push({ fullPath: f.fullPath, ts: parsed ?? f.mtimeMs })
  }
  return targets
}
