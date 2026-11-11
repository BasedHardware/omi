// C1 regression: the app must still OPEN on a database that shipped `main` created.
//
// This runs db.ts's REAL bootstrap statements — imported, not re-typed. That
// distinction is the whole point of the bug: every other schema test in this repo
// re-declares db.ts's SQL from scratch, so all 58 of them stayed green while the
// shipped bootstrap threw `no such column: hash` on any upgraded database and took
// down every db-backed IPC handler with it (conversations, chat, insights, KG —
// not just Rewind, because `get()` is one shared, un-try/caught singleton).
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { applyRewindEmbeddingSchema } from './rewindEmbeddingSchema'

/** rewind_embeddings EXACTLY as shipped `main` (PR0) creates it: vector-per-frame,
 *  no `hash` column, no index, and no rewind_embedding_vectors table at all.
 *  Verbatim from `git show origin/main:…/ipc/db.ts`. */
const PR0_SCHEMA = `
  CREATE TABLE IF NOT EXISTS rewind_embeddings (
    frame_id INTEGER PRIMARY KEY,
    dim INTEGER,
    model TEXT,
    vec BLOB,
    created_at INTEGER
  );
`

function columnsOf(db: DatabaseSync, table: string): string[] {
  return (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map((c) => c.name)
}

function tableExists(db: DatabaseSync, table: string): boolean {
  return (
    db.prepare("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name=?").get(table) !==
    undefined
  )
}

describe('rewind embedding schema bootstrap', () => {
  it('opens a PR0-era database without throwing, and migrates it to the hashed shape', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(PR0_SCHEMA) // this is what a user upgrading from a shipped build has

    // Before the fix this threw `no such column: hash` — CREATE TABLE IF NOT EXISTS
    // was a no-op on the legacy table, and the CREATE INDEX then indexed a column
    // that did not exist.
    expect(() => applyRewindEmbeddingSchema(db)).not.toThrow()

    // The legacy table is gone and the current one is in place. (Dropping is
    // lossless: PR0 never wrote a single row to it.)
    expect(columnsOf(db, 'rewind_embeddings').sort()).toEqual(['frame_id', 'hash'])
    expect(tableExists(db, 'rewind_embedding_vectors')).toBe(true)

    // And the schema it produced actually works end to end.
    db.exec("INSERT INTO rewind_embeddings (frame_id, hash) VALUES (1, 'abc')")
    expect(db.prepare('SELECT hash FROM rewind_embeddings WHERE frame_id = 1').get()).toEqual({
      hash: 'abc'
    })
    db.close()
  })

  it('creates both tables on a fresh database', () => {
    const db = new DatabaseSync(':memory:')
    applyRewindEmbeddingSchema(db)
    expect(columnsOf(db, 'rewind_embeddings').sort()).toEqual(['frame_id', 'hash'])
    expect(columnsOf(db, 'rewind_embedding_vectors').sort()).toEqual([
      'created_at',
      'dim',
      'hash',
      'model',
      'vec'
    ])
    db.close()
  })

  it('is idempotent — a second launch preserves the rows of the first', () => {
    const db = new DatabaseSync(':memory:')
    applyRewindEmbeddingSchema(db)
    db.exec("INSERT INTO rewind_embeddings (frame_id, hash) VALUES (7, 'keep-me')")

    applyRewindEmbeddingSchema(db) // relaunch

    // The current table must NOT be dropped — only a table missing `hash` is legacy.
    expect(db.prepare('SELECT COUNT(*) AS n FROM rewind_embeddings').get()).toEqual({ n: 1 })
    db.close()
  })
})
