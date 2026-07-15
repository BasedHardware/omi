// Proof that the embedding store's SQL does what the indexer assumes, in a REAL
// SQLite database.
//
// The statements under test are IMPORTED from ipc/rewindEmbeddingSql.ts, not
// re-declared here. That is the point: db.ts's better-sqlite3 can't load under
// plain-node vitest (Electron ABI), and the old version of this file coped by
// pasting a "verbatim" copy of each statement — which then drifted from
// production without a single test turning red (the work-query copy filtered
// `ocr_text != ''` long after production moved to `LENGTH(TRIM(ocr_text)) >= 10`;
// the paged-scan copy never grew the `LENGTH(v.vec)=…` guard). Importing the real
// statements makes that class of divergence impossible.
//
// Two things here are load-bearing enough to pin:
//   * RETENTION MUST REACH THE VECTORS. They are derived from the user's screen
//     content, there is no FK/CASCADE (foreign_keys is off), and a vector that
//     outlives its frame is exactly the data the user asked us to forget.
//   * The backfill predicate. If it returned frames that already have an
//     embedding, or frames too short to embed, the launch backfill would spin.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import { contentHash, l2Normalize, scanTopKBySimilarity } from './embedVector'
import { MIN_EMBED_TEXT_LEN } from './embedQueue'
import { bufferToVector, vectorToBuffer } from '../ipc/taskEmbeddingVector'
import { applyRewindEmbeddingSchema } from '../ipc/rewindEmbeddingSchema'
import {
  DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL,
  DROP_ORPHANED_EMBEDDING_VECTORS_SQL,
  rewindFramesNeedingEmbeddingSql,
  searchEmbeddingPageSql
} from '../ipc/rewindEmbeddingSql'

// rewind_frames is db.ts's, trimmed to the columns these queries project/touch —
// it is not part of the extracted embedding SQL, so it stays inline. The two
// embedding tables ARE extracted (rewindEmbeddingSchema), so they are created by
// the real DDL, not a copy.
const REWIND_FRAMES_DDL = `
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
`

// The real 2-dim toy vectors are 8 bytes (Float32 x 2). Production's guard expects
// a full 3072-dim / 12288-byte blob; the page SQL takes the size as a parameter
// precisely so this test can drive the identical guard with small vectors.
const TOY_BLOB_BYTES = 2 * Float32Array.BYTES_PER_ELEMENT

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
  db.prepare(DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL).run()
  db.prepare(DROP_ORPHANED_EMBEDDING_VECTORS_SQL).run()
}

const counts = (): { frames: number; mappings: number; vectors: number } => ({
  frames: (db.prepare('SELECT COUNT(*) AS n FROM rewind_frames').get() as { n: number }).n,
  mappings: (db.prepare('SELECT COUNT(*) AS n FROM rewind_embeddings').get() as { n: number }).n,
  vectors: (db.prepare('SELECT COUNT(*) AS n FROM rewind_embedding_vectors').get() as { n: number })
    .n
})

const needsEmbedding = (limit = 100): number[] =>
  (db.prepare(rewindFramesNeedingEmbeddingSql(0)).all(limit) as { id: number }[]).map((r) => r.id)

beforeEach(() => {
  db = new DatabaseSync(':memory:')
  db.exec(REWIND_FRAMES_DDL)
  applyRewindEmbeddingSchema(db) // the REAL embedding-table DDL
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

    db.prepare(DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL).run()
    db.prepare(DROP_ORPHANED_EMBEDDING_VECTORS_SQL).run()

    expect(counts()).toEqual({ frames: 0, mappings: 0, vectors: 0 })
  })

  // Mutation guard for the `WHERE hash IS NOT NULL` in the vector GC. `hash` is
  // nullable; SQLite's `x NOT IN (<set with NULL>)` is NULL (never true) for every
  // row, so a single NULL-hash mapping would make the vector DELETE match NOTHING
  // and every retired vector would orphan and survive "delete my history". Drop
  // that guard from DROP_ORPHANED_EMBEDDING_VECTORS_SQL and this test goes red.
  it('GCs an orphan vector even when a NULL-hash mapping is present', () => {
    // A live, real-hash frame + its vector.
    addFrame(1, 1000, 'live content')
    embedFrame(1, 'live content', [1, 0])
    // A second live frame whose mapping hash is NULL (the defensive edge the guard
    // exists for), plus an orphan vector no mapping references.
    addFrame(2, 2000, 'frame with null-hash mapping')
    db.prepare('INSERT INTO rewind_embeddings (frame_id, hash) VALUES (2, NULL)').run()
    db.prepare(
      `INSERT INTO rewind_embedding_vectors (hash, dim, model, vec, created_at)
       VALUES ('orphan-hash', 2, 'm', ?, 1)`
    ).run(vectorToBuffer(l2Normalize(Float32Array.from([1, 0]))))
    expect(counts()).toEqual({ frames: 2, mappings: 2, vectors: 2 })

    db.prepare(DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL).run() // both frames live: no-op
    db.prepare(DROP_ORPHANED_EMBEDDING_VECTORS_SQL).run()

    // The orphan is gone; the live vector survives. Without the NULL guard the
    // orphan would still be here (the DELETE would have matched nothing).
    const hashes = (
      db.prepare('SELECT hash FROM rewind_embedding_vectors ORDER BY hash').all() as {
        hash: string
      }[]
    ).map((r) => r.hash)
    expect(hashes).toEqual([contentHash('live content')])
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

  // The min-length floor, now that the test runs the REAL query. A frame whose OCR
  // is one char short of MIN_EMBED_TEXT_LEN must NOT be handed to the backfill —
  // the queue would refuse it, it would never earn an embedding row, and it would
  // be returned forever, stalling the sweep at the head of the newest-first page.
  // The old re-declared copy filtered `ocr_text != ''` and never checked this.
  it('excludes frames whose OCR text is below the min-length floor', () => {
    const belowLen = MIN_EMBED_TEXT_LEN - 1
    addFrame(1, 1000, 'x'.repeat(belowLen)) // 9 chars — too short
    addFrame(2, 2000, 'x'.repeat(MIN_EMBED_TEXT_LEN)) // 10 chars — exactly the floor
    addFrame(3, 3000, `   ${'x'.repeat(belowLen)}   `) // 9 non-space chars, padded — TRIM catches it

    // Only the ≥10-char frame qualifies; the short and whitespace-padded ones don't.
    expect(needsEmbedding()).toEqual([2])
  })

  // C3: a frame that failed this launch is excluded IN SQL, so the sweep can move
  // past it. Filtering it out afterwards made an all-failed page look like
  // "caught up" and silently abandoned the rest of the launch's budget.
  it('excludes the caller-supplied failed ids, so the sweep can advance past them', () => {
    addFrame(1, 3000, 'failed frame text')
    addFrame(2, 2000, 'good frame text')
    // The REAL query with one exclusion placeholder; bind the excluded id, then limit.
    const rows = db.prepare(rewindFramesNeedingEmbeddingSql(1)).all(1, 10) as { id: number }[]
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

    // The REAL paged query, incl. the EXISTS guard that skips vectors no live frame
    // references and the vec-size guard (driven with the toy blob size).
    const page = db.prepare(searchEmbeddingPageSql(TOY_BLOB_BYTES))
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

    const page = db.prepare(searchEmbeddingPageSql(TOY_BLOB_BYTES))
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

  // The vec-size guard (m-1 fix) pinned: a live-referenced but wrong-size vector
  // (a partial write) must be skipped, not fed to the ranker — a short page there
  // used to truncate the whole scan. Drop `LENGTH(v.vec) = …` and this goes red.
  it('skips a live vector whose blob is the wrong size', async () => {
    addFrame(1, 1000, 'good vector')
    embedFrame(1, 'good vector', [1, 0]) // 8-byte blob, matches TOY_BLOB_BYTES
    // A referenced vector with a truncated (4-byte) blob — a partial write.
    db.prepare('INSERT INTO rewind_embeddings (frame_id, hash) VALUES (2, ?)').run('short-hash')
    addFrame(2, 2000, 'short vector frame')
    db.prepare(
      `INSERT INTO rewind_embedding_vectors (hash, dim, model, vec, created_at)
       VALUES ('short-hash', 1, 'm', ?, 1)`
    ).run(Buffer.from([1, 2, 3, 4]))

    const page = db.prepare(searchEmbeddingPageSql(TOY_BLOB_BYTES))
    const rows = page.all(100, 0) as { hash: string }[]
    // Only the correctly-sized vector is returned to the scan.
    expect(rows.map((r) => r.hash)).toEqual([contentHash('good vector')])
  })
})
