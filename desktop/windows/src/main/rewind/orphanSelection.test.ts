import { describe, it, expect } from 'vitest'
import { selectOrphanFiles, parseFrameTs, ORPHAN_GRACE_MS, type SweepFile } from './orphanSelection'

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
