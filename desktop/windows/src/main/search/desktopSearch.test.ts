// Unified local search, proven against a REAL SQLite database via node:sqlite
// (better-sqlite3 here is built for Electron's ABI and won't load under
// plain-node vitest).
//
// The memories and task schemas are IMPORTED from the modules that own them, so
// a column rename there fails this suite rather than shipping a search that
// silently returns nothing. The rewind_frames block is copied from db.ts, whose
// DDL is inline in its bootstrap exec and has no exported form.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { MEMORY_SEARCH_SCHEMA } from './memorySearchStore'
import { TASK_TABLES_SCHEMA } from '../ipc/taskStore'
import { PER_CORPUS_LIMIT, searchAllCorpora, type SearchDb } from './desktopSearch'

/** Copied from db.ts's bootstrap block (rewind_frames + its FTS mirror). */
const REWIND_SCHEMA = `
  CREATE TABLE IF NOT EXISTS rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    path TEXT NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
  );
  CREATE VIRTUAL TABLE IF NOT EXISTS rewind_frames_fts USING fts5(
    ocr_text, window_title, app,
    content='rewind_frames', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER IF NOT EXISTS rewind_frames_ai AFTER INSERT ON rewind_frames BEGIN
    INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
    VALUES (new.id, new.ocr_text, new.window_title, new.app);
  END;
`

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
`

const EPOCH = 1_723_800_000_000

const open = (): SearchDb & { exec: (s: string) => void } => {
  const db = new DatabaseSync(':memory:')
  db.exec(MEMORIES_SCHEMA)
  db.exec(MEMORY_SEARCH_SCHEMA)
  db.exec(TASK_TABLES_SCHEMA)
  db.exec(REWIND_SCHEMA)
  return db as unknown as SearchDb & { exec: (s: string) => void }
}

const addMemory = (db: SearchDb, content: string, at = EPOCH, summary = ''): void => {
  db.prepare(
    `INSERT INTO memories (content, category, context_summary, created_at) VALUES (?, 'personal', ?, ?)`
  ).all(content, summary, at)
}

const addAction = (
  db: SearchDb,
  description: string,
  over: { completed?: boolean; deleted?: boolean; at?: number } = {}
): void => {
  db.prepare(
    `INSERT INTO action_items (description, completed, deleted, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?)`
  ).all(
    description,
    over.completed ? 1 : 0,
    over.deleted ? 1 : 0,
    over.at ?? EPOCH,
    over.at ?? EPOCH
  )
}

const addStaged = (db: SearchDb, description: string, at = EPOCH): void => {
  db.prepare(`INSERT INTO staged_tasks (description, created_at, updated_at) VALUES (?, ?, ?)`).all(
    description,
    at,
    at
  )
}

const addFrame = (
  db: SearchDb,
  over: { ocr?: string; title?: string; app?: string; at?: number } = {}
): void => {
  db.prepare(
    `INSERT INTO rewind_frames (ts, path, app, window_title, ocr_text) VALUES (?, ?, ?, ?, ?)`
  ).all(over.at ?? EPOCH, 'C:/frames/f.jpg', over.app ?? 'Chrome', over.title ?? '', over.ocr ?? '')
}

describe('searchAllCorpora', () => {
  it('finds the same word across memories, tasks and screen text in one call', () => {
    const db = open()
    addMemory(db, 'Prefers the lease renewed annually')
    addAction(db, 'Send the lease to legal')
    addStaged(db, 'Review lease clause 7')
    addFrame(db, { ocr: 'lease agreement draft', title: 'Docs' })

    const out = searchAllCorpora(db, 'lease')
    expect(out.memories.hits.map((h) => h.title)).toEqual(['Prefers the lease renewed annually'])
    expect(out.tasks.hits.map((h) => h.title).sort()).toEqual([
      'Review lease clause 7',
      'Send the lease to legal'
    ])
    expect(out.screen.hits.length).toBe(1)
  })

  it('narrows as more words are typed rather than widening', () => {
    const db = open()
    addMemory(db, 'budget review with finance')
    addMemory(db, 'budget approved')

    // Tokens are AND-joined: the second word must also match.
    expect(searchAllCorpora(db, 'budget').memories.hits.length).toBe(2)
    expect(searchAllCorpora(db, 'budget finance').memories.hits.length).toBe(1)
  })

  it('matches a prefix so results appear while the word is still being typed', () => {
    const db = open()
    addMemory(db, 'Renewed the insurance policy')
    expect(searchAllCorpora(db, 'insur').memories.hits.length).toBe(1)
  })

  it('treats punctuation as literal text instead of query syntax', () => {
    const db = open()
    addMemory(db, 'Ship v2 of the API')
    // A bare `"` or `*` reaching FTS5 is a syntax error thrown out of SQLite,
    // which would surface as a crash on a keystroke.
    expect(() => searchAllCorpora(db, 'api "')).not.toThrow()
    expect(() => searchAllCorpora(db, '***')).not.toThrow()
    expect(() => searchAllCorpora(db, 'api AND OR NOT')).not.toThrow()
  })

  it('returns empty slices for a query with nothing searchable in it', () => {
    const db = open()
    addMemory(db, 'anything')
    const out = searchAllCorpora(db, '   ')
    expect(out).toEqual({
      memories: { hits: [], total: 0 },
      tasks: { hits: [], total: 0 },
      screen: { hits: [], total: 0 }
    })
  })

  it('reports the true total so the UI never implies it showed everything', () => {
    const db = open()
    for (let i = 0; i < 30; i += 1) addMemory(db, `standup note ${i}`, EPOCH + i)

    const out = searchAllCorpora(db, 'standup')
    expect(out.memories.hits.length).toBe(PER_CORPUS_LIMIT)
    // 30 matched; 20 are shown. A slice that reported 20 would read as "that is
    // everything you have".
    expect(out.memories.total).toBe(30)
  })

  it('searches both accepted and suggested tasks, and counts both', () => {
    const db = open()
    addAction(db, 'invoice Acme')
    addStaged(db, 'invoice Globex')

    const out = searchAllCorpora(db, 'invoice')
    expect(out.tasks.total).toBe(2)
    expect(out.tasks.hits.map((h) => h.id.split(':')[0]).sort()).toEqual(['action', 'staged'])
    expect(out.tasks.hits.find((h) => h.id.startsWith('staged'))?.detail).toBe('Suggested')
  })

  it('keeps completed tasks findable but drops deleted ones', () => {
    const db = open()
    addAction(db, 'renew the domain', { completed: true })
    addAction(db, 'renew the certificate', { deleted: true })

    const out = searchAllCorpora(db, 'renew')
    // "What did I decide about X" is usually a question about finished work.
    expect(out.tasks.hits.map((h) => h.title)).toEqual(['renew the domain'])
    expect(out.tasks.hits[0].detail).toBe('Done')
    expect(out.tasks.total).toBe(1)
  })

  it('orders merged task results by recency, not by two incomparable scores', () => {
    const db = open()
    addAction(db, 'ship the report', { at: EPOCH })
    addStaged(db, 'ship the deck', EPOCH + 5_000)
    addAction(db, 'ship the notes', { at: EPOCH + 10_000 })

    expect(searchAllCorpora(db, 'ship').tasks.hits.map((h) => h.title)).toEqual([
      'ship the notes',
      'ship the deck',
      'ship the report'
    ])
  })

  it('labels a screen hit by its window title and falls back to the app', () => {
    const db = open()
    addFrame(db, { ocr: 'quarterly figures', title: 'Q3 Plan - Google Docs', app: 'Chrome' })
    addFrame(db, { ocr: 'quarterly figures', title: '', app: 'Excel', at: EPOCH - 1 })

    const hits = searchAllCorpora(db, 'quarterly').screen.hits
    expect(hits.map((h) => h.title).sort()).toEqual(['Excel', 'Q3 Plan - Google Docs'])
  })

  it('finds a memory by its context summary as well as its content', () => {
    const db = open()
    addMemory(db, 'Ships on Fridays', EPOCH, 'agreed during the release sync')
    expect(searchAllCorpora(db, 'release').memories.hits.length).toBe(1)
  })

  it('never matches a memory on its raw window title', () => {
    const db = open()
    db.prepare(
      `INSERT INTO memories (content, category, window_title, created_at)
       VALUES (?, 'personal', ?, ?)`
    ).all('Prefers async standups', 'MyChart - Lab Results', EPOCH)
    expect(searchAllCorpora(db, 'mychart').memories.hits).toEqual([])
  })

  it('splits a camelCase query word so it still matches the spaced-out text', () => {
    const db = open()
    addMemory(db, 'Owns the data pipeline rewrite')
    // The expansion is on the QUERY side: "DataPipeline" becomes
    // ("DataPipeline"* OR "Data"* OR "Pipeline"*), so a name copied out of code
    // still finds the prose that describes it. The FTS tokenizer does not split
    // the indexed text, so the reverse does not hold.
    expect(searchAllCorpora(db, 'DataPipeline').memories.hits.length).toBe(1)
  })
})
