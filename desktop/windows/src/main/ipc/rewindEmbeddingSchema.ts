// Schema for the Rewind semantic-search tables, and the migration that carries a
// PR0-era database onto it.
//
// This lives OUTSIDE db.ts on purpose. db.ts imports better-sqlite3 (Electron
// ABI) and `electron`, so it cannot be loaded under plain-node vitest — which is
// why every schema test so far RE-DECLARED db.ts's SQL, and why a bug that only
// exists in the real bootstrap ordering (an index built on a column a legacy
// table does not have) could pass a full green suite. The DDL and the migration
// are therefore exported from here as the single source of truth, db.ts splices
// them into its bootstrap, and the tests run the SAME statements against a real
// (node:sqlite) database.
//
// Structural `MigrationDb` typing, for the same reason as dbMigrations.ts: it is
// satisfied by both better-sqlite3 (production) and node:sqlite's DatabaseSync
// (tests), with no driver import here.
import type { MigrationDb } from './dbMigrations'

/**
 * The two tables.
 *
 * Two, because consecutive screenshots of a mostly-static screen carry
 * BYTE-IDENTICAL OCR text: `rewind_embeddings` maps each frame to its content
 * hash (~8 bytes), and `rewind_embedding_vectors` stores ONE 12KB vector per
 * unique hash. A vector per frame would amplify the store by the duplicate ratio
 * (~20x — the same ratio that makes the API-side dedup worth doing) while every
 * duplicate frame stays equally findable either way.
 *
 * `rewind_embedding_vectors` keeps dim/model/created_at as metadata; the legacy
 * copies of those columns on `rewind_embeddings` are gone (see
 * `migrateRewindEmbeddingSchema`).
 */
export const REWIND_EMBEDDING_DDL = `
  CREATE TABLE IF NOT EXISTS rewind_embeddings (
    frame_id INTEGER PRIMARY KEY,
    hash TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_rewind_embeddings_hash ON rewind_embeddings(hash);
  CREATE TABLE IF NOT EXISTS rewind_embedding_vectors (
    hash TEXT PRIMARY KEY,
    dim INTEGER,
    model TEXT,
    vec BLOB,
    created_at INTEGER
  );
`

/**
 * Carry a database created by shipped `main` onto the shape above. MUST run
 * BEFORE `REWIND_EMBEDDING_DDL`.
 *
 * PR0 shipped `rewind_embeddings(frame_id, dim, model, vec, created_at)` — no
 * `hash` column — and nothing ever wrote to it. On such a database
 * `CREATE TABLE IF NOT EXISTS` is a no-op, so the table keeps its old shape; the
 * `CREATE INDEX … (hash)` that follows then references a column that does not
 * exist and SQLite raises `no such column: hash`, taking down the whole bootstrap
 * `exec` — and with it `get()`, which is the singleton behind EVERY db-backed IPC
 * handler (conversations, chat, insights, KG). The app is dead on first launch
 * after the upgrade, not merely missing semantic search.
 *
 * Adding the column afterwards (an `ALTER TABLE … ADD COLUMN`) cannot fix that:
 * the exec has already thrown. The table has to be brought to the new shape
 * BEFORE the DDL runs, and since it has never held a row, dropping it is lossless
 * — the same argument (and the same helper) as the local_kg_* tables in db.ts.
 */
function migrateRewindEmbeddingSchema(d: MigrationDb): void {
  const exists = d
    .prepare("SELECT 1 AS x FROM sqlite_master WHERE type='table' AND name='rewind_embeddings'")
    .get() as { x: number } | undefined
  if (!exists) return
  const cols = d.prepare('PRAGMA table_info(rewind_embeddings)').all() as { name: string }[]
  if (!cols.some((c) => c.name === 'hash')) d.exec('DROP TABLE rewind_embeddings')
}

/**
 * Bring the Rewind embedding tables to their current shape: migrate first, then
 * create. Exported as ONE call precisely so the two halves cannot drift apart —
 * the ordering IS the fix, and a caller that could get it wrong is the bug.
 * Idempotent; safe on a fresh database, a PR0-era one, and a current one.
 */
export function applyRewindEmbeddingSchema(d: MigrationDb): void {
  migrateRewindEmbeddingSchema(d)
  d.exec(REWIND_EMBEDDING_DDL)
}
