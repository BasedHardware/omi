// Proves the `local_conversation` created_at index (from the SAME importable DDL
// db.ts ships) flips listLocalConversations()'s read from a full scan + temp-b-tree
// sort to an index-ordered scan. Run against a REAL SQLite via node:sqlite —
// db.ts's better-sqlite3 is rebuilt for Electron's ABI and can't load under
// plain-node vitest (same constraint as dbSchema.track4.test.ts).
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { LOCAL_CONVERSATION_SCHEMA } from './localConversationSchema'

// Minimal local_conversation baseline (the columns the read query needs). The
// TABLE is not what this test guards against drift — the INDEX is, and that comes
// from the imported LOCAL_CONVERSATION_SCHEMA below, not a re-declared copy.
const BASE = `
  CREATE TABLE local_conversation (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER NOT NULL,
    transcript TEXT NOT NULL,
    created_at INTEGER NOT NULL
  );
`

// The stable shape of listLocalConversations()'s read (db.ts). The SELECT column
// list does not affect the planner's ORDER BY decision, so the bare form is the
// faithful probe.
const READ_QUERY = 'SELECT * FROM local_conversation ORDER BY created_at DESC'

function makeDb(withIndex: boolean): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec(BASE)
  if (withIndex) db.exec(LOCAL_CONVERSATION_SCHEMA)
  // A few rows so the planner has something to order.
  const insert = db.prepare(
    'INSERT INTO local_conversation (id, started_at, ended_at, transcript, created_at) VALUES (?, 0, 0, ?, ?)'
  )
  for (let i = 0; i < 50; i++) insert.run(`c${i}`, 't', i)
  return db
}

function queryPlan(db: DatabaseSync): string {
  return (db.prepare(`EXPLAIN QUERY PLAN ${READ_QUERY}`).all() as { detail: string }[])
    .map((r) => r.detail)
    .join(' | ')
}

describe('local_conversation created_at index', () => {
  it('without the index, the read scans + sorts with a temp b-tree', () => {
    const plan = queryPlan(makeDb(false))
    expect(plan).toMatch(/TEMP B-TREE/i) // the sort we are removing
    expect(plan).not.toContain('idx_local_conversation_created_at')
  })

  it('with the index, the read is an index-ordered scan (no temp-b-tree sort)', () => {
    const plan = queryPlan(makeDb(true))
    expect(plan).toContain('idx_local_conversation_created_at')
    expect(plan).not.toMatch(/TEMP B-TREE/i)
  })
})
