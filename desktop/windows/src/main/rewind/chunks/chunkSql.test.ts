// Proof that the chunk SQL does what the compactor assumes, in a REAL SQLite
// database, running the statements production runs (imported, never re-typed —
// see the header of rewindEmbeddingSql.ts for what re-typing them costs).
//
// The property under test throughout: a frame's JPEG is only ever given up in
// exchange for a chunk slot that actually exists, exactly once.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  CHUNK_BACKED_FRAME_COUNT_SQL,
  CLAIM_FRAME_INTO_CHUNK_SQL,
  COMPACTABLE_FRAMES_SQL,
  DELETE_FRAMES_IN_CHUNK_SQL,
  FRAMES_IN_CHUNK_SQL,
  IS_CHUNK_ABANDONED_SQL,
  REFERENCED_CHUNK_PATHS_SQL,
  TOMBSTONE_CHUNK_SQL
} from './chunkSql'
import { MIGRATIONS, runMigrations, type MigrationDb } from '../../ipc/dbMigrations'

// The pre-migration table, as db.ts's baseline creates it. Migration 3 is then
// run against it by the real migration runner, so this file also proves the
// migration produces a schema these statements work on.
const LEGACY_REWIND_FRAMES = `
  CREATE TABLE rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    process_name TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
  );
  CREATE TABLE local_conversation (id TEXT PRIMARY KEY);`

let db: DatabaseSync

function addFrame(o: {
  id: number
  ts: number
  indexed?: number
  imagePath?: string
  width?: number
  height?: number
}): void {
  db.prepare(
    'INSERT INTO rewind_frames (id, ts, image_path, width, height, indexed) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(
    o.id,
    o.ts,
    o.imagePath ?? `C:/rewind/2026-08-17/${o.ts}.jpg`,
    o.width ?? 1280,
    o.height ?? 720,
    o.indexed ?? 1
  )
}

function compactable(olderThan: number, limit = 100) {
  return db.prepare(COMPACTABLE_FRAMES_SQL).all(olderThan, limit) as {
    id: number
    ts: number
    imagePath: string
  }[]
}

function claim(id: number, chunkPath: string, offset: number): number {
  const abandoned = db.prepare(IS_CHUNK_ABANDONED_SQL).get(chunkPath) as { abandoned: number }
  if (abandoned.abandoned) return 0
  return db.prepare(CLAIM_FRAME_INTO_CHUNK_SQL).run(chunkPath, offset, id).changes as number
}

beforeEach(() => {
  db = new DatabaseSync(':memory:')
  db.exec(LEGACY_REWIND_FRAMES)
  runMigrations(db as unknown as MigrationDb, MIGRATIONS)
})

describe('migration 3', () => {
  it('adds the locator columns to an existing table', () => {
    const cols = (db.prepare('PRAGMA table_info(rewind_frames)').all() as { name: string }[]).map(
      (c) => c.name
    )
    expect(cols).toContain('chunk_path')
    expect(cols).toContain('chunk_offset')
  })

  it('leaves every existing row uncompacted', () => {
    // The default is the migration's entire behaviour for existing data: NULL
    // is what marks a frame as still JPEG-backed.
    addFrame({ id: 1, ts: 1000 })
    const row = db.prepare('SELECT chunk_path, chunk_offset FROM rewind_frames').get() as {
      chunk_path: string | null
      chunk_offset: number | null
    }
    expect(row.chunk_path).toBeNull()
    expect(row.chunk_offset).toBeNull()
  })

  it('creates the abandoned-chunk table', () => {
    const t = db
      .prepare(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rewind_abandoned_chunks'"
      )
      .get()
    expect(t).toBeTruthy()
  })

  it('is idempotent', () => {
    expect(() => runMigrations(db as unknown as MigrationDb, MIGRATIONS)).not.toThrow()
  })
})

describe('choosing what to compact', () => {
  it('offers an OCR-indexed, JPEG-backed, old-enough frame', () => {
    addFrame({ id: 1, ts: 1000 })
    expect(compactable(5000).map((f) => f.id)).toEqual([1])
  })

  it('never offers a frame OCR has not reached', () => {
    // The one that actually matters. ocrService.ts reads image_path for
    // indexed=0 frames and, when the file is gone, marks the frame indexed with
    // EMPTY text instead of failing — so compacting one of these does not error,
    // it silently destroys that frame's searchable text forever.
    addFrame({ id: 1, ts: 1000, indexed: 0 })
    expect(compactable(5000)).toHaveLength(0)
  })

  it('never offers a frame twice', () => {
    addFrame({ id: 1, ts: 1000 })
    claim(1, '2026-08-17/1-2.omichunk', 0)
    expect(compactable(5000)).toHaveLength(0)
  })

  it('excludes an already-compacted frame even if it still names a JPEG', () => {
    // The case that proves `chunk_path IS NULL` carries its own weight. The
    // normal claim also blanks image_path, so the two clauses mask each other
    // and either alone appears sufficient; a row written by hand separates
    // them. A frame in this state re-compacted would be pointed at a second
    // chunk while the first still claimed it.
    db.prepare(
      'INSERT INTO rewind_frames (id, ts, image_path, width, height, indexed, chunk_path, chunk_offset)' +
        " VALUES (1, 1000, 'C:/rewind/2026-08-17/1000.jpg', 1280, 720, 1, '2026-08-17/1-2.omichunk', 0)"
    ).run()
    expect(compactable(5000)).toHaveLength(0)
  })

  it('never offers a frame that already gave up its JPEG', () => {
    addFrame({ id: 1, ts: 1000, imagePath: '' })
    expect(compactable(5000)).toHaveLength(0)
  })

  it('respects the age cutoff the caller binds', () => {
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 9000 })
    expect(compactable(5000).map((f) => f.id)).toEqual([1])
  })

  it('returns frames in capture order', () => {
    // The planner's grouping and the resulting chunk offsets depend on it.
    addFrame({ id: 3, ts: 3000 })
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 2000 })
    expect(compactable(5000).map((f) => f.ts)).toEqual([1000, 2000, 3000])
  })

  it('orders frames sharing a millisecond deterministically', () => {
    addFrame({ id: 9, ts: 1000 })
    addFrame({ id: 4, ts: 1000 })
    expect(compactable(5000).map((f) => f.id)).toEqual([4, 9])
  })

  it('honours the limit', () => {
    for (let i = 1; i <= 10; i++) addFrame({ id: i, ts: i * 100 })
    expect(compactable(5000, 3)).toHaveLength(3)
  })
})

describe('claiming a frame into a chunk', () => {
  const CHUNK = '2026-08-17/1000-3000.omichunk'

  it('records the slot and surrenders the JPEG path', () => {
    addFrame({ id: 1, ts: 1000 })
    expect(claim(1, CHUNK, 4)).toBe(1)
    const row = db
      .prepare('SELECT chunk_path, chunk_offset, image_path FROM rewind_frames')
      .get() as {
      chunk_path: string
      chunk_offset: number
      image_path: string
    }
    expect(row.chunk_path).toBe(CHUNK)
    expect(row.chunk_offset).toBe(4)
    // '' rather than NULL: the column is NOT NULL and readers compare it as a
    // string. macOS carries the identical compromise for the same reason.
    expect(row.image_path).toBe('')
  })

  it('refuses to re-point a frame another chunk already owns', () => {
    // Without the guard, a re-run holding a stale plan would silently move a
    // frame to a chunk that does not contain its pixels.
    addFrame({ id: 1, ts: 1000 })
    expect(claim(1, CHUNK, 0)).toBe(1)
    expect(claim(1, '2026-08-17/9000-9999.omichunk', 0)).toBe(0)
    const row = db.prepare('SELECT chunk_path FROM rewind_frames').get() as { chunk_path: string }
    expect(row.chunk_path).toBe(CHUNK)
  })

  it('refuses to claim into a tombstoned chunk', () => {
    // An abandoned chunk's file may already be gone; a frame pointed into it
    // would be unreadable forever.
    addFrame({ id: 1, ts: 1000 })
    db.prepare(TOMBSTONE_CHUNK_SQL).run(CHUNK)
    expect(claim(1, CHUNK, 0)).toBe(0)
    const row = db.prepare('SELECT chunk_path, image_path FROM rewind_frames').get() as {
      chunk_path: string | null
      image_path: string
    }
    expect(row.chunk_path).toBeNull()
    expect(row.image_path).not.toBe('')
  })

  it('reads a chunk back in offset order, not insertion order', () => {
    // Offsets are deliberately the REVERSE of row order. With offsets ascending
    // in row order, SQLite returns them correctly with or without the ORDER BY,
    // so the clause could be deleted without a test noticing.
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 2000 })
    addFrame({ id: 3, ts: 3000 })
    claim(1, CHUNK, 2)
    claim(2, CHUNK, 1)
    claim(3, CHUNK, 0)
    const rows = db.prepare(FRAMES_IN_CHUNK_SQL).all(CHUNK) as { id: number; chunkOffset: number }[]
    expect(rows.map((r) => r.chunkOffset)).toEqual([0, 1, 2])
    expect(rows.map((r) => r.id)).toEqual([3, 2, 1])
  })
})

describe('abandoning a chunk', () => {
  const CHUNK = '2026-08-17/1000-3000.omichunk'

  it('tombstones it and drops the frames pointing into it', () => {
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 2000 })
    claim(1, CHUNK, 0)
    claim(2, CHUNK, 1)

    db.prepare(TOMBSTONE_CHUNK_SQL).run(CHUNK)
    const deleted = db.prepare(DELETE_FRAMES_IN_CHUNK_SQL).run(CHUNK).changes
    expect(deleted).toBe(2)
    expect((db.prepare(IS_CHUNK_ABANDONED_SQL).get(CHUNK) as { abandoned: number }).abandoned).toBe(
      1
    )
  })

  it('leaves frames in other chunks alone', () => {
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 2000 })
    claim(1, CHUNK, 0)
    claim(2, '2026-08-17/4000-5000.omichunk', 0)
    db.prepare(DELETE_FRAMES_IN_CHUNK_SQL).run(CHUNK)
    expect(db.prepare('SELECT COUNT(*) AS n FROM rewind_frames').get()).toEqual({ n: 1 })
  })

  it('is safe to repeat after a crash between its two statements', () => {
    addFrame({ id: 1, ts: 1000 })
    claim(1, CHUNK, 0)
    db.prepare(TOMBSTONE_CHUNK_SQL).run(CHUNK) // crash here
    expect(() => db.prepare(TOMBSTONE_CHUNK_SQL).run(CHUNK)).not.toThrow()
    expect(db.prepare(DELETE_FRAMES_IN_CHUNK_SQL).run(CHUNK).changes).toBe(1)
    expect(db.prepare(DELETE_FRAMES_IN_CHUNK_SQL).run(CHUNK).changes).toBe(0)
  })
})

describe('finding live chunks', () => {
  it('lists each referenced chunk once', () => {
    const a = '2026-08-17/1-2.omichunk'
    const b = '2026-08-17/3-4.omichunk'
    for (let i = 1; i <= 4; i++) addFrame({ id: i, ts: i * 1000 })
    claim(1, a, 0)
    claim(2, a, 1)
    claim(3, b, 0)
    const paths = (db.prepare(REFERENCED_CHUNK_PATHS_SQL).all() as { chunk_path: string }[]).map(
      (r) => r.chunk_path
    )
    expect(paths.sort()).toEqual([a, b])
  })

  it('stops listing a chunk once its last frame is gone', () => {
    // This is what makes the file collectable: retention deletes rows by age,
    // and the chunk becomes garbage when the last one goes.
    const a = '2026-08-17/1-2.omichunk'
    addFrame({ id: 1, ts: 1000 })
    claim(1, a, 0)
    db.prepare('DELETE FROM rewind_frames WHERE id = 1').run()
    expect(db.prepare(REFERENCED_CHUNK_PATHS_SQL).all()).toEqual([])
  })

  it('counts chunk-backed frames for the status surface', () => {
    addFrame({ id: 1, ts: 1000 })
    addFrame({ id: 2, ts: 2000 })
    claim(1, '2026-08-17/1-2.omichunk', 0)
    expect(db.prepare(CHUNK_BACKED_FRAME_COUNT_SQL).get()).toEqual({ n: 1 })
  })
})
