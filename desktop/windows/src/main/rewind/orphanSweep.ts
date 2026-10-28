import { readdir, stat, unlink } from 'fs/promises'
import { join } from 'path'
import { rewindRoot } from './paths'
import { rewindImagePathsBetween } from '../ipc/db'
import { getRewindSettings } from './captureService'
import { retentionCutoff } from './retentionSelection'
import {
  selectOrphanFiles,
  deriveKeepSetWindow,
  parseFrameTs,
  ORPHAN_GRACE_MS,
  type SweepFile
} from './orphanSelection'

/**
 * Windows-specific durability sweep. Each Rewind frame is written as a JPEG
 * (writeFileSync) and THEN its DB row is inserted (insertRewindFrame). A crash
 * between those two steps orphans the file forever — no DB row ever references it,
 * so retention never deletes it and it wastes disk. (macOS has no equivalent: its
 * capture is in-process and it only does DB-row-driven retention.)
 *
 * This finds `<tsMs>.jpg` files under each day dir with no matching DB row and
 * deletes the ones old enough that they can't be an in-flight insert. Pure
 * selection logic lives in orphanSelection.ts.
 *
 * Selection is bounded by normal retention, not just the grace window: a no-row
 * file younger than the retention cutoff is kept, because its row may have been
 * lost to an index reset (the sign-out wipe incident: the sweep then saw every
 * historical JPEG as unreferenced and mass-deleted them) rather than to
 * retention, and rebuildIndex.ts can still re-associate it. Only files past the
 * retention cutoff are garbage no matter why their row is gone. Sign-out no
 * longer resets the index at all (dbWipe.ts parks it), so this bound is the
 * second line of defense for any future index-destroying bug.
 */

/** How often the runner sweeps after the startup pass. */
const SWEEP_INTERVAL_MS = 6 * 60 * 60 * 1000 // every 6h
/** Delay the first sweep so it never competes with launch. */
const SWEEP_STARTUP_DELAY_MS = 60_000

const DAY_DIR_RE = /^\d{4}-\d{2}-\d{2}$/

async function sweepDayDir(
  dayName: string,
  nowMs: number,
  retireBeforeMs: number
): Promise<number> {
  const dir = join(rewindRoot(), dayName)
  let entries: string[]
  try {
    entries = await readdir(dir)
  } catch {
    return 0 // dir vanished between listing and read — nothing to do
  }
  const jpgs = entries.filter((e) => e.toLowerCase().endsWith('.jpg'))
  if (jpgs.length === 0) return 0

  const files: SweepFile[] = []
  for (const filename of jpgs) {
    const fullPath = join(dir, filename)
    try {
      const st = await stat(fullPath)
      files.push({ filename, fullPath, mtimeMs: st.mtimeMs })
    } catch {
      /* file vanished — skip */
    }
  }

  // Bound the keep-set query by the ACTUAL file timestamps (padded a day each
  // side), never the dir's local-midnight name — otherwise a DST/TZ offset change
  // between capture and sweep pushes a frame's ts past local-midnight+24h and its
  // still-valid DB row falls outside a name-derived window, false-deleting the file.
  const tsValues = files.map((f) => parseFrameTs(f.filename)).filter((n): n is number => n != null)
  const win = deriveKeepSetWindow(tsValues)
  if (!win) return 0 // no parseable frame ts → nothing to bound; skip the query
  const dbImagePaths = new Set(rewindImagePathsBetween(win.fromMs, win.toMs))
  const orphans = selectOrphanFiles({
    files,
    dbImagePaths,
    nowMs,
    graceMs: ORPHAN_GRACE_MS,
    retireBeforeMs
  })
  let removed = 0
  for (const p of orphans) {
    try {
      await unlink(p)
      removed++
    } catch {
      /* best-effort: file may already be gone */
    }
  }
  return removed
}

/** One full sweep across all day dirs. Returns the number of orphaned files deleted. */
export async function sweepOrphanedFramesOnce(nowMs = Date.now()): Promise<number> {
  let dayNames: string[]
  try {
    dayNames = (await readdir(rewindRoot())).filter((n) => DAY_DIR_RE.test(n))
  } catch {
    return 0 // rewind root doesn't exist yet (no frames captured)
  }
  // Retention bound for the index-reset defense: only files past the cutoff are
  // deletable-on-sight. retentionCutoff clamps <= 0 days to `nowMs`, which
  // degenerates to the legacy grace-only behavior (newestSignal is never > now).
  const { retentionDays } = getRewindSettings()
  const retireBeforeMs = retentionCutoff(nowMs, retentionDays)
  let total = 0
  for (const day of dayNames) total += await sweepDayDir(day, nowMs, retireBeforeMs)
  return total
}

export function startOrphanSweep(): void {
  const run = (): void => {
    void sweepOrphanedFramesOnce()
      .then((n) => {
        if (n > 0) console.log(`[rewind] orphan sweep removed ${n} stale JPEG(s)`)
      })
      .catch((e) => console.warn('[rewind] orphan sweep failed:', e))
  }
  setTimeout(run, SWEEP_STARTUP_DELAY_MS)
  setInterval(run, SWEEP_INTERVAL_MS)
}
