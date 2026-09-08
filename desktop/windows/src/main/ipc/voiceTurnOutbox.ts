// Track 2: Voice & PTT depth — durable voice-turn outbox CRUD, kept
// driver-agnostic (no better-sqlite3 / electron import) so it is unit-testable
// under plain-node vitest with node:sqlite — db.ts's native better-sqlite3 dep
// is built for Electron's ABI and can't load there. Same pattern as dbWipe.ts /
// dbMigrations.ts. The voice_turn_outbox table itself is created in db.ts's
// bootstrap; these functions operate on whatever DB handle is passed in.
//
// Mirrors the macOS RealtimeVoiceTurnOutbox 1:1 (enqueue = idempotent UPSERT,
// acknowledge = delete-on-ack, list = oldest-first for the single-writer drain).
// Nothing consumes it yet — Phase B / Track 1 wire the kernel-write path.

import type { VoiceTurnOutboxEntry, VoiceTurnOutboxInput, VoiceTurnStatus } from '../../shared/types'

// Minimal DB surface these functions need — satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests). Bind params
// are positional `?` (no named-param dialect differences between the drivers).
export interface VoiceTurnOutboxDb {
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

type VoiceTurnOutboxRow = {
  idempotencyKey: string
  ownerId: string
  surface: string | null
  appId: string | null
  sessionId: string | null
  userText: string | null
  assistantText: string | null
  interrupted: number
  createdAtMs: number
  status: string
  attempts: number
  lastError: string | null
  updatedAtMs: number
}

// Column list with camelCase aliases so a raw row maps straight onto the entry.
const OUTBOX_COLUMNS =
  'idempotency_key AS idempotencyKey, owner_id AS ownerId, surface, app_id AS appId, ' +
  'session_id AS sessionId, user_text AS userText, assistant_text AS assistantText, ' +
  'interrupted, created_at_ms AS createdAtMs, status, attempts, ' +
  'last_error AS lastError, updated_at_ms AS updatedAtMs'

function mapRow(r: VoiceTurnOutboxRow): VoiceTurnOutboxEntry {
  return {
    idempotencyKey: r.idempotencyKey,
    ownerId: r.ownerId,
    surface: r.surface ?? null,
    appId: r.appId ?? null,
    sessionId: r.sessionId ?? null,
    userText: r.userText ?? null,
    assistantText: r.assistantText ?? null,
    // SQLite stores the flag as INTEGER 0/1 (no BOOLEAN type — codebase idiom).
    interrupted: Boolean(r.interrupted),
    createdAtMs: Number(r.createdAtMs),
    status: (r.status === 'acked' ? 'acked' : 'pending') as VoiceTurnStatus,
    attempts: Number(r.attempts),
    lastError: r.lastError ?? null,
    updatedAtMs: Number(r.updatedAtMs)
  }
}

/** Idempotent enqueue keyed on idempotency_key. A re-enqueue for the same key
 *  (e.g. a barge-in follow-up capturing more assistant text, or an outbox replay
 *  after a crash) updates the assistant text / interrupted flag and touches
 *  updated_at_ms rather than inserting a duplicate — status/attempts are left
 *  untouched so an in-flight drain's bookkeeping survives the update. */
export function insertVoiceTurnOn(
  d: VoiceTurnOutboxDb,
  entry: VoiceTurnOutboxInput,
  nowMs: number
): void {
  d.prepare(
    `INSERT INTO voice_turn_outbox
       (idempotency_key, owner_id, surface, app_id, session_id, user_text, assistant_text,
        interrupted, created_at_ms, status, attempts, updated_at_ms)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)
     ON CONFLICT(idempotency_key) DO UPDATE SET
       assistant_text = excluded.assistant_text,
       interrupted = excluded.interrupted,
       updated_at_ms = excluded.updated_at_ms`
  ).run(
    entry.idempotencyKey,
    entry.ownerId,
    entry.surface ?? null,
    entry.appId ?? null,
    entry.sessionId ?? null,
    entry.userText ?? null,
    entry.assistantText ?? null,
    entry.interrupted ? 1 : 0,
    entry.createdAtMs,
    nowMs
  )
}

/** Pending turns oldest-first (created_at_ms ascending) so the drain preserves
 *  the single-writer ordering invariant. Optional cap on rows returned. */
export function listPendingVoiceTurnsOn(d: VoiceTurnOutboxDb, limit?: number): VoiceTurnOutboxEntry[] {
  const base = `SELECT ${OUTBOX_COLUMNS} FROM voice_turn_outbox WHERE status = 'pending' ORDER BY created_at_ms ASC`
  const rows = (
    limit != null
      ? d.prepare(`${base} LIMIT ?`).all(limit)
      : d.prepare(base).all()
  ) as VoiceTurnOutboxRow[]
  return rows.map(mapRow)
}

/** Remove the row on a positive kernel ack (the only removal path, mirroring
 *  Mac's acknowledge(idempotencyKey:)). */
export function markVoiceTurnAckedOn(d: VoiceTurnOutboxDb, idempotencyKey: string): void {
  d.prepare('DELETE FROM voice_turn_outbox WHERE idempotency_key = ?').run(idempotencyKey)
}

/** Record a failed delivery attempt: bump attempts, store the last error, touch
 *  updated_at_ms. Leaves status 'pending' so the row is picked up on the next drain. */
export function recordVoiceTurnFailureOn(
  d: VoiceTurnOutboxDb,
  idempotencyKey: string,
  error: string,
  nowMs: number
): void {
  d.prepare(
    'UPDATE voice_turn_outbox SET attempts = attempts + 1, last_error = ?, updated_at_ms = ? WHERE idempotency_key = ?'
  ).run(error, nowMs, idempotencyKey)
}
