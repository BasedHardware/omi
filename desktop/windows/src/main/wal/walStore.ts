// Write-ahead log index for captured audio the transcription socket did not
// take. The audio itself lives in files (one per stored window); this table is
// the durable record of what exists, what state its sync is in, and which
// server job owns it.
//
// Driver-agnostic (no better-sqlite3 / electron import) so the DDL and the CRUD
// are unit-testable under plain-node vitest with node:sqlite, matching
// liveNotesStore.ts / voiceTurnOutbox.ts. db.ts execs WAL_SCHEMA and calls these
// functions; the tests import the same symbols, so production and tests run
// byte-identical statements.
//
// Ports the persistence half of Flutter `services/wals/local_wal_sync.dart` and
// macOS `OmiWAL/WALModel.swift`.

import { isWalPending, makeWalEntry, walId, type WalEntry, type WalStatus } from '../../shared/wal'

// Minimal DB surface, satisfied structurally by better-sqlite3 (production) and
// node:sqlite's DatabaseSync (tests). Positional `?` params only.
export interface WalDb {
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

// `id` is "{device}_{timerStart}" so re-chunking the same recording updates in
// place instead of duplicating it. `file_name` is a name, not a path: the WAL
// directory moves with userData and an absolute path would break on migration.
export const WAL_SCHEMA = `
  CREATE TABLE IF NOT EXISTS audio_wal (
    id TEXT PRIMARY KEY,
    timer_start INTEGER NOT NULL,
    codec TEXT NOT NULL,
    channel INTEGER NOT NULL DEFAULT 1,
    sample_rate INTEGER NOT NULL DEFAULT 16000,
    seconds INTEGER NOT NULL,
    device TEXT NOT NULL,
    device_model TEXT,
    status TEXT NOT NULL,
    storage TEXT NOT NULL,
    file_name TEXT,
    frame_size INTEGER NOT NULL,
    total_frames INTEGER NOT NULL DEFAULT 0,
    synced_frame_offset INTEGER NOT NULL DEFAULT 0,
    conversation_id TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at INTEGER NOT NULL DEFAULT 0,
    job_id TEXT,
    uploaded_at INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_audio_wal_status ON audio_wal(status, timer_start);
  CREATE INDEX IF NOT EXISTS idx_audio_wal_job ON audio_wal(job_id);
`

interface WalRow {
  id: string
  timer_start: number
  codec: string
  channel: number
  sample_rate: number
  seconds: number
  device: string
  device_model: string | null
  status: string
  storage: string
  file_name: string | null
  frame_size: number
  total_frames: number
  synced_frame_offset: number
  conversation_id: string | null
  retry_count: number
  last_retry_at: number
  job_id: string | null
  uploaded_at: number
  size_bytes: number
}

const rowToEntry = (row: WalRow): WalEntry =>
  makeWalEntry({
    timerStart: row.timer_start,
    codec: row.codec,
    channel: row.channel,
    sampleRate: row.sample_rate,
    seconds: row.seconds,
    device: row.device,
    deviceModel: row.device_model,
    status: row.status as WalStatus,
    storage: row.storage === 'mem' ? 'mem' : 'disk',
    filePath: row.file_name,
    frameSize: row.frame_size,
    totalFrames: row.total_frames,
    syncedFrameOffset: row.synced_frame_offset,
    conversationId: row.conversation_id,
    retryCount: row.retry_count,
    lastRetryAt: row.last_retry_at,
    jobId: row.job_id,
    uploadedAt: row.uploaded_at,
    sizeBytes: row.size_bytes
  })

/** Inserts a recording, or updates it in place when the same window is
 *  re-chunked (same capture source and start time). */
export function upsertWal(db: WalDb, entry: WalEntry, nowMs: number = Date.now()): string {
  const id = walId(entry)
  db.prepare(
    `INSERT INTO audio_wal (
       id, timer_start, codec, channel, sample_rate, seconds, device, device_model,
       status, storage, file_name, frame_size, total_frames, synced_frame_offset,
       conversation_id, retry_count, last_retry_at, job_id, uploaded_at, size_bytes, created_at
     ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(id) DO UPDATE SET
       seconds = excluded.seconds,
       status = excluded.status,
       storage = excluded.storage,
       file_name = excluded.file_name,
       total_frames = excluded.total_frames,
       synced_frame_offset = excluded.synced_frame_offset,
       conversation_id = COALESCE(excluded.conversation_id, audio_wal.conversation_id),
       size_bytes = excluded.size_bytes`
  ).run(
    id,
    entry.timerStart,
    entry.codec,
    entry.channel,
    entry.sampleRate,
    entry.seconds,
    entry.device,
    entry.deviceModel,
    entry.status,
    entry.storage,
    entry.filePath,
    entry.frameSize,
    entry.totalFrames,
    entry.syncedFrameOffset,
    entry.conversationId,
    entry.retryCount,
    entry.lastRetryAt,
    entry.jobId,
    entry.uploadedAt,
    entry.sizeBytes,
    nowMs
  )
  return id
}

export function getWal(db: WalDb, id: string): WalEntry | null {
  const row = db.prepare(`SELECT * FROM audio_wal WHERE id = ?`).get(id) as WalRow | undefined
  return row === undefined ? null : rowToEntry(row)
}

export function listWals(db: WalDb): WalEntry[] {
  const rows = db.prepare(`SELECT * FROM audio_wal ORDER BY timer_start DESC`).all() as WalRow[]
  return rows.map(rowToEntry)
}

/** Recordings that still need an upload attempt, oldest first so a backlog
 *  drains in capture order. */
export function listPendingWals(db: WalDb, limit = 50): WalEntry[] {
  const rows = db
    .prepare(
      `SELECT * FROM audio_wal
        WHERE status IN ('miss','inProgress') AND file_name IS NOT NULL
        ORDER BY timer_start ASC
        LIMIT ?`
    )
    .all(limit) as WalRow[]
  return rows.map(rowToEntry)
}

/** Recordings whose bytes the server accepted but whose job has not been
 *  resolved yet. */
export function listUploadedWals(db: WalDb): WalEntry[] {
  const rows = db
    .prepare(
      `SELECT * FROM audio_wal WHERE status = 'uploaded' AND job_id IS NOT NULL
        ORDER BY uploaded_at ASC`
    )
    .all() as WalRow[]
  return rows.map(rowToEntry)
}

export function setWalStatus(db: WalDb, id: string, status: WalStatus): void {
  db.prepare(`UPDATE audio_wal SET status = ? WHERE id = ?`).run(status, id)
}

/** Records a 202: the server has the bytes, the job owns the outcome, and the
 *  local file stays until that job is confirmed. */
export function markWalUploaded(db: WalDb, ids: string[], jobId: string, nowSeconds: number): void {
  const statement = db.prepare(
    `UPDATE audio_wal SET status = 'uploaded', job_id = ?, uploaded_at = ? WHERE id = ?`
  )
  for (const id of ids) statement.run(jobId, nowSeconds, id)
}

/** Records a failed attempt so the display state can move waiting -> retrying
 *  -> failed and the scheduler can back off. */
export function recordWalRetry(db: WalDb, id: string, nowSeconds: number): void {
  db.prepare(
    `UPDATE audio_wal SET status = 'miss', retry_count = retry_count + 1, last_retry_at = ?,
       job_id = NULL WHERE id = ?`
  ).run(nowSeconds, id)
}

/** Clears the attempt history so a manual retry starts from a clean slate. */
export function resetWalRetries(db: WalDb, id: string): void {
  db.prepare(
    `UPDATE audio_wal SET status = 'miss', retry_count = 0, last_retry_at = 0, job_id = NULL
      WHERE id = ?`
  ).run(id)
}

export function setWalConversationId(db: WalDb, id: string, conversationId: string): void {
  db.prepare(`UPDATE audio_wal SET conversation_id = ? WHERE id = ?`).run(conversationId, id)
}

export function deleteWal(db: WalDb, id: string): void {
  db.prepare(`DELETE FROM audio_wal WHERE id = ?`).run(id)
}

export interface WalStats {
  total: number
  pending: number
  uploaded: number
  synced: number
  failed: number
  bytes: number
}

export function walStats(db: WalDb): WalStats {
  const rows = db
    .prepare(
      `SELECT status, COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS bytes FROM audio_wal GROUP BY status`
    )
    .all() as Array<{ status: string; n: number; bytes: number }>
  const stats: WalStats = { total: 0, pending: 0, uploaded: 0, synced: 0, failed: 0, bytes: 0 }
  for (const row of rows) {
    stats.total += row.n
    stats.bytes += row.bytes
    if (isWalPending({ status: row.status as WalStatus })) stats.pending += row.n
    if (row.status === 'uploaded') stats.uploaded += row.n
    if (row.status === 'synced') stats.synced += row.n
    if (row.status === 'corrupted' || row.status === 'outsideRecoveryWindow') stats.failed += row.n
  }
  return stats
}

/**
 * Recordings whose bytes may be removed: confirmed by the server and older than
 * the cutoff. Deliberately excludes `uploaded` — the server holds those bytes
 * but has not confirmed the conversation, so deleting them can lose the audio.
 */
export function cleanupCandidates(db: WalDb, cutoffSeconds: number): WalEntry[] {
  const rows = db
    .prepare(
      `SELECT * FROM audio_wal WHERE status = 'synced' AND timer_start < ? ORDER BY timer_start ASC`
    )
    .all(cutoffSeconds) as WalRow[]
  // The status filter lives in the query alone: a second one here would make
  // neither the authority, and a change to either could pass unnoticed.
  return rows.map(rowToEntry)
}

/**
 * Entries whose backing file is gone. A recording with no bytes can never be
 * uploaded, so it is marked rather than left to fail an attempt every cycle.
 */
export function markMissingFilesCorrupted(
  db: WalDb,
  fileExists: (fileName: string) => boolean
): string[] {
  const rows = db
    .prepare(
      `SELECT * FROM audio_wal WHERE status IN ('miss','inProgress','uploaded') AND file_name IS NOT NULL`
    )
    .all() as WalRow[]
  const corrupted: string[] = []
  for (const row of rows) {
    if (row.file_name === null || fileExists(row.file_name)) continue
    setWalStatus(db, row.id, 'corrupted')
    corrupted.push(row.id)
  }
  return corrupted
}
