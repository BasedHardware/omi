// Track 2: Voice & PTT depth — voice-turn outbox CRUD contract, proven against a
// real SQLite database via node:sqlite (better-sqlite3 is built for Electron's
// ABI and won't load under plain-node vitest — same reason dbMigrations.test.ts
// / dbWipe.test.ts use node:sqlite). The functions under test are driver-agnostic
// (voiceTurnOutbox.ts), so the DatabaseSync handle is passed straight in.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  insertVoiceTurnOn,
  listPendingVoiceTurnsOn,
  markVoiceTurnAckedOn,
  recordVoiceTurnFailureOn,
  type VoiceTurnOutboxDb
} from './voiceTurnOutbox'
import type { VoiceTurnOutboxInput } from '../../shared/types'

// The voice_turn_outbox schema verbatim from db.ts's bootstrap — kept in sync by
// hand (same convention as dbMigrations.test.ts's OLD_SCHEMA copy).
const SCHEMA = `
  CREATE TABLE IF NOT EXISTS voice_turn_outbox (
    idempotency_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    surface TEXT,
    app_id TEXT,
    session_id TEXT,
    user_text TEXT,
    assistant_text TEXT,
    interrupted INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at_ms INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_voice_turn_outbox_pending
    ON voice_turn_outbox(status, created_at_ms);
`

let raw: DatabaseSync
let db: VoiceTurnOutboxDb

function makeInput(over: Partial<VoiceTurnOutboxInput> = {}): VoiceTurnOutboxInput {
  return {
    idempotencyKey: 'turn-1',
    ownerId: 'owner-1',
    surface: 'main_chat',
    appId: 'app-1',
    sessionId: 'sess-1',
    userText: 'what time is it',
    assistantText: 'it is noon',
    interrupted: false,
    createdAtMs: 1000,
    ...over
  }
}

beforeEach(() => {
  raw = new DatabaseSync(':memory:')
  raw.exec(SCHEMA)
  db = raw as unknown as VoiceTurnOutboxDb
})

describe('voice_turn_outbox CRUD', () => {
  it('insert → listPending returns the row with fields + defaults mapped', () => {
    insertVoiceTurnOn(db, makeInput({ interrupted: true }), 1500)

    const pending = listPendingVoiceTurnsOn(db)
    expect(pending).toHaveLength(1)
    expect(pending[0]).toEqual({
      idempotencyKey: 'turn-1',
      ownerId: 'owner-1',
      surface: 'main_chat',
      appId: 'app-1',
      sessionId: 'sess-1',
      userText: 'what time is it',
      assistantText: 'it is noon',
      interrupted: true, // stored 0/1, mapped back to boolean
      createdAtMs: 1000,
      status: 'pending', // DB default
      attempts: 0, // DB default
      lastError: null,
      updatedAtMs: 1500
    })
  })

  it('nullable surface triple / text default to null', () => {
    insertVoiceTurnOn(
      db,
      { idempotencyKey: 'turn-min', ownerId: 'owner-1', createdAtMs: 500 },
      500
    )
    const [row] = listPendingVoiceTurnsOn(db)
    expect(row.surface).toBeNull()
    expect(row.appId).toBeNull()
    expect(row.sessionId).toBeNull()
    expect(row.userText).toBeNull()
    expect(row.assistantText).toBeNull()
    expect(row.interrupted).toBe(false)
  })

  it('duplicate idempotency_key is an idempotent UPSERT (no dup row; updates assistant/interrupted)', () => {
    insertVoiceTurnOn(db, makeInput({ assistantText: 'partial', interrupted: false }), 1000)
    // Re-enqueue for the same key (a barge-in follow-up with fuller assistant text).
    insertVoiceTurnOn(db, makeInput({ assistantText: 'fuller reply', interrupted: true }), 2000)

    const pending = listPendingVoiceTurnsOn(db)
    expect(pending).toHaveLength(1) // no duplicate
    expect(pending[0].assistantText).toBe('fuller reply')
    expect(pending[0].interrupted).toBe(true)
    expect(pending[0].updatedAtMs).toBe(2000)
    // Bookkeeping untouched by the conflict-update.
    expect(pending[0].status).toBe('pending')
    expect(pending[0].attempts).toBe(0)
  })

  it('listPending is oldest-first (created_at_ms ascending) and honors the limit', () => {
    insertVoiceTurnOn(db, makeInput({ idempotencyKey: 'b', createdAtMs: 3000 }), 3000)
    insertVoiceTurnOn(db, makeInput({ idempotencyKey: 'a', createdAtMs: 1000 }), 1000)
    insertVoiceTurnOn(db, makeInput({ idempotencyKey: 'c', createdAtMs: 2000 }), 2000)

    const ordered = listPendingVoiceTurnsOn(db)
    expect(ordered.map((r) => r.idempotencyKey)).toEqual(['a', 'c', 'b'])

    const limited = listPendingVoiceTurnsOn(db, 2)
    expect(limited.map((r) => r.idempotencyKey)).toEqual(['a', 'c'])
  })

  it('markAcked deletes the row so it no longer appears in pending', () => {
    insertVoiceTurnOn(db, makeInput({ idempotencyKey: 'keep', createdAtMs: 1000 }), 1000)
    insertVoiceTurnOn(db, makeInput({ idempotencyKey: 'ack', createdAtMs: 2000 }), 2000)

    markVoiceTurnAckedOn(db, 'ack')

    const pending = listPendingVoiceTurnsOn(db)
    expect(pending.map((r) => r.idempotencyKey)).toEqual(['keep'])
  })

  it('recordVoiceTurnFailure increments attempts, sets last_error + updated_at_ms', () => {
    insertVoiceTurnOn(db, makeInput(), 1000)

    recordVoiceTurnFailureOn(db, 'turn-1', 'network down', 5000)
    let [row] = listPendingVoiceTurnsOn(db)
    expect(row.attempts).toBe(1)
    expect(row.lastError).toBe('network down')
    expect(row.updatedAtMs).toBe(5000)
    expect(row.status).toBe('pending') // still drainable

    recordVoiceTurnFailureOn(db, 'turn-1', 'timeout', 6000)
    ;[row] = listPendingVoiceTurnsOn(db)
    expect(row.attempts).toBe(2)
    expect(row.lastError).toBe('timeout')
    expect(row.updatedAtMs).toBe(6000)
  })
})
