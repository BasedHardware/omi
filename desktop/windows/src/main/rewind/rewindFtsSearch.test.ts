// End-to-end proof that the FTS5 MATCH string produced by the query builder
// actually finds the right rewind_frames rows, ranked by bm25, in a REAL SQLite
// FTS5 index. db.ts's better-sqlite3 can't load under plain-node vitest (Electron
// ABI), so — same pattern as dbSchema.track4.test.ts — the DDL is replicated
// verbatim from db.ts and driven via node:sqlite, while the REAL query builder
// (buildRewindFtsMatch) and the REAL search SQL shape are exercised.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { buildRewindFtsMatch } from './rewindSearchQuery'

// rewind_frames + the Track 4 FTS index/triggers, verbatim from db.ts get().
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
  CREATE VIRTUAL TABLE rewind_frames_fts USING fts5(
    ocr_text, window_title, app,
    content='rewind_frames', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER rewind_frames_ai AFTER INSERT ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
    VALUES (new.id, new.ocr_text, new.window_title, new.app);
  END;
  CREATE TRIGGER rewind_frames_ad AFTER DELETE ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
  END;
  CREATE TRIGGER rewind_frames_au AFTER UPDATE ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
    INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
    VALUES (new.id, new.ocr_text, new.window_title, new.app);
  END;
`

// The exact WHERE/ORDER-BY shape searchRewindFrames() uses in db.ts.
const SEARCH_SQL = `
  SELECT rewind_frames.id FROM rewind_frames
    JOIN rewind_frames_fts ON rewind_frames.id = rewind_frames_fts.rowid
   WHERE rewind_frames_fts MATCH ?
   ORDER BY bm25(rewind_frames_fts) ASC, rewind_frames.ts DESC
   LIMIT ?
`

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec(SCHEMA)
  return db
}

function insert(db: DatabaseSync, ts: number, app: string, title: string, ocr: string): number {
  const r = db
    .prepare(
      'INSERT INTO rewind_frames (ts, app, window_title, process_name, ocr_text, image_path) VALUES (?, ?, ?, ?, ?, ?)'
    )
    .run(ts, app, title, '', ocr, `/tmp/${ts}.jpg`)
  return Number(r.lastInsertRowid)
}

function search(db: DatabaseSync, query: string, limit = 500): number[] {
  const match = buildRewindFtsMatch(query)
  if (!match) return []
  return (db.prepare(SEARCH_SQL).all(match, limit) as { id: number }[]).map((r) => r.id)
}

describe('rewind FTS5 search (real index)', () => {
  it('the quoted prefix term actually matches as a prefix', () => {
    const db = makeDb()
    const id = insert(db, 1000, 'Chrome', 'Docs', 'reservoir engineering schematic')
    // "res"* must prefix-match "reservoir".
    expect(search(db, 'res')).toEqual([id])
    // Non-prefix miss.
    expect(search(db, 'zzz')).toEqual([])
  })

  it('matches OCR text, window title, and app columns', () => {
    const db = makeDb()
    const id = insert(db, 1000, 'Slack', 'general channel', 'quarterly planning notes')
    expect(search(db, 'quarterly')).toEqual([id])
    expect(search(db, 'general')).toEqual([id])
    expect(search(db, 'slack')).toEqual([id])
  })

  it('camelCase expansion matches either sub-word (OR)', () => {
    const db = makeDb()
    const a = insert(db, 1000, 'App', 'w', 'the Activity tab is open')
    const b = insert(db, 2000, 'App', 'w', 'Performance metrics dashboard')
    // "ActivityPerformance" -> ("ActivityPerformance"* OR "Activity"* OR "Performance"*)
    expect(new Set(search(db, 'ActivityPerformance'))).toEqual(new Set([a, b]))
  })

  it('multiple tokens are AND-ed — only frames with all tokens match', () => {
    const db = makeDb()
    const both = insert(db, 1000, 'App', 'w', 'pelican near the reservoir')
    insert(db, 2000, 'App', 'w', 'pelican on the beach')
    insert(db, 3000, 'App', 'w', 'reservoir levels rising')
    expect(search(db, 'pelican reservoir')).toEqual([both])
  })

  it('ranks the tighter match first via bm25 (shorter doc, same term)', () => {
    const db = makeDb()
    const short = insert(db, 1000, 'App', 'w', 'budget')
    const long = insert(db, 2000, 'App', 'w', `budget ${'filler '.repeat(200)}`)
    // bm25 favors the shorter document → it sorts first under ASC ordering.
    expect(search(db, 'budget')).toEqual([short, long])
  })

  it('user-supplied FTS special characters cannot break the query', () => {
    const db = makeDb()
    const id = insert(db, 1000, 'App', 'w', 'the (special) budget: report')
    // Parens/colon in the query are quoted → treated literally, no syntax error.
    expect(() => search(db, 'budget) OR (report')).not.toThrow()
    expect(search(db, 'budget report')).toEqual([id])
  })
})
