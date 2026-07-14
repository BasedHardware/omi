// Proof that the embedding store's SQL does what the indexer assumes, in a REAL
// SQLite database. db.ts's better-sqlite3 can't load under plain-node vitest
// (Electron ABI), so — same pattern as rewindFtsSearch.test.ts — the DDL and the
// query shapes are replicated verbatim from db.ts and driven via node:sqlite,
// while the REAL vector codec + ranking (taskEmbeddingVector, scanTopKBySimilarity)
// are exercised.
//
// Two things here are load-bearing enough to pin:
//   * RETENTION MUST REACH THE VECTORS. They are derived from the user's screen
//     content, there is no FK/CASCADE (foreign_keys is off), and a vector that
//     outlives its frame is exactly the data the user asked us to forget.
//   * The backfill predicate. If it returned frames that already have an
//     embedding, the launch backfill would re-embed the same frames forever.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import { contentHash, l2Normalize, scanTopKBySimilarity } from './embedVector'
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
    hash TEXT
  );
  CREATE INDEX idx_rewind_embeddings_hash ON rewind_embeddings(hash);
  CREATE TABLE rewind_embedding_vectors (
    hash TEXT PRIMARY KEY,
    dim INTEGER,
    model TEXT,
    vec BLOB,
    created_at INTEGER
  );
`

// The backfill's work list, verbatim from db.ts rewindFramesNeedingEmbedding().
const NEEDS_EMBEDDING = `
  SELECT rewind_frames.id FROM rewind_frames
    LEFT JOIN rewind_embeddings ON rewind_embeddings.frame_id = rewind_frames.id
   WHERE rewind_frames.indexed = 1
     AND rewind_frames.ocr_text IS NOT NULL AND rewind_frames.ocr_text != ''
     AND rewind_embeddings.frame_id IS NULL
   ORDER BY rewind_frames.ts DESC
   LIMIT ?
`

// The orphan GC, verbatim from db.ts dropOrphanedEmbeddingsOn().
const DROP_ORPHAN_MAPPINGS =
  'DELETE FROM rewind_embeddings WHERE frame_id NOT IN (SELECT id FROM rewind_frames)'
const DROP_ORPHAN_VECTORS = `
  DELETE FROM rewind_embedding_vectors
   WHERE hash NOT IN (SELECT hash FROM rewind_embeddings WHERE hash IS NOT NULL)
`

let db: DatabaseSync

const addFrame = (id: number, ts: number, ocrText: string, indexed = 1): void => {
  db.prepare(
    'INSERT INTO rewind_frames (id, ts, ocr_text, image_path, indexed) VALUES (?, ?, ?, ?, ?)'
  ).run(id, ts, ocrText, `C:\\f\\${id}.jpg`, indexed)
}

/** The real upsert path: one vector per unique content, one mapping per frame. */
const embedFrame = (frameId: number, text: string, values: number[]): void => {
  const hash = contentHash(text)
  const vec = l2Normalize(Float32Array.from(values))
  db.prepare(
    `INSERT INTO rewind_embedding_vectors (hash, dim, model, vec, created_at)
     VALUES (?, ?, ?, ?, ?) ON CONFLICT(hash) DO UPDATE SET vec = excluded.vec`
  ).run(hash, vec.length, 'gemini-embedding-001', vectorToBuffer(vec), 1)
  db.prepare(
    `INSERT INTO rewind_embeddings (frame_id, hash) VALUES (?, ?)
     ON CONFLICT(frame_id) DO UPDATE SET hash = excluded.hash`
  ).run(frameId, hash)
}

const pruneOlderThan = (cutoff: number): void => {
  db.prepare('DELETE FROM rewind_frames WHERE ts < ?').run(cutoff)
  db.prepare(DROP_ORPHAN_MAPPINGS).run()
  db.prepare(DROP_ORPHAN_VECTORS).run()
}

const counts = (): { frames: number; mappings: number; vectors: number } => ({
  frames: (db.prepare('SELECT COUNT(*) AS n FROM rewind_frames').get() as { n: number }).n,
  mappings: (db.prepare('SELECT COUNT(*) AS n FROM rewind_embeddings').get() as { n: number }).n,
  vectors: (db.prepare('SELECT COUNT(*) AS n FROM rewind_embedding_vectors').get() as { n: number })
    .n
})

const needsEmbedding = (limit = 100): number[] =>
  (db.prepare(NEEDS_EMBEDDING).all(limit) as { id: number }[]).map((r) => r.id)

beforeEach(() => {
  db = new DatabaseSync(':memory:')
  db.exec(SCHEMA)
})

describe('retention (privacy)', () => {
  // C1: the vector is derived from the user's screen. Retention deleting the frame
  // but keeping the vector means a 14-day retention setting is silently not honored.
  it('deletes the vectors of pruned frames, not just the frames', () => {
    addFrame(1, 1000, 'old secret content')
    addFrame(2, 9000, 'recent content')
    embedFrame(1, 'old secret content', [1, 0])
    embedFrame(2, 'recent content', [0, 1])
    expect(counts()).toEqual({ frames: 2, mappings: 2, vectors: 2 })

    pruneOlderThan(5000)

    // The pruned frame's vector is GONE — not merely unreferenced.
    expect(counts()).toEqual({ frames: 1, mappings: 1, vectors: 1 })
    const left = db.prepare('SELECT hash FROM rewind_embedding_vectors').all() as { hash: string }[]
    expect(left[0].hash).toBe(contentHash('recent content'))
  })

  // The shared-vector case: content still referenced by a live frame must SURVIVE
  // the prune, or pruning one old frame would blind the search for a recent one.
  it('keeps a shared vector while any live frame still references it', () => {
    addFrame(1, 1000, 'same screen text')
    addFrame(2, 9000, 'same screen text')
    embedFrame(1, 'same screen text', [1, 0])
    embedFrame(2, 'same screen text', [1, 0])
    expect(counts()).toEqual({ frames: 2, mappings: 2, vectors: 1 }) // ONE vector, two frames

    pruneOlderThan(5000)

    expect(counts()).toEqual({ frames: 1, mappings: 1, vectors: 1 }) // still findable
  })

  it('sweeps embeddings orphaned by a frame delete that skipped the GC', () => {
    addFrame(1, 1000, 'leaked content')
    embedFrame(1, 'leaked content', [1, 0])
    // Simulate what an earlier build of this feature left behind: the frame is
    // gone, but its vector was never cleaned up.
    db.prepare('DELETE FROM rewind_frames WHERE id = 1').run()
    expect(counts()).toEqual({ frames: 0, mappings: 1, vectors: 1 })

    db.prepare(DROP_ORPHAN_MAPPINGS).run()
    db.prepare(DROP_ORPHAN_VECTORS).run()

    expect(counts()).toEqual({ frames: 0, mappings: 0, vectors: 0 })
  })
})

describe('storage (one vector per unique content)', () => {
  // M4: a 12KB vector per FRAME amplifies the store by the duplicate ratio (~20x).
  it('stores ONE vector for many duplicate frames, all of them still findable', () => {
    for (let i = 1; i <= 10; i++) {
      addFrame(i, i * 1000, 'identical screen text')
      embedFrame(i, 'identical screen text', [1, 0])
    }
    const c = counts()
    expect(c.frames).toBe(10)
    expect(c.mappings).toBe(10) // every frame is still mapped...
    expect(c.vectors).toBe(1) // ...to a single stored vector

    // And all ten frames come back from a similarity hit on that one vector.
    const hit = db
      .prepare('SELECT frame_id FROM rewind_embeddings WHERE hash = ?')
      .all(contentHash('identical screen text')) as { frame_id: number }[]
    expect(hit).toHaveLength(10)
  })
})

describe('the backfill work list', () => {
  it('returns only OCR-indexed frames that have no embedding yet, newest first', () => {
    addFrame(1, 1000, 'has text')
    addFrame(2, 3000, 'has text too')
    addFrame(3, 2000, '') // OCR found nothing — nothing to embed
    addFrame(4, 4000, 'not OCRd yet', 0) // OCR hasn't run
    embedFrame(1, 'has text', [1, 0]) // already embedded

    expect(needsEmbedding()).toEqual([2]) // and NOT 1, 3, or 4
  })

  it('drops a frame out of the list once its embedding is stored', () => {
    addFrame(1, 1000, 'text content')
    expect(needsEmbedding()).toEqual([1])
    embedFrame(1, 'text content', [1, 0])
    // This is what makes the backfill resumable across launches with no cursor:
    // persisted work simply stops being returned.
    expect(needsEmbedding()).toEqual([])
  })

  // C3: a frame that failed this launch is excluded IN SQL, so the sweep can move
  // past it. Filtering it out afterwards made an all-failed page look like
  // "caught up" and silently abandoned the rest of the launch's budget.
  it('excludes the caller-supplied failed ids, so the sweep can advance past them', () => {
    addFrame(1, 3000, 'failed frame text')
    addFrame(2, 2000, 'good frame text')
    const rows = db
      .prepare(
        `SELECT rewind_frames.id FROM rewind_frames
           LEFT JOIN rewind_embeddings ON rewind_embeddings.frame_id = rewind_frames.id
          WHERE rewind_frames.indexed = 1
            AND rewind_frames.ocr_text != ''
            AND rewind_embeddings.frame_id IS NULL
            AND rewind_frames.id NOT IN (?)
          ORDER BY rewind_frames.ts DESC
          LIMIT ?`
      )
      .all(1, 10) as { id: number }[]
    // Frame 1 (the newest, and the one that failed) is skipped — frame 2 is reached.
    expect(rows.map((r) => r.id)).toEqual([2])
  })
})

describe('similarity search over stored rows', () => {
  it('ranks stored content by cosine similarity, scanning in bounded pages', async () => {
    addFrame(1, 1000, 'orthogonal content')
    addFrame(2, 2000, 'exact match content')
    addFrame(3, 3000, 'diagonal content')
    embedFrame(1, 'orthogonal content', [0, 1])
    embedFrame(2, 'exact match content', [1, 0])
    embedFrame(3, 'diagonal content', [1, 1])

    // The real paged query from db.ts searchRewindEmbeddings, incl. the EXISTS
    // guard that skips vectors no live frame references.
    const page = db.prepare(
      `SELECT v.hash AS hash, v.vec AS vec FROM rewind_embedding_vectors v
        WHERE EXISTS (SELECT 1 FROM rewind_embeddings e WHERE e.hash = v.hash)
        ORDER BY v.hash LIMIT ? OFFSET ?`
    )
    const top = await scanTopKBySimilarity(
      (offset, limit) =>
        (page.all(limit, offset) as { hash: string; vec: Uint8Array }[]).map((r) => ({
          hash: r.hash,
          vec: bufferToVector(r.vec)
        })),
      l2Normalize(Float32Array.from([1, 0])),
      2,
      async () => {},
      2 // page size — forces more than one page over 3 rows
    )

    expect(top.map((t) => t.hash)).toEqual([
      contentHash('exact match content'),
      contentHash('diagonal content')
    ])
    expect(top[0].similarity).toBeCloseTo(1, 5)
  })

  it('skips a vector no live frame references, so an orphan can never be a hit', async () => {
    addFrame(1, 1000, 'live content')
    embedFrame(1, 'live content', [1, 0])
    // An orphan vector with a PERFECT match to the query — it must still not win.
    db.prepare(
      `INSERT INTO rewind_embedding_vectors (hash, dim, model, vec, created_at)
       VALUES ('orphan', 2, 'm', ?, 1)`
    ).run(vectorToBuffer(l2Normalize(Float32Array.from([1, 0]))))

    const page = db.prepare(
      `SELECT v.hash AS hash, v.vec AS vec FROM rewind_embedding_vectors v
        WHERE EXISTS (SELECT 1 FROM rewind_embeddings e WHERE e.hash = v.hash)
        ORDER BY v.hash LIMIT ? OFFSET ?`
    )
    const top = await scanTopKBySimilarity(
      (offset, limit) =>
        (page.all(limit, offset) as { hash: string; vec: Uint8Array }[]).map((r) => ({
          hash: r.hash,
          vec: bufferToVector(r.vec)
        })),
      l2Normalize(Float32Array.from([1, 0])),
      5,
      async () => {}
    )
    expect(top.map((t) => t.hash)).toEqual([contentHash('live content')])
  })
})
