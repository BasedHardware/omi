// PR8 LiveNotes persistence — proven against a REAL SQLite database via
// node:sqlite. db.ts's better-sqlite3 is built for Electron's ABI and can't load
// under plain-node vitest, so the tests exercise the SAME schema + CRUD symbols
// db.ts imports (LIVE_NOTES_SCHEMA + the *On functions) — never a re-declared copy
// (that drift hid two real bugs in this program). This asserts:
//   - the schema materializes both tables,
//   - AI and manual notes are SEPARATE rows (auto-gen never overwrites a typed note),
//   - is_ai maps to a real boolean, notes list oldest-first,
//   - update touches text + updated_at only, delete removes one row.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  LIVE_NOTES_SCHEMA,
  createTranscriptionSessionOn,
  createLiveNoteOn,
  updateLiveNoteOn,
  deleteLiveNoteOn,
  listLiveNotesOn,
  type LiveNotesDb
} from './liveNotesStore'

const SESSION = 'session-1'

function makeDb(): DatabaseSync {
  const db = new DatabaseSync(':memory:')
  db.exec(LIVE_NOTES_SCHEMA)
  return db
}

function asDb(db: DatabaseSync): LiveNotesDb {
  return db as unknown as LiveNotesDb
}

function seedSession(db: DatabaseSync, id = SESSION): void {
  createTranscriptionSessionOn(asDb(db), { id, startedAt: 1000, createdAt: 1000 })
}

describe('LiveNotes schema', () => {
  it('creates transcription_sessions and live_notes', () => {
    const db = makeDb()
    const names = (
      db
        .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        .all() as { name: string }[]
    ).map((r) => r.name)
    expect(names).toContain('transcription_sessions')
    expect(names).toContain('live_notes')
  })

  it('declares the cascading FK on live_notes.session_id', () => {
    const db = makeDb()
    const fks = db.prepare('PRAGMA foreign_key_list(live_notes)').all() as {
      table: string
      from: string
      to: string
      on_delete: string
    }[]
    expect(fks).toHaveLength(1)
    expect(fks[0].table).toBe('transcription_sessions')
    expect(fks[0].from).toBe('session_id')
    expect(fks[0].on_delete).toBe('CASCADE')
  })
})

describe('LiveNotes CRUD', () => {
  let db: DatabaseSync
  beforeEach(() => {
    db = makeDb()
    seedSession(db)
  })

  it('stores AI and manual notes as separate rows (never overwrites a typed note)', () => {
    createLiveNoteOn(asDb(db), {
      id: 'n1',
      sessionId: SESSION,
      text: 'typed by user',
      isAi: false,
      createdAt: 2000,
      updatedAt: 2000
    })
    createLiveNoteOn(asDb(db), {
      id: 'n2',
      sessionId: SESSION,
      text: 'ai bullet',
      isAi: true,
      segStart: 3,
      segEnd: 6,
      createdAt: 2500,
      updatedAt: 2500
    })

    const notes = listLiveNotesOn(asDb(db), SESSION)
    expect(notes).toHaveLength(2)
    // Oldest-first: the typed note precedes the later AI note.
    expect(notes.map((n) => n.id)).toEqual(['n1', 'n2'])
    const [manual, ai] = notes
    expect(manual.isAi).toBe(false)
    expect(manual.text).toBe('typed by user')
    expect(ai.isAi).toBe(true)
    expect(ai.segStart).toBe(3)
    expect(ai.segEnd).toBe(6)
  })

  it('updates only text + updated_at on an explicit edit', () => {
    createLiveNoteOn(asDb(db), {
      id: 'n1',
      sessionId: SESSION,
      text: 'original',
      isAi: false,
      createdAt: 2000,
      updatedAt: 2000
    })
    updateLiveNoteOn(asDb(db), 'n1', 'edited', 9000)
    const [note] = listLiveNotesOn(asDb(db), SESSION)
    expect(note.text).toBe('edited')
    expect(note.updatedAt).toBe(9000)
    expect(note.createdAt).toBe(2000)
  })

  it('deletes a single note', () => {
    createLiveNoteOn(asDb(db), {
      id: 'n1',
      sessionId: SESSION,
      text: 'a',
      isAi: true,
      createdAt: 2000,
      updatedAt: 2000
    })
    createLiveNoteOn(asDb(db), {
      id: 'n2',
      sessionId: SESSION,
      text: 'b',
      isAi: true,
      createdAt: 2100,
      updatedAt: 2100
    })
    deleteLiveNoteOn(asDb(db), 'n1')
    const notes = listLiveNotesOn(asDb(db), SESSION)
    expect(notes.map((n) => n.id)).toEqual(['n2'])
  })

  it('scopes notes to their session', () => {
    seedSession(db, 'session-2')
    createLiveNoteOn(asDb(db), {
      id: 'n1',
      sessionId: SESSION,
      text: 'a',
      isAi: true,
      createdAt: 2000,
      updatedAt: 2000
    })
    createLiveNoteOn(asDb(db), {
      id: 'n2',
      sessionId: 'session-2',
      text: 'b',
      isAi: true,
      createdAt: 2100,
      updatedAt: 2100
    })
    expect(listLiveNotesOn(asDb(db), SESSION).map((n) => n.id)).toEqual(['n1'])
    expect(listLiveNotesOn(asDb(db), 'session-2').map((n) => n.id)).toEqual(['n2'])
  })

  it('is idempotent on a repeated session id (StrictMode / reconnect safe)', () => {
    seedSession(db) // same id again
    const count = (
      db.prepare('SELECT COUNT(*) AS n FROM transcription_sessions').get() as { n: number }
    ).n
    expect(count).toBe(1)
  })
})
