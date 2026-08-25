import { describe, it, expect } from 'vitest'
import {
  selectOrphanFiles,
  parseFrameTs,
  deriveKeepSetWindow,
  ORPHAN_GRACE_MS,
  type SweepFile
} from './orphanSelection'

const NOW = 10_000_000

function file(tsMs: number, mtimeMs = tsMs): SweepFile {
  return { filename: `${tsMs}.jpg`, fullPath: `/rewind/2026-07-14/${tsMs}.jpg`, mtimeMs }
}

describe('parseFrameTs', () => {
  it('parses <tsMs>.jpg', () => {
    expect(parseFrameTs('1720000000000.jpg')).toBe(1720000000000)
  })
  it('rejects non-frame filenames', () => {
    expect(parseFrameTs('notes.txt')).toBeNull()
    expect(parseFrameTs('abc.jpg')).toBeNull()
    expect(parseFrameTs('.jpg')).toBeNull()
  })
})

describe('selectOrphanFiles', () => {
  it('deletes an orphan older than the grace window', () => {
    const f = file(NOW - ORPHAN_GRACE_MS - 1_000) // orphan, well past grace
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: new Set(),
        nowMs: NOW,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([f.fullPath])
  })

  it('keeps an orphan still within the grace window (possible in-flight insert)', () => {
    const f = file(NOW - 5_000) // orphan, 5s old, inside 60s grace
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: new Set(),
        nowMs: NOW,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([])
  })

  it('keeps a file that has a matching DB row, even when old', () => {
    const f = file(NOW - ORPHAN_GRACE_MS - 10_000)
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: new Set([f.fullPath]),
        nowMs: NOW,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([])
  })

  it('keeps an old-by-name file whose mtime is fresh (either signal young → keep)', () => {
    // filename ts is ancient but the file was just touched — mtime says young.
    const f = file(NOW - ORPHAN_GRACE_MS - 100_000, NOW - 1_000)
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: new Set(),
        nowMs: NOW,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([])
  })

  it('sweeps only the orphans in a mixed dir', () => {
    const rowed = file(NOW - 200_000)
    const oldOrphan = file(NOW - 200_000 - 1) // distinct path
    oldOrphan.fullPath = '/rewind/2026-07-14/old.jpg'
    oldOrphan.filename = 'old.jpg'
    const freshOrphan = file(NOW - 1_000)
    freshOrphan.fullPath = '/rewind/2026-07-14/fresh.jpg'
    freshOrphan.filename = 'fresh.jpg'
    const out = selectOrphanFiles({
      files: [rowed, oldOrphan, freshOrphan],
      dbImagePaths: new Set([rowed.fullPath]),
      nowMs: NOW,
      graceMs: ORPHAN_GRACE_MS
    })
    expect(out).toEqual([oldOrphan.fullPath])
  })
})

describe('deriveKeepSetWindow', () => {
  it('returns null for a dir with no parseable frame timestamps', () => {
    expect(deriveKeepSetWindow([])).toBeNull()
  })
  it('pads a full day on each side of the min/max file ts', () => {
    const DAY = 24 * 60 * 60 * 1000
    expect(deriveKeepSetWindow([5_000_000, 7_000_000])).toEqual({
      fromMs: 5_000_000 - DAY,
      toMs: 7_000_000 + DAY
    })
  })
})

describe('C1 regression — DST/TZ offset shift must not false-delete valid files', () => {
  // A 25-hour local day (DST fall-back) or westward TZ travel pushes a frame's ts
  // past local-midnight+24h, yet the frame still lives in this day-dir (named from
  // its LOCAL date at capture). The keep-set window must still cover its DB row.
  it('keeps a valid file whose ts is past local-midnight+24h (bug repro + fix)', () => {
    const DAY = 24 * 60 * 60 * 1000
    const localMidnight = new Date(2026, 10, 1).getTime() // Nov 1 2026, local midnight
    const dstFileTs = localMidnight + DAY + 30 * 60_000 // 24h30m into the 25h day
    const f: SweepFile = {
      filename: `${dstFileTs}.jpg`,
      fullPath: `/rewind/2026-11-01/${dstFileTs}.jpg`,
      mtimeMs: dstFileTs
    }
    // The file HAS a valid DB row (ts = dstFileTs).
    const dbRows = [{ imagePath: f.fullPath, ts: dstFileTs }]
    const now = dstFileTs + 10 * 60_000 // well past the 60s grace

    // OLD name-derived window [localMidnight, localMidnight+24h) EXCLUDES the row →
    // keep-set misses it → the sweep would unlink a valid file (the data-loss bug).
    const buggyKeep = new Set(
      dbRows
        .filter((r) => r.ts >= localMidnight && r.ts < localMidnight + DAY)
        .map((r) => r.imagePath)
    )
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: buggyKeep,
        nowMs: now,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([f.fullPath]) // demonstrates the bug without the fix

    // FIXED file-derived window covers the row → keep-set includes it → not deleted.
    const win = deriveKeepSetWindow([parseFrameTs(f.filename)!])!
    const fixedKeep = new Set(
      dbRows.filter((r) => r.ts >= win.fromMs && r.ts < win.toMs).map((r) => r.imagePath)
    )
    expect(
      selectOrphanFiles({
        files: [f],
        dbImagePaths: fixedKeep,
        nowMs: now,
        graceMs: ORPHAN_GRACE_MS
      })
    ).toEqual([]) // fix: no false deletion
  })
})
