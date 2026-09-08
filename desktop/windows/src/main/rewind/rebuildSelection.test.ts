import { describe, it, expect } from 'vitest'
import { selectFramesToReindex, type DiskFrameFile } from './rebuildSelection'

function file(tsMs: number, mtimeMs = tsMs): DiskFrameFile {
  return { filename: `${tsMs}.jpg`, fullPath: `/rewind/2026-07-14/${tsMs}.jpg`, mtimeMs }
}

describe('selectFramesToReindex', () => {
  it('selects an orphan JPEG (no DB row) with the ts parsed from its filename', () => {
    const f = file(1_720_000_000_000)
    expect(selectFramesToReindex({ files: [f], dbImagePaths: new Set() })).toEqual([
      { fullPath: f.fullPath, ts: 1_720_000_000_000 }
    ])
  })

  it('skips a file that already has a DB row (idempotent)', () => {
    const f = file(1_720_000_000_000)
    expect(selectFramesToReindex({ files: [f], dbImagePaths: new Set([f.fullPath]) })).toEqual([])
  })

  it('a second run over an already-rebuilt dir selects nothing', () => {
    const files = [file(1000), file(2000), file(3000)]
    // First run: nothing in the DB → all three selected.
    const first = selectFramesToReindex({ files, dbImagePaths: new Set() })
    expect(first).toHaveLength(3)
    // Those rows now exist → second run selects none.
    const afterInsert = new Set(first.map((t) => t.fullPath))
    expect(selectFramesToReindex({ files, dbImagePaths: afterInsert })).toEqual([])
  })

  it('selects only the orphans in a mixed dir', () => {
    const rowed = file(1000)
    const orphan = file(2000)
    const out = selectFramesToReindex({
      files: [rowed, orphan],
      dbImagePaths: new Set([rowed.fullPath])
    })
    expect(out).toEqual([{ fullPath: orphan.fullPath, ts: 2000 }])
  })

  it('falls back to mtime for a file whose name does not parse as <ts>.jpg', () => {
    const f: DiskFrameFile = {
      filename: 'screenshot.jpg',
      fullPath: '/rewind/2026-07-14/screenshot.jpg',
      mtimeMs: 5_555
    }
    expect(selectFramesToReindex({ files: [f], dbImagePaths: new Set() })).toEqual([
      { fullPath: f.fullPath, ts: 5_555 }
    ])
  })

  // Mutation check for the skip-existing-row guard: the guard is the ONLY thing
  // keeping the rebuild non-destructive (never a duplicate row for a path a row
  // already references). Delete `if (dbImagePaths.has(f.fullPath)) continue` in
  // selectFramesToReindex and this fails — a duplicate target is produced for the
  // already-rowed file.
  it('MUTATION GUARD: never re-selects a path the DB already references', () => {
    const f = file(9000)
    const out = selectFramesToReindex({ files: [f], dbImagePaths: new Set([f.fullPath]) })
    expect(out).toHaveLength(0)
  })
})
