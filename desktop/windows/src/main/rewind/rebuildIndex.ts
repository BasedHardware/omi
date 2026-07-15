import { readdir, stat, readFile } from 'fs/promises'
import { join } from 'path'
import { nativeImage } from 'electron'
import { rewindRoot } from './paths'
import { rewindImagePathsBetween, insertRewindFrame } from '../ipc/db'
import { deriveKeepSetWindow, parseFrameTs } from './orphanSelection'
import { selectFramesToReindex, type DiskFrameFile } from './rebuildSelection'

/**
 * Windows-specific recovery: re-create `rewind_frames` rows from the JPEGs still on
 * disk. macOS has a live `rebuildFromVideoFiles` reached from its recovery banner;
 * Windows had NO analog — the orphan sweep only ever DELETES unreferenced files, it
 * never re-associates them. So after a whole-DB reset/recovery (PR2b) wiped
 * rewind_frames, every surviving `<userData>/rewind/<day>/<ts>.jpg` became
 * unreachable garbage the sweep would eventually delete, even though the pixels are
 * intact. This closes that gap: for each JPEG with no row, INSERT one with
 * `indexed=0` so the EXISTING OCR backfill (ocrService.ts) re-OCRs it.
 *
 * Strictly additive and non-destructive:
 *  - Only INSERTs. Never deletes a file (that's the orphan sweep's job) and never
 *    overwrites an existing row (skip-existing guard in selectFramesToReindex).
 *  - Idempotent — a second run finds the rows it just made and inserts nothing.
 *  - Fail-open per entry — an unreadable dir/file or an undecodable JPEG is skipped,
 *    never crashing the rebuild.
 *  - No phantom frames — a row is only created for a file that actually decodes as a
 *    JPEG (nativeImage, same validation the capture path uses).
 *  - Bounded — processes one day dir at a time; never loads every path across the
 *    whole history into memory at once.
 *
 * Pure selection lives in rebuildSelection.ts.
 */

const DAY_DIR_RE = /^\d{4}-\d{2}-\d{2}$/

async function rebuildDayDir(dayName: string): Promise<number> {
  const dir = join(rewindRoot(), dayName)
  let entries: string[]
  try {
    entries = await readdir(dir)
  } catch {
    return 0 // dir vanished between listing and read — nothing to do
  }
  const jpgs = entries.filter((e) => e.toLowerCase().endsWith('.jpg'))
  if (jpgs.length === 0) return 0

  const files: DiskFrameFile[] = []
  for (const filename of jpgs) {
    const fullPath = join(dir, filename)
    try {
      const st = await stat(fullPath)
      files.push({ filename, fullPath, mtimeMs: st.mtimeMs })
    } catch {
      /* file vanished — skip */
    }
  }
  if (files.length === 0) return 0

  // Bound the "already has a row" query by each file's EFFECTIVE ts (filename ts, or
  // mtime when the name doesn't parse) padded a day each side — the same DST/TZ-safe
  // windowing the orphan sweep uses, extended to cover mtime-derived rows so a
  // previously-rebuilt stray file is still recognised as already-rowed on re-run.
  const effectiveTs = files.map((f) => parseFrameTs(f.filename) ?? f.mtimeMs)
  const win = deriveKeepSetWindow(effectiveTs)
  if (!win) return 0 // no files to bound (all stats failed) — nothing to do
  const dbImagePaths = new Set(rewindImagePathsBetween(win.fromMs, win.toMs))

  const targets = selectFramesToReindex({ files, dbImagePaths })
  let inserted = 0
  for (const t of targets) {
    try {
      const buf = await readFile(t.fullPath)
      // Decode-validate: a row must never be created for a file that isn't a
      // readable image, so a stray non-JPEG never becomes a phantom frame. This
      // also yields the real dimensions the frame viewer needs (the OCR backfill
      // only fills text, never width/height).
      const image = nativeImage.createFromBuffer(buf)
      if (image.isEmpty()) continue
      const { width, height } = image.getSize()
      insertRewindFrame({
        ts: t.ts,
        app: '',
        windowTitle: '',
        processName: '',
        ocrText: '',
        imagePath: t.fullPath,
        width,
        height,
        indexed: 0 // let the existing OCR backfill re-index it
      })
      inserted++
    } catch {
      /* unreadable file — fail-open, skip this entry */
    }
  }
  return inserted
}

/**
 * Re-create missing `rewind_frames` rows from the JPEGs on disk across every day
 * dir. Returns the number of rows inserted. Safe to call any time — it only fills
 * gaps (idempotent) — but it exists for the post-recovery case where rewind_frames
 * was wiped while the JPEGs survived.
 */
export async function rebuildRewindIndexFromDisk(): Promise<number> {
  let dayNames: string[]
  try {
    dayNames = (await readdir(rewindRoot())).filter((n) => DAY_DIR_RE.test(n))
  } catch {
    return 0 // rewind root doesn't exist yet (no frames ever captured)
  }
  let total = 0
  for (const day of dayNames) total += await rebuildDayDir(day)
  if (total > 0) console.log(`[rewind] index rebuild inserted ${total} row(s) from disk`)
  return total
}
