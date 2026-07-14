// Proof that the embedding store's SQL does what the indexer assumes, in a REAL
// SQLite database. db.ts's better-sqlite3 can't load under plain-node vitest
// (Electron ABI), so — same pattern as rewindFtsSearch.test.ts — the DDL and the
// query shapes are replicated verbatim from db.ts and driven via node:sqlite,
// while the REAL vector codec + ranking (taskEmbeddingVector, topKBySimilarity)
// are exercised.
//
// The predicate under test is load-bearing: if it returned frames that already
// have a vector, the launch backfill would re-embed the same frames forever.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import { l2Normalize, topKBySimilarity } from './embedVector'
import { bufferToVector, vectorToBuffer } from '../ipc/taskEmbeddingVector'

// Verbatim from db.ts get() (rewind_frames trimmed to the columns these queries touch).
const SCHEMA = `
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
    indexed INTEGER NOT NULL DEFAULT 0,
    ocr_lines_json TEXT
  );
  CREATE TABLE rewind_embeddings (
    frame_id INTEGER PRIMARY KEY,
    dim INTEGER,
    model TEXT,
    vec BLOB,
    created_at INTEGER
  );
`

// The backfill's work list, verbatim from db.ts rewindFramesNeedingEmbedding().
const NEEDS_EMBEDDING = `
  SELECT rewind_frames.id, rewind_frames.ts FROM rewind_frames
    LEFT JOIN rewind_embeddings ON rewind_embeddings.frame_id = rewind_frames.id
   WHERE rewind_frames.indexed = 1
     AND rewind_frames.ocr_text IS NOT NULL AND rewind_frames.ocr_text != ''
     AND rewind_embeddings.frame_id IS NULL
   ORDER BY rewind_frames.ts DESC
   LIMIT ?
`

const UPSERT = `
  INSERT INTO rewind_embeddings (frame_id, dim, model, vec, created_at)
  VALUES (?, ?, ?, ?, ?)
  ON CONFLICT(frame_id) DO UPDATE SET
    dim = excluded.dim, model = excluded.model, vec = excluded.vec, created_at = excluded.created_at
`

let db: DatabaseSync

const addFrame = (id: number, ts: number, ocrText: string, indexed = 1): void => {
  db.prepare(
    'INSERT INTO rewind_frames (id, ts, ocr_text, image_path, indexed) VALUES (?, ?, ?, ?, ?)'
  ).run(id, ts, ocrText, `C:\\f\\${id}.jpg`, indexed)
}

const addVector = (frameId: number, values: number[]): void => {
  const vec = l2Normalize(Float32Array.from(values))
  db.prepare(UPSERT).run(frameId, vec.length, 'gemini-embedding-001', vectorToBuffer(vec), 1)
}

const needsEmbedding = (limit = 100): number[] =>
  (db.prepare(NEEDS_EMBEDDING).all(limit) as { id: number }[]).map((r) => r.id)

beforeEach(() => {
  db = new DatabaseSync(':memory:')
  db.exec(SCHEMA)
})

describe('the backfill work list', () => {
  it('returns only OCR-indexed frames that have no vector yet, newest first', () => {
    addFrame(1, 1000, 'has text')
    addFrame(2, 3000, 'has text too')
    addFrame(3, 2000, '') // OCR found nothing — nothing to embed
    addFrame(4, 4000, 'not OCRd yet', 0) // OCR hasn't run
    addVector(1, [1, 0, 0]) // already embedded

    expect(needsEmbedding()).toEqual([2]) // and NOT 1, 3, or 4
  })

  it('drops a frame out of the list once its vector is stored', () => {
    addFrame(1, 1000, 'text')
    expect(needsEmbedding()).toEqual([1])
    addVector(1, [1, 0, 0])
    // This is what makes the backfill resumable across launches with no cursor:
    // persisted work simply stops being returned.
    expect(needsEmbedding()).toEqual([])
  })

  it('honours the limit, taking the newest frames first', () => {
    addFrame(1, 1000, 'old')
    addFrame(2, 5000, 'newest')
    addFrame(3, 3000, 'middle')
    expect(needsEmbedding(2)).toEqual([2, 3])
  })
})

describe('vector storage', () => {
  it('round-trips a normalized vector through the BLOB column', () => {
    addFrame(1, 1000, 'text')
    addVector(1, [3, 4, 0])
    const row = db
      .prepare('SELECT dim, model, vec FROM rewind_embeddings WHERE frame_id = 1')
      .get() as {
      dim: number
      model: string
      vec: Uint8Array
    }
    expect(row.dim).toBe(3)
    expect(row.model).toBe('gemini-embedding-001')
    expect(row.vec.byteLength).toBe(12) // 3 floats
    const restored = bufferToVector(row.vec)
    expect(restored[0]).toBeCloseTo(0.6, 6) // still unit length
    expect(restored[1]).toBeCloseTo(0.8, 6)
  })

  it('replaces the vector on conflict rather than erroring or duplicating', () => {
    addFrame(1, 1000, 'text')
    addVector(1, [1, 0, 0])
    addVector(1, [0, 1, 0]) // re-embedded (e.g. the frame was re-OCRd)
    const rows = db.prepare('SELECT vec FROM rewind_embeddings').all() as { vec: Uint8Array }[]
    expect(rows).toHaveLength(1)
    expect([...bufferToVector(rows[0].vec)]).toEqual([0, 1, 0])
  })
})

describe('similarity search over stored rows', () => {
  it('ranks the stored frames by cosine similarity to the query', () => {
    addFrame(1, 1000, 'a')
    addFrame(2, 2000, 'b')
    addFrame(3, 3000, 'c')
    addVector(1, [0, 1]) // orthogonal to the query
    addVector(2, [1, 0]) // exact
    addVector(3, [1, 1]) // 45 degrees

    const rows = db.prepare('SELECT frame_id, vec FROM rewind_embeddings').all() as {
      frame_id: number
      vec: Uint8Array
    }[]
    const top = topKBySimilarity(
      rows.map((r) => ({ frameId: r.frame_id, vec: bufferToVector(r.vec) })),
      l2Normalize(Float32Array.from([1, 0])),
      2
    )
    expect(top.map((t) => t.frameId)).toEqual([2, 3])
    expect(top[0].similarity).toBeCloseTo(1, 5)
  })
})
