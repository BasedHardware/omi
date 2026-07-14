import { readdir, stat, unlink } from 'fs/promises'
import { join } from 'path'
import { rewindRoot } from './paths'
import { rewindImagePathsBetween } from '../ipc/db'
import { selectOrphanFiles, ORPHAN_GRACE_MS, type SweepFile } from './orphanSelection'

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
 */

const DAY_MS = 24 * 60 * 60 * 1000
/** How often the runner sweeps after the startup pass. */
const SWEEP_INTERVAL_MS = 6 * 60 * 60 * 1000 // every 6h
/** Delay the first sweep so it never competes with launch. */
const SWEEP_STARTUP_DELAY_MS = 60_000

const DAY_DIR_RE = /^\d{4}-\d{2}-\d{2}$/

/** Local-midnight ms bounds [start, end) for a "YYYY-MM-DD" day-dir name. */
function dayBounds(dayName: string): { fromMs: number; toMs: number } {
  const [y, m, d] = dayName.split('-').map(Number)
  const fromMs = new Date(y, m - 1, d).getTime()
  return { fromMs, toMs: fromMs + DAY_MS }
}

async function sweepDayDir(dayName: string, nowMs: number): Promise<number> {
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

  const { fromMs, toMs } = dayBounds(dayName)
  const dbImagePaths = new Set(rewindImagePathsBetween(fromMs, toMs))
  const orphans = selectOrphanFiles({ files, dbImagePaths, nowMs, graceMs: ORPHAN_GRACE_MS })
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
  let total = 0
  for (const day of dayNames) total += await sweepDayDir(day, nowMs)
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
