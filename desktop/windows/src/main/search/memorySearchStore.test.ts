// Proven against a REAL SQLite database via node:sqlite — better-sqlite3 in this
// repo is built for Electron's ABI and won't load under plain-node vitest (same
// reason dbMigrations.test.ts / dbWipe.test.ts use node:sqlite).
//
// MEMORY_SEARCH_SCHEMA is IMPORTED, not re-declared, so this exercises the exact
// DDL production runs. The base `memories` table below is a copy of db.ts's Track
// 3 block; the last test pins what actually happens when the two drift.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { MEMORY_SEARCH_SCHEMA, searchMemoriesFts, type MemorySearchDb } from './memorySearchStore'

/** Verbatim from db.ts's `CREATE TABLE IF NOT EXISTS memories` block. */
const MEMORIES_SCHEMA = `
  CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    source_app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    context_summary TEXT NOT NULL DEFAULT '',
    confidence REAL,
    screenshot_id INTEGER,
    backend_id TEXT,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
`

const EPOCH = 1_723_800_000_000

interface Seed {
  content: string
  category?: string
  sourceApp?: string
  windowTitle?: string
  contextSummary?: string
  createdAt?: number
}

const open = (): MemorySearchDb & { close: () => void } => {
  const db = new DatabaseSync(':memory:')
  db.exec(MEMORIES_SCHEMA)
  db.exec(MEMORY_SEARCH_SCHEMA)
  return db as unknown as MemorySearchDb & { close: () => void }
}

const insert = (db: MemorySearchDb, seed: Seed): number => {
  db.prepare(
    `INSERT INTO memories
       (content, category, source_app, window_title, context_summary, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(
    seed.content,
    seed.category ?? 'personal',
    seed.sourceApp ?? 'Slack',
    seed.windowTitle ?? '',
    seed.contextSummary ?? '',
    seed.createdAt ?? EPOCH
  )
  const row = db.prepare('SELECT last_insert_rowid() AS id').get() as { id: number }
  return row.id
}

describe('memories full-text index', () => {
  it('finds a memory by a word in its content', () => {
    const db = open()
    insert(db, { content: 'Prefers oat milk in coffee' })
    insert(db, { content: 'Runs on Tuesday mornings' })

    const hits = searchMemoriesFts(db, 'coffee*')
    expect(hits.map((h) => h.content)).toEqual(['Prefers oat milk in coffee'])
    expect(hits[0]).toMatchObject({ category: 'personal', sourceApp: 'Slack', createdAt: EPOCH })
  })

  it('searches the context summary as well as the content', () => {
    const db = open()
    insert(db, { content: 'Ships on Fridays', contextSummary: 'discussed during the release sync' })
    expect(searchMemoriesFts(db, 'release*').length).toBe(1)
  })

  it('never matches on the raw window title', () => {
    const db = open()
    insert(db, {
      content: 'Prefers async standups',
      windowTitle: 'MyChart - Lab Results'
    })
    // Window titles are unfiltered PII that memory/persist.ts deliberately keeps
    // local. Indexing them would make that PII reachable by typing a fragment of
    // it into a search box.
    expect(searchMemoriesFts(db, 'mychart*')).toEqual([])
    expect(searchMemoriesFts(db, 'lab*')).toEqual([])
    // The curated content is still findable.
    expect(searchMemoriesFts(db, 'standups*').length).toBe(1)
  })

  it('breaks equal relevance ties newest first', () => {
    const db = open()
    insert(db, { content: 'budget review', createdAt: EPOCH })
    insert(db, { content: 'budget review', createdAt: EPOCH + 60_000 })
    insert(db, { content: 'budget review', createdAt: EPOCH + 30_000 })

    expect(searchMemoriesFts(db, 'budget*').map((h) => h.createdAt)).toEqual([
      EPOCH + 60_000,
      EPOCH + 30_000,
      EPOCH
    ])
  })

  it('drops a memory from the index when it is deleted', () => {
    const db = open()
    const id = insert(db, { content: 'Allergic to penicillin' })
    expect(searchMemoriesFts(db, 'penicillin*').length).toBe(1)

    db.prepare('DELETE FROM memories WHERE id = ?').run(id)
    // The delete trigger is what makes memories_fts safe to leave out of
    // USER_DATA_TABLES: an account switch deletes the rows and the index follows.
    expect(searchMemoriesFts(db, 'penicillin*')).toEqual([])
  })

  it('follows an edit rather than keeping the old text findable', () => {
    const db = open()
    const id = insert(db, { content: 'Drinks decaf' })
    db.prepare('UPDATE memories SET content = ? WHERE id = ?').run('Drinks espresso', id)

    expect(searchMemoriesFts(db, 'decaf*')).toEqual([])
    expect(searchMemoriesFts(db, 'espresso*').length).toBe(1)
  })

  it('indexes memories that already existed when the index was created', () => {
    // The triggers only fire on new writes, so an existing install needs the
    // one-time rebuild that migration v3 runs.
    const db = new DatabaseSync(':memory:') as unknown as MemorySearchDb
    db.exec(MEMORIES_SCHEMA)
    insert(db, { content: 'Signed the lease in March' })
    db.exec(MEMORY_SEARCH_SCHEMA)
    expect(searchMemoriesFts(db, 'lease*')).toEqual([])

    db.exec("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
    expect(searchMemoriesFts(db, 'lease*').length).toBe(1)
  })

  it('respects the result limit', () => {
    const db = open()
    for (let i = 0; i < 10; i += 1) insert(db, { content: `standup note ${i}` })
    expect(searchMemoriesFts(db, 'standup*', 4).length).toBe(4)
  })

  it('returns nothing for an empty match rather than scanning', () => {
    const db = open()
    insert(db, { content: 'anything' })
    expect(searchMemoriesFts(db, '')).toEqual([])
  })

  it('fails loudly on the first write if the base table drifts', () => {
    // The triggers read new.content / new.context_summary / new.source_app off
    // `memories`. SQLite does NOT resolve those columns when the trigger is
    // created, so a rename in db.ts installs cleanly and then throws on the next
    // memory insert. Pinned because that makes a rename break memory WRITES, not
    // just search: whoever renames the column needs to see this test, not a
    // silently empty search box.
    const db = new DatabaseSync(':memory:')
    db.exec(`CREATE TABLE memories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      body TEXT NOT NULL,
      category TEXT NOT NULL,
      source_app TEXT NOT NULL DEFAULT '',
      context_summary TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL
    );`)
    expect(() => db.exec(MEMORY_SEARCH_SCHEMA)).not.toThrow()
    expect(() =>
      db
        .prepare(`INSERT INTO memories (body, category, created_at) VALUES (?, ?, ?)`)
        .run('drifted', 'personal', EPOCH)
    ).toThrow(/no such column: new\.content/)
  })
})
