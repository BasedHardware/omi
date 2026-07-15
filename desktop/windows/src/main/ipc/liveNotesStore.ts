// PR8 LiveNotes — local-only persistence for AI-generated + user-typed notes
// taken during a live recording. Kept driver-agnostic (no better-sqlite3 /
// electron import) so both the DDL and the CRUD are unit-testable under
// plain-node vitest with node:sqlite — db.ts's native better-sqlite3 dep is built
// for Electron's ABI and can't load there. Same pattern as conversationFolders.ts
// / voiceTurnOutbox.ts / dbWipe.ts.
//
// Ports the macOS LiveNotes storage (Desktop/Sources/LiveNotes/NoteStorage.swift +
// RewindDatabase's `live_notes` migration). Notes NEVER leave the machine — there
// is no backend upload of note content.
//
// Both the schema (LIVE_NOTES_SCHEMA) and the CRUD live here so production (db.ts)
// and the tests run byte-identical statements: a re-declared test copy drifts
// silently (it has, twice in this program — see rewindEmbeddingSql.ts). db.ts
// execs LIVE_NOTES_SCHEMA and calls these functions; the tests import the same
// symbols. dbWipe.test.ts's drift guard also scans this file so the two tables are
// required in USER_DATA_TABLES.

import type { LiveNote } from '../../shared/types'

// Minimal DB surface these functions need — satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests). Bind params
// are positional `?` (no named-param dialect differences between the drivers).
export interface LiveNotesDb {
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

// Schema for the two LiveNotes tables. `transcription_sessions` is a minimal
// session anchor (Mac's `transcription_sessions`); `live_notes.session_id`
// references it ON DELETE CASCADE, mirroring Mac's RewindDatabase migration so a
// deleted session takes its notes with it. NOTE: the app opens SQLite with
// `foreign_keys` OFF globally (see db.ts's rewind-embeddings comment), so the FK
// is declarative parity + future-enforcement, not live cascade today — the
// actual account-switch cleanup is dbWipe (both tables are in USER_DATA_TABLES).
// `session_id` holds the live conversation's client id; notes are separate rows
// distinguished by `is_ai` (auto-generation never overwrites a typed note).
export const LIVE_NOTES_SCHEMA = `
  CREATE TABLE IF NOT EXISTS transcription_sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    created_at INTEGER NOT NULL
  );
  CREATE TABLE IF NOT EXISTS live_notes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES transcription_sessions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    is_ai INTEGER NOT NULL DEFAULT 0,
    seg_start INTEGER,
    seg_end INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_live_notes_session ON live_notes(session_id);
`

/** A note to insert. `id` is a caller-minted UUID; `updatedAt` defaults to
 *  `createdAt` for a fresh row. */
export type LiveNoteInput = {
  id: string
  sessionId: string
  text: string
  isAi: boolean
  segStart?: number | null
  segEnd?: number | null
  createdAt: number
  updatedAt: number
}

type LiveNoteRow = {
  id: string
  sessionId: string
  text: string
  isAi: number
  segStart: number | null
  segEnd: number | null
  createdAt: number
  updatedAt: number
}

const NOTE_COLUMNS =
  'id, session_id AS sessionId, text, is_ai AS isAi, seg_start AS segStart, ' +
  'seg_end AS segEnd, created_at AS createdAt, updated_at AS updatedAt'

function mapRow(r: LiveNoteRow): LiveNote {
  return {
    id: r.id,
    sessionId: r.sessionId,
    text: r.text,
    // SQLite stores the flag as INTEGER 0/1 (no BOOLEAN type — codebase idiom).
    isAi: Boolean(r.isAi),
    segStart: r.segStart ?? null,
    segEnd: r.segEnd ?? null,
    createdAt: Number(r.createdAt),
    updatedAt: Number(r.updatedAt)
  }
}

/** Persist the session anchor when a recording starts (Mac's startSession). No-op
 *  on a repeat id so a StrictMode double-mount / reconnect can't duplicate it. */
export function createTranscriptionSessionOn(
  d: LiveNotesDb,
  session: { id: string; startedAt: number; createdAt: number }
): void {
  d.prepare(
    `INSERT INTO transcription_sessions (id, started_at, created_at)
     VALUES (?, ?, ?)
     ON CONFLICT(id) DO NOTHING`
  ).run(session.id, session.startedAt, session.createdAt)
}

/** Stamp a session's end time (best-effort; the row is created lazily so this is
 *  a no-op if the session was never persisted). */
export function endTranscriptionSessionOn(d: LiveNotesDb, id: string, endedAt: number): void {
  d.prepare('UPDATE transcription_sessions SET ended_at = ? WHERE id = ?').run(endedAt, id)
}

/** Insert one note (AI or manual). Always an INSERT — auto-generation never
 *  updates an existing row, so it can't clobber a user-typed note. */
export function createLiveNoteOn(d: LiveNotesDb, note: LiveNoteInput): void {
  d.prepare(
    `INSERT INTO live_notes (id, session_id, text, is_ai, seg_start, seg_end, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    note.id,
    note.sessionId,
    note.text,
    note.isAi ? 1 : 0,
    note.segStart ?? null,
    note.segEnd ?? null,
    note.createdAt,
    note.updatedAt
  )
}

/** Update a note's text (explicit user edit only — Mac's updateNote). */
export function updateLiveNoteOn(
  d: LiveNotesDb,
  id: string,
  text: string,
  updatedAt: number
): void {
  d.prepare('UPDATE live_notes SET text = ?, updated_at = ? WHERE id = ?').run(text, updatedAt, id)
}

/** Delete a note (explicit user delete only — Mac's deleteNote). */
export function deleteLiveNoteOn(d: LiveNotesDb, id: string): void {
  d.prepare('DELETE FROM live_notes WHERE id = ?').run(id)
}

/** All notes for a session, oldest-first (created_at ascending) so the list reads
 *  top-to-bottom in speech order. Used for crash-recovery reload of a session. */
export function listLiveNotesOn(d: LiveNotesDb, sessionId: string): LiveNote[] {
  const rows = d
    .prepare(
      `SELECT ${NOTE_COLUMNS} FROM live_notes WHERE session_id = ? ORDER BY created_at ASC, id ASC`
    )
    .all(sessionId) as LiveNoteRow[]
  return rows.map(mapRow)
}
