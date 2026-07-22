// Runner tests for the disk→DB Rewind rebuild. db.ts's better-sqlite3 and Electron's
// nativeImage can't load under plain-node vitest, so we mock the three impure seams
// (fs/promises, electron.nativeImage, ../ipc/db) and drive the REAL runner logic —
// its fail-open handling, the skip-existing / indexed=0 / decode-validation rules,
// and (critically) that it NEVER deletes. The pure selection guard is pinned
// separately in rebuildSelection.test.ts.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { join } from 'path'
import type { RewindFrame } from '../../shared/types'

const ROOT = join('C:', 'fake', 'userData', 'rewind')

const fsMock = vi.hoisted(() => ({
  readdir: vi.fn(),
  stat: vi.fn(),
  readFile: vi.fn(),
  unlink: vi.fn() // present so the test can PROVE the rebuild never calls it
}))
const db = vi.hoisted(() => ({
  rewindImagePathsBetween: vi.fn(),
  insertRewindFrame: vi.fn((_f: Omit<RewindFrame, 'id'>) => 1)
}))
const electron = vi.hoisted(() => ({ nativeImage: { createFromBuffer: vi.fn() } }))
const paths = vi.hoisted(() => ({ rewindRoot: vi.fn(() => ROOT) }))
const ocr = vi.hoisted(() => ({ signalRewindOcrPending: vi.fn() }))

vi.mock('fs/promises', () => fsMock)
vi.mock('../ipc/db', () => db)
vi.mock('electron', () => electron)
vi.mock('./paths', () => paths)
vi.mock('./ocrService', () => ocr)

import { rebuildRewindIndexFromDisk } from './rebuildIndex'

/** A decodable 640x480 image. Buffers that aren't this are treated as undecodable. */
const GOOD = Buffer.from('good-jpeg')
function decodable(buf: Buffer): boolean {
  return buf.equals(GOOD)
}

/**
 * Wire the fs + electron mocks to a fake tree: { '<day>': ['<file>', ...] }, where
 * every listed file reads back as a decodable JPEG unless named in `undecodable`.
 * `existingRows` is the set of full paths the DB already references (a live row).
 */
function seed(opts: {
  days: Record<string, string[]>
  existingRows?: string[]
  undecodable?: string[]
  unreadable?: string[]
}): void {
  const { days, existingRows = [], undecodable = [], unreadable = [] } = opts
  const undecSet = new Set(undecodable)
  const unreadSet = new Set(unreadable)

  fsMock.readdir.mockImplementation(async (dir: string) => {
    if (dir === ROOT) return Object.keys(days)
    for (const [day, files] of Object.entries(days)) {
      if (dir === join(ROOT, day)) return files
    }
    throw new Error('ENOENT')
  })
  fsMock.stat.mockImplementation(async () => {
    // mtime = a fixed sane value; filename-ts wins where the name parses anyway.
    return { mtimeMs: 1_700_000_000_000 }
  })
  fsMock.readFile.mockImplementation(async (full: string) => {
    if (unreadSet.has(full)) throw new Error('EACCES')
    return decodableFor(full, undecSet)
  })
  electron.nativeImage.createFromBuffer.mockImplementation((buf: Buffer) => ({
    isEmpty: () => !decodable(buf),
    getSize: () => ({ width: 640, height: 480 })
  }))
  db.rewindImagePathsBetween.mockReturnValue(existingRows)
}

function decodableFor(full: string, undec: Set<string>): Buffer {
  const name = full.split(/[\\/]/).pop() ?? ''
  return undec.has(name) ? Buffer.from('garbage') : GOOD
}

function insertedRows(): Omit<RewindFrame, 'id'>[] {
  return db.insertRewindFrame.mock.calls.map((c) => c[0])
}

beforeEach(() => vi.clearAllMocks())

describe('rebuildRewindIndexFromDisk', () => {
  it('inserts a row with indexed=0 for each orphan JPEG, carrying real dimensions', async () => {
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] } })
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(2)
    const rows = insertedRows()
    expect(rows).toHaveLength(2)
    for (const r of rows) {
      expect(r.indexed).toBe(0) // so the existing OCR backfill re-indexes it
      expect(r.width).toBe(640)
      expect(r.height).toBe(480)
      expect(r.ocrText).toBe('')
    }
    expect(rows.map((r) => r.ts).sort()).toEqual([1000, 2000])
    expect(rows.map((r) => r.imagePath)).toEqual([
      join(ROOT, '2026-07-14', '1000.jpg'),
      join(ROOT, '2026-07-14', '2000.jpg')
    ])
  })

  it('is idempotent — inserts nothing when every JPEG already has a row', async () => {
    const p1 = join(ROOT, '2026-07-14', '1000.jpg')
    const p2 = join(ROOT, '2026-07-14', '2000.jpg')
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] }, existingRows: [p1, p2] })
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(0)
    expect(db.insertRewindFrame).not.toHaveBeenCalled()
  })

  // The rebuilt rows are indexed=0 and the OCR backlog sweep is gated on an
  // in-memory pending latch — so the rebuild (a second producer of un-OCR'd rows
  // besides the capture hot path) MUST wake the sweep, or a rebuild done while the
  // sweep is idle would leave those frames un-OCR'd until the next capture/restart.
  it('signals the OCR sweep after inserting rebuilt rows', async () => {
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] } })
    await rebuildRewindIndexFromDisk()
    expect(ocr.signalRewindOcrPending).toHaveBeenCalledTimes(1)
  })

  it('does NOT signal the OCR sweep when it inserted nothing', async () => {
    const p1 = join(ROOT, '2026-07-14', '1000.jpg')
    seed({ days: { '2026-07-14': ['1000.jpg'] }, existingRows: [p1] })
    await rebuildRewindIndexFromDisk()
    expect(ocr.signalRewindOcrPending).not.toHaveBeenCalled()
  })

  it('skips files that already have a row, inserting only the orphans', async () => {
    const rowed = join(ROOT, '2026-07-14', '1000.jpg')
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] }, existingRows: [rowed] })
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(1)
    expect(insertedRows().map((r) => r.imagePath)).toEqual([join(ROOT, '2026-07-14', '2000.jpg')])
  })

  it('never creates a phantom row for an undecodable file (no crash)', async () => {
    seed({
      days: { '2026-07-14': ['1000.jpg', 'garbage.jpg'] },
      undecodable: ['garbage.jpg']
    })
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(1) // only the real JPEG
    expect(insertedRows().map((r) => r.imagePath)).toEqual([join(ROOT, '2026-07-14', '1000.jpg')])
  })

  it('fails open on an unreadable file — skips it, still processes the rest', async () => {
    const bad = join(ROOT, '2026-07-14', '2000.jpg')
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] }, unreadable: [bad] })
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(1)
    expect(insertedRows().map((r) => r.imagePath)).toEqual([join(ROOT, '2026-07-14', '1000.jpg')])
  })

  it('ignores non-day-dir entries and non-jpg files', async () => {
    seed({
      days: { '2026-07-14': ['1000.jpg', 'notes.txt'], 'not-a-day': ['9999.jpg'] }
    })
    const n = await rebuildRewindIndexFromDisk()
    // Only 1000.jpg under the real day dir. notes.txt (not .jpg) and the whole
    // 'not-a-day' dir (fails DAY_DIR_RE) are ignored.
    expect(n).toBe(1)
    expect(insertedRows().map((r) => r.imagePath)).toEqual([join(ROOT, '2026-07-14', '1000.jpg')])
  })

  it('returns 0 when the rewind root does not exist yet', async () => {
    fsMock.readdir.mockRejectedValue(new Error('ENOENT'))
    const n = await rebuildRewindIndexFromDisk()
    expect(n).toBe(0)
    expect(db.insertRewindFrame).not.toHaveBeenCalled()
  })

  it('NEVER deletes — unlink is not called on any path', async () => {
    seed({
      days: { '2026-07-14': ['1000.jpg', 'garbage.jpg'] },
      undecodable: ['garbage.jpg'],
      existingRows: []
    })
    await rebuildRewindIndexFromDisk()
    expect(fsMock.unlink).not.toHaveBeenCalled()
  })

  // MUTATION GUARD (single-flight): two rebuilds started at once share ONE run, so
  // each orphan is inserted exactly once. Both callers snapshot the same empty
  // "existing paths" set before inserting, so without the guard each would insert
  // every orphan → duplicate rows (the corruption this whole feature undoes). Remove
  // the `if (inFlight) return inFlight` guard in rebuildIndex.ts and this sees 4
  // inserts, not 2.
  it('single-flights concurrent runs — each orphan inserted exactly once', async () => {
    seed({ days: { '2026-07-14': ['1000.jpg', '2000.jpg'] } })
    const [a, b] = await Promise.all([rebuildRewindIndexFromDisk(), rebuildRewindIndexFromDisk()])
    expect(a).toBe(2)
    expect(b).toBe(2) // the second caller joined the same run, same count
    expect(db.insertRewindFrame).toHaveBeenCalledTimes(2) // once per orphan, not per caller
  })

  it('does NOT block a sequential re-run — the guard clears on completion', async () => {
    seed({ days: { '2026-07-14': ['1000.jpg'] } })
    await rebuildRewindIndexFromDisk()
    const afterFirst = fsMock.readdir.mock.calls.length
    expect(afterFirst).toBeGreaterThan(0)
    // A call after the first RESOLVED must scan again — the in-flight ref must have
    // been released, not stuck (which would make later rebuilds silent no-ops).
    await rebuildRewindIndexFromDisk()
    expect(fsMock.readdir.mock.calls.length).toBeGreaterThan(afterFirst)
  })
})
