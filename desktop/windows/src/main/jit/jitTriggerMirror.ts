import {
  compileTriggerSnapshotRow,
  type JitCompiledTrigger,
  type JitTriggerSnapshot,
  type JitTriggerSnapshotRow
} from '../../shared/jitTriggerRuntime'
import { createHash, createHmac, randomBytes } from 'node:crypto'

/**
 * Driver-neutral durable mirror for the Windows JIT lane.
 *
 * All tables are prefixed with `jit_` and contain only server-authoritative JIT
 * projections or bounded receipts.  The mirror never touches legacy memory,
 * conversation, or Rewind tables.  Tests use node:sqlite and production uses
 * better-sqlite3 through db.ts.
 */
export const JIT_TRIGGER_MIRROR_SCHEMA = `
CREATE TABLE IF NOT EXISTS jit_trigger_mirror (
  memory_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  item_revision INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  condition_json TEXT NOT NULL,
  action_type TEXT NOT NULL,
  action_prompt TEXT NOT NULL,
  wakeup_budget_per_day INTEGER,
  snoozed_until TEXT
);
CREATE TABLE IF NOT EXISTS jit_fact_mirror (
  memory_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  item_revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_history_mirror (
  history_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  item_revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_playbook_mirror (
  playbook_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  item_revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_alias_mirror (
  alias_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  item_revision INTEGER NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_snapshot_receipt (
  owner_id TEXT PRIMARY KEY,
  account_generation INTEGER NOT NULL,
  head_commit_id TEXT NOT NULL,
  commit_sequence INTEGER NOT NULL,
  snapshot_revision TEXT NOT NULL,
  trigger_row_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_ledger_snapshot_receipt (
  owner_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL DEFAULT 'knowledge_ledger_mirror.v1',
  account_generation INTEGER NOT NULL,
  source_generation INTEGER NOT NULL,
  writer_epoch INTEGER NOT NULL,
  head_commit_id TEXT NOT NULL,
  commit_sequence INTEGER NOT NULL,
  epoch_id TEXT NOT NULL,
  page_revision TEXT NOT NULL,
  chain_revision TEXT NOT NULL DEFAULT '',
  scanned_count INTEGER NOT NULL DEFAULT 0,
  projected_count INTEGER NOT NULL DEFAULT 0,
  terminal_count INTEGER NOT NULL DEFAULT 0,
  chain_json TEXT NOT NULL DEFAULT '{}',
  row_count INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_wakeup_receipt (
  continuity_key TEXT PRIMARY KEY,
  trigger_id TEXT NOT NULL,
  lane TEXT NOT NULL,
  budget_day TEXT NOT NULL,
  snapshot_revision TEXT NOT NULL,
  observation_fingerprint TEXT NOT NULL,
  state TEXT NOT NULL,
  lease_token TEXT,
  lease_expires_at INTEGER,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_proactivity_reservation_receipt (
  event_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  account_generation INTEGER NOT NULL,
  candidate_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  server_receipt_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_keyframe_pin (
  frame_id INTEGER PRIMARY KEY,
  owner_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  pinned_at INTEGER NOT NULL,
  image_path TEXT NOT NULL DEFAULT '',
  renderer_deletion_key TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jit_keyframe_cleanup_outbox (
  frame_id INTEGER PRIMARY KEY,
  owner_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  image_path TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_temporary_frame (
  frame_id INTEGER PRIMARY KEY,
  owner_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jit_wakeup_trigger_day
  ON jit_wakeup_receipt(trigger_id, budget_day, state);
CREATE INDEX IF NOT EXISTS idx_jit_wakeup_day
  ON jit_wakeup_receipt(budget_day, state);
CREATE TABLE IF NOT EXISTS jit_ambient_context_state (
  context_id TEXT PRIMARY KEY,
  semantic_fingerprint TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jit_feedback_outbox (
  event_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  account_generation INTEGER NOT NULL,
  action TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  trigger_revision INTEGER,
  occurred_at INTEGER NOT NULL,
  snoozed_until TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'pending',
  last_error TEXT,
  next_attempt_at INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jit_feedback_pending
  ON jit_feedback_outbox(state, occurred_at);
CREATE TABLE IF NOT EXISTS jit_installation_identity (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  installation_id TEXT NOT NULL
);
`

export type JitMirrorStatement = {
  run: (...params: unknown[]) => { changes?: number; lastInsertRowid?: number | bigint }
  get: (...params: unknown[]) => unknown
  all: (...params: unknown[]) => unknown[]
}

export type JitMirrorDb = {
  exec(sql: string): unknown
  prepare(sql: string): JitMirrorStatement
}

const OPAQUE_ID_PATTERN = /^[a-f0-9]{64}$/

/**
 * Return the one random secret for this local installation. It is intentionally
 * stored without any context dictionary: HMAC-derived retained IDs remain
 * stable for local idempotency but cannot be reconstructed from app/window
 * text, trigger facts, or the machine hostname.
 */
export function getOrCreateJitInstallationId(
  db: JitMirrorDb,
  randomId: () => string = () => randomBytes(32).toString('hex')
): string {
  const read = (): string | null => {
    const row = db
      .prepare(
        'SELECT installation_id AS installationId FROM jit_installation_identity WHERE singleton = 1'
      )
      .get() as { installationId?: unknown } | undefined
    return typeof row?.installationId === 'string' && OPAQUE_ID_PATTERN.test(row.installationId)
      ? row.installationId
      : null
  }
  const existing = read()
  if (existing) return existing
  const generated = randomId().toLowerCase()
  if (!OPAQUE_ID_PATTERN.test(generated)) throw new JitMirrorError('malformed_row')
  db.prepare(
    'INSERT OR IGNORE INTO jit_installation_identity (singleton, installation_id) VALUES (1, ?)'
  ).run(generated)
  const installed = read()
  if (!installed) throw new JitMirrorError('database_unavailable')
  return installed
}

/** HMAC-SHA256 IDs are opaque on the wire while remaining locally idempotent. */
export function deriveJitOpaqueId(db: JitMirrorDb, namespace: string, seed: string): string {
  if (!namespace || !seed) throw new JitMirrorError('malformed_row')
  return createHmac('sha256', Buffer.from(getOrCreateJitInstallationId(db), 'hex'))
    .update(`${namespace}\u0000${seed}`, 'utf8')
    .digest('hex')
}

/** The backend's 64-hex device field is derived from a random installation ID,
 * never from a hostname or another machine-identifying fact. */
export function jitInstallationDeviceId(db: JitMirrorDb): string {
  return createHash('sha256').update(getOrCreateJitInstallationId(db), 'utf8').digest('hex')
}

export type JitMirrorErrorCode =
  | 'incomplete'
  | 'invalid_identity'
  | 'stale_generation'
  | 'stale_revision'
  | 'conflicting_revision'
  | 'malformed_row'
  | 'database_unavailable'
  | 'budget_exhausted'

export class JitMirrorError extends Error {
  constructor(readonly code: JitMirrorErrorCode) {
    super(code)
    this.name = 'JitMirrorError'
  }
}

export type JitMirrorReceipt = {
  ownerId: string
  accountGeneration: number
  commitSequence: number
  snapshotRevision: string
  rowCount: number
}

export type JitLedgerMirrorRow = {
  memoryId: string
  itemRevision: number
  status: string
  sourceState: string
  canonicalMemoryId: string | null
  contentPurged: boolean
  memory: Record<string, unknown> | null
}

export type JitLedgerMirrorAlias = {
  aliasMemoryId: string
  canonicalMemoryId: string
  sourceMemoryId: string
  reason: 'canonical_memory_id' | 'superseded_by'
}

export type JitLedgerMirrorPage = {
  schemaVersion: 'knowledge_ledger_mirror.v1'
  ownerId: string
  accountGeneration: number
  sourceGeneration: number
  writerEpoch: number
  headCommitId: string
  commitSequence: number
  epochId: string
  pageRevision: string
  chainRevision: string
  scannedCount: number
  projectedCount: number
  terminalCount: number
  /** Older mirror envelopes omit the cumulative terminal count. */
  terminalCountFromServer?: boolean
  rows: JitLedgerMirrorRow[]
  aliases: JitLedgerMirrorAlias[]
  nextCursor: string | null
  finalPage: boolean
  failureReason: string | null
}

export type JitLedgerMirrorReceipt = {
  schemaVersion: 'knowledge_ledger_mirror.v1'
  ownerId: string
  accountGeneration: number
  sourceGeneration: number
  writerEpoch: number
  headCommitId: string
  commitSequence: number
  epochId: string
  pageRevision: string
  chainRevision: string
  scannedCount: number
  projectedCount: number
  terminalCount: number
  rowCount: number
}

export type JitWakeupClaim = {
  continuityKey: string
  triggerId: string
  leaseToken: string
}

export type JitProactivityReservationReceipt = {
  eventId: string
  ownerId: string
  accountGeneration: number
  candidateId: string
  operation: string
  requestHash: string
  serverReceiptJson: string
  createdAt: number
}

export type JitKeyframePin = {
  frameId: number
  ownerId: string
  conversationId: string
  imagePath: string
  /** The renderer-owned chat/session key that must retire this pin. */
  rendererDeletionKey?: string
}

export type JitKeyframeCleanup = JitKeyframePin & {
  attempts: number
  nextAttemptAt: number
  lastError: string | null
  updatedAt: number
}

export function pinJitConversationKeyframe(
  db: JitMirrorDb,
  input: {
    frameId: number
    ownerId: string
    conversationId: string
    imagePath?: string
    rendererDeletionKey?: string
    pinnedAt?: number
  }
): void {
  if (!Number.isInteger(input.frameId) || input.frameId < 0)
    throw new JitMirrorError('malformed_row')
  safeIdentifier(input.ownerId)
  safeIdentifier(input.conversationId)
  const rendererDeletionKey = input.rendererDeletionKey?.trim() ?? ''
  if (rendererDeletionKey) safeIdentifier(rendererDeletionKey)
  const existing = db
    .prepare(
      'SELECT frame_id FROM jit_keyframe_pin WHERE owner_id = ? AND conversation_id = ? LIMIT 1'
    )
    .get(input.ownerId, input.conversationId) as { frame_id: number } | undefined
  if (existing && existing.frame_id !== input.frameId)
    throw new JitMirrorError('conflicting_revision')
  db.prepare(
    `INSERT INTO jit_keyframe_pin (frame_id, owner_id, conversation_id, pinned_at, image_path, renderer_deletion_key) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(frame_id) DO UPDATE SET owner_id=excluded.owner_id, conversation_id=excluded.conversation_id, pinned_at=excluded.pinned_at, image_path=excluded.image_path, renderer_deletion_key=excluded.renderer_deletion_key`
  ).run(
    input.frameId,
    input.ownerId,
    input.conversationId,
    input.pinnedAt ?? Date.now(),
    typeof input.imagePath === 'string' ? input.imagePath : '',
    rendererDeletionKey
  )
}

export function isJitConversationKeyframePinned(db: JitMirrorDb, frameId: number): boolean {
  const row = db.prepare('SELECT 1 FROM jit_keyframe_pin WHERE frame_id = ?').get(frameId)
  return Boolean(row)
}

/** Remove only the permanent pins owned by one deleted conversation. */
export function listJitConversationKeyframePins(db: JitMirrorDb, conversationId: string): number[] {
  safeIdentifier(conversationId)
  const rows = db
    .prepare('SELECT frame_id AS frameId FROM jit_keyframe_pin WHERE conversation_id = ?')
    .all(conversationId) as Array<{ frameId: number }>
  return rows.map((row) => row.frameId)
}

/** Full pin ownership, including the captured path needed when the base
 * rewind row has already disappeared after a crash or independent retention. */
export function listJitConversationKeyframePinDetails(
  db: JitMirrorDb,
  conversationId: string
): JitKeyframePin[] {
  safeIdentifier(conversationId)
  const rows = db
    .prepare(
      'SELECT frame_id AS frameId, owner_id AS ownerId, conversation_id AS conversationId, image_path AS imagePath, renderer_deletion_key AS rendererDeletionKey FROM jit_keyframe_pin WHERE conversation_id = ?'
    )
    .all(conversationId) as Array<{
    frameId: number
    ownerId: string
    conversationId: string
    imagePath: string | null
    rendererDeletionKey: string | null
  }>
  return rows.map((row) => ({
    frameId: row.frameId,
    ownerId: row.ownerId,
    conversationId: row.conversationId,
    imagePath: row.imagePath ?? '',
    ...(typeof row.rendererDeletionKey === 'string' && row.rendererDeletionKey
      ? { rendererDeletionKey: row.rendererDeletionKey }
      : {})
  }))
}

/** Find pins by the renderer-owned key used by local chat/session deletion.
 * This association is written at pin time, before any renderer teardown, so
 * deleting a cloud/local conversation cannot strand a JIT image behind the
 * separate candidate kernel surface. */
export function listJitKeyframePinDetailsForDeletionKey(
  db: JitMirrorDb,
  rendererDeletionKey: string
): JitKeyframePin[] {
  const key = safeIdentifier(rendererDeletionKey)
  const rows = db
    .prepare(
      'SELECT frame_id AS frameId, owner_id AS ownerId, conversation_id AS conversationId, image_path AS imagePath, renderer_deletion_key AS rendererDeletionKey FROM jit_keyframe_pin WHERE renderer_deletion_key = ?'
    )
    .all(key) as Array<{
    frameId: number
    ownerId: string
    conversationId: string
    imagePath: string | null
    rendererDeletionKey: string | null
  }>
  return rows.map((row) => ({
    frameId: row.frameId,
    ownerId: row.ownerId,
    conversationId: row.conversationId,
    imagePath: row.imagePath ?? '',
    rendererDeletionKey: row.rendererDeletionKey ?? key
  }))
}

/** All permanent pins, including pins from a prior account generation.  These
 * rows are install-scoped cleanup authority and must survive an account switch
 * until their image unlink reaches ENOENT/success. */
export function listAllJitKeyframePinDetails(db: JitMirrorDb): JitKeyframePin[] {
  const rows = db
    .prepare(
      'SELECT frame_id AS frameId, owner_id AS ownerId, conversation_id AS conversationId, image_path AS imagePath, renderer_deletion_key AS rendererDeletionKey FROM jit_keyframe_pin ORDER BY frame_id'
    )
    .all() as Array<{
    frameId: number
    ownerId: string
    conversationId: string
    imagePath: string | null
    rendererDeletionKey: string | null
  }>
  return rows.map((row) => ({
    frameId: row.frameId,
    ownerId: row.ownerId,
    conversationId: row.conversationId,
    imagePath: row.imagePath ?? '',
    ...(typeof row.rendererDeletionKey === 'string' && row.rendererDeletionKey
      ? { rendererDeletionKey: row.rendererDeletionKey }
      : {})
  }))
}

export function enqueueJitKeyframeCleanup(
  db: JitMirrorDb,
  input: JitKeyframePin,
  now = Date.now()
): void {
  if (!Number.isInteger(input.frameId) || input.frameId < 0)
    throw new JitMirrorError('malformed_row')
  safeIdentifier(input.ownerId)
  safeIdentifier(input.conversationId)
  db.prepare(
    `INSERT INTO jit_keyframe_cleanup_outbox (frame_id, owner_id, conversation_id, image_path, attempts, next_attempt_at, last_error, updated_at) VALUES (?, ?, ?, ?, 0, ?, NULL, ?) ON CONFLICT(frame_id) DO UPDATE SET owner_id=excluded.owner_id, conversation_id=excluded.conversation_id, image_path=CASE WHEN excluded.image_path <> '' THEN excluded.image_path ELSE jit_keyframe_cleanup_outbox.image_path END, next_attempt_at=MIN(jit_keyframe_cleanup_outbox.next_attempt_at, excluded.next_attempt_at), last_error=NULL, updated_at=excluded.updated_at`
  ).run(input.frameId, input.ownerId, input.conversationId, input.imagePath, now, now)
}

export function listPendingJitKeyframeCleanup(
  db: JitMirrorDb,
  now = Date.now(),
  limit = 32
): JitKeyframeCleanup[] {
  const bounded = Math.max(1, Math.min(32, Math.trunc(limit)))
  const rows = db
    .prepare(
      `SELECT frame_id AS frameId, owner_id AS ownerId, conversation_id AS conversationId, image_path AS imagePath, attempts, next_attempt_at AS nextAttemptAt, last_error AS lastError, updated_at AS updatedAt FROM jit_keyframe_cleanup_outbox WHERE next_attempt_at <= ? ORDER BY updated_at, frame_id LIMIT ?`
    )
    .all(now, bounded) as Array<{
    frameId: number
    ownerId: string
    conversationId: string
    imagePath: string
    attempts: number
    nextAttemptAt: number
    lastError: string | null
    updatedAt: number
  }>
  return rows
}

export function markJitKeyframeCleanupRetry(
  db: JitMirrorDb,
  frameId: number,
  error: string,
  now = Date.now()
): void {
  const current = db
    .prepare('SELECT attempts FROM jit_keyframe_cleanup_outbox WHERE frame_id = ?')
    .get(frameId) as { attempts: number } | undefined
  if (!current) return
  const attempts = current.attempts + 1
  const backoff = Math.min(60 * 60_000, 1_000 * 2 ** Math.min(attempts - 1, 10))
  db.prepare(
    'UPDATE jit_keyframe_cleanup_outbox SET attempts = ?, next_attempt_at = ?, last_error = ?, updated_at = ? WHERE frame_id = ?'
  ).run(attempts, now + backoff, error.slice(0, 256), now, frameId)
}

export function completeJitKeyframeCleanup(db: JitMirrorDb, frameId: number): void {
  // The outbox is the retry authority. Retire it and the permanent pin in one
  // SQLite transaction so a fault between the two deletes cannot strand a pin
  // without a retry record (or clear the retry record while the pin remains).
  runTransaction(db, () => {
    db.prepare('DELETE FROM jit_keyframe_cleanup_outbox WHERE frame_id = ?').run(frameId)
    removeJitConversationKeyframePin(db, frameId)
  })
}

/** Delete a pin only after its attached frame has been removed successfully. */
export function removeJitConversationKeyframePin(db: JitMirrorDb, frameId: number): boolean {
  const result = db.prepare('DELETE FROM jit_keyframe_pin WHERE frame_id = ?').run(frameId)
  return (result.changes ?? 0) === 1
}

/** Compatibility helper for callers that own the entire delete transaction. */
export function takeJitConversationKeyframePins(db: JitMirrorDb, conversationId: string): number[] {
  const frameIds = listJitConversationKeyframePins(db, conversationId)
  db.prepare('DELETE FROM jit_keyframe_pin WHERE conversation_id = ?').run(conversationId)
  return frameIds
}

/** Ambient evidence is temporary until a real conversation is attached. */
export function markJitTemporaryFrame(
  db: JitMirrorDb,
  input: { frameId: number; ownerId: string; expiresAt: number; createdAt?: number }
): void {
  if (!Number.isInteger(input.frameId) || input.frameId < 0)
    throw new JitMirrorError('malformed_row')
  safeIdentifier(input.ownerId)
  const createdAt = input.createdAt ?? Date.now()
  if (
    !Number.isFinite(createdAt) ||
    !Number.isFinite(input.expiresAt) ||
    input.expiresAt < createdAt ||
    input.expiresAt > createdAt + 7 * 24 * 60 * 60_000
  )
    throw new JitMirrorError('malformed_row')
  db.prepare(
    `INSERT INTO jit_temporary_frame (frame_id, owner_id, expires_at, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(frame_id) DO UPDATE SET owner_id=excluded.owner_id, expires_at=excluded.expires_at, created_at=excluded.created_at`
  ).run(input.frameId, input.ownerId, input.expiresAt, createdAt)
}

export function pruneJitTemporaryFrames(db: JitMirrorDb, now = Date.now()): number {
  const result = db.prepare('DELETE FROM jit_temporary_frame WHERE expires_at <= ?').run(now)
  return result.changes ?? 0
}

/** Durable semantic novelty gate for the ambient lane. Timestamp-only
 * observations are not enough: an unchanged context remains suppressed until
 * its cooldown, while a materially changed fingerprint can be reconsidered. */
export function claimJitAmbientContext(
  db: JitMirrorDb,
  input: { contextId: string; semanticFingerprint: string; now?: number; cooldownMs?: number }
): boolean {
  const contextId = safeIdentifier(input.contextId, 256)
  if (!/^[0-9a-f]{8,128}$/i.test(input.semanticFingerprint))
    throw new JitMirrorError('malformed_row')
  const now = input.now ?? Date.now()
  const cooldownMs = input.cooldownMs ?? 15 * 60_000
  if (!Number.isFinite(now) || !Number.isFinite(cooldownMs) || cooldownMs < 0)
    throw new JitMirrorError('malformed_row')
  return runTransaction(db, () => {
    const existing = db
      .prepare(
        'SELECT semantic_fingerprint AS semanticFingerprint, updated_at AS updatedAt FROM jit_ambient_context_state WHERE context_id = ?'
      )
      .get(contextId) as { semanticFingerprint: string; updatedAt: number } | undefined
    if (
      existing &&
      existing.semanticFingerprint === input.semanticFingerprint &&
      now - existing.updatedAt < cooldownMs
    )
      return false
    db.prepare(
      `INSERT INTO jit_ambient_context_state (context_id, semantic_fingerprint, updated_at) VALUES (?, ?, ?) ON CONFLICT(context_id) DO UPDATE SET semantic_fingerprint=excluded.semantic_fingerprint, updated_at=excluded.updated_at`
    ).run(contextId, input.semanticFingerprint, now)
    return true
  })
}

export type JitFeedbackAction =
  | 'useful'
  | 'false_positive'
  | 'snooze'
  | 'disable'
  | 'missed_or_late'
export type JitFeedbackOutboxEntry = {
  eventId: string
  ownerId: string
  accountGeneration: number
  action: JitFeedbackAction
  subjectId: string
  triggerRevision: number | null
  occurredAt: number
  snoozedUntil: string | null
  attempts: number
  state: 'pending' | 'sending' | 'failed' | 'unsupported' | 'complete'
  lastError: string | null
  nextAttemptAt?: number
}

type SnapshotReceiptRow = {
  owner_id: string
  account_generation: number
  head_commit_id: string
  commit_sequence: number
  snapshot_revision: string
  trigger_row_count: number
}

type LedgerReceiptRow = {
  owner_id: string
  schema_version: string
  account_generation: number
  source_generation: number
  writer_epoch: number
  head_commit_id: string
  commit_sequence: number
  epoch_id: string
  page_revision: string
  chain_revision: string
  scanned_count: number
  projected_count: number
  terminal_count: number
  chain_json: string
  row_count: number
}

function safeIdentifier(value: string, max = 256): string {
  const normalized = value.trim()
  if (!normalized || normalized.length > max) throw new JitMirrorError('invalid_identity')
  return normalized
}

function nowIso(now: number): string {
  return new Date(now).toISOString()
}

function randomLeaseToken(): string {
  // The token is only a local compare-and-swap nonce; no secret is persisted.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 18)}`
}

function runTransaction<T>(db: JitMirrorDb, fn: () => T): T {
  db.exec('BEGIN IMMEDIATE')
  try {
    const result = fn()
    db.exec('COMMIT')
    return result
  } catch (error) {
    try {
      db.exec('ROLLBACK')
    } catch {
      /* preserve the original failure */
    }
    throw error
  }
}

function assertSnapshotIdentity(snapshot: JitTriggerSnapshot, ownerId: string): void {
  if (!snapshot.complete || snapshot.failureReason) throw new JitMirrorError('incomplete')
  if (
    snapshot.ownerId !== ownerId ||
    !snapshot.ownerId ||
    !snapshot.snapshotRevision ||
    snapshot.accountGeneration < 0 ||
    snapshot.commitSequence < 0
  ) {
    throw new JitMirrorError('invalid_identity')
  }
  if (snapshot.rows.length > 500) throw new JitMirrorError('malformed_row')
}

function validateRows(rows: JitTriggerSnapshotRow[]): JitCompiledTrigger[] {
  const seen = new Set<string>()
  const compiled: JitCompiledTrigger[] = []
  for (const row of rows) {
    if (seen.has(row.memoryId)) throw new JitMirrorError('malformed_row')
    seen.add(row.memoryId)
    try {
      compiled.push(compileTriggerSnapshotRow(row))
    } catch {
      throw new JitMirrorError('malformed_row')
    }
  }
  return compiled
}

export function initializeJitTriggerMirror(db: JitMirrorDb): void {
  db.exec(JIT_TRIGGER_MIRROR_SCHEMA)
  // Existing development profiles may have created the original JIT outbox
  // before the server feedback contract carried the generation/snooze fence.
  // These additive columns preserve those rows while making new writes typed.
  try {
    db.exec(
      'ALTER TABLE jit_feedback_outbox ADD COLUMN account_generation INTEGER NOT NULL DEFAULT 0'
    )
  } catch {
    /* already present */
  }
  try {
    db.exec('ALTER TABLE jit_feedback_outbox ADD COLUMN snoozed_until TEXT')
  } catch {
    /* already present */
  }
  try {
    db.exec('ALTER TABLE jit_feedback_outbox ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0')
  } catch {
    /* already present */
  }
  try {
    db.exec('ALTER TABLE jit_feedback_outbox ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0')
  } catch {
    /* already present */
  }
  try {
    db.exec('ALTER TABLE jit_trigger_mirror ADD COLUMN snoozed_until TEXT')
  } catch {
    /* already present */
  }
  try {
    db.exec("ALTER TABLE jit_keyframe_pin ADD COLUMN image_path TEXT NOT NULL DEFAULT ''")
  } catch {
    /* already present */
  }
  try {
    db.exec(
      "ALTER TABLE jit_keyframe_pin ADD COLUMN renderer_deletion_key TEXT NOT NULL DEFAULT ''"
    )
  } catch {
    /* already present */
  }
  for (const [name, definition] of [
    ['schema_version', "TEXT NOT NULL DEFAULT 'knowledge_ledger_mirror.v1'"],
    ['chain_revision', "TEXT NOT NULL DEFAULT ''"],
    ['scanned_count', 'INTEGER NOT NULL DEFAULT 0'],
    ['projected_count', 'INTEGER NOT NULL DEFAULT 0'],
    ['terminal_count', 'INTEGER NOT NULL DEFAULT 0'],
    ['chain_json', "TEXT NOT NULL DEFAULT '{}'"]
  ] as const) {
    try {
      db.exec(`ALTER TABLE jit_ledger_snapshot_receipt ADD COLUMN ${name} ${definition}`)
    } catch {
      /* already present */
    }
  }
}

export function reconcileJitTriggerSnapshot(
  db: JitMirrorDb,
  snapshot: JitTriggerSnapshot,
  ownerId: string,
  now = Date.now()
): JitMirrorReceipt {
  assertSnapshotIdentity(snapshot, ownerId)
  validateRows(snapshot.rows)
  const prior = db
    .prepare(
      `SELECT owner_id, account_generation, head_commit_id, commit_sequence, snapshot_revision, trigger_row_count FROM jit_snapshot_receipt LIMIT 1`
    )
    .get() as SnapshotReceiptRow | undefined
  if (prior) {
    if (snapshot.accountGeneration < prior.account_generation)
      throw new JitMirrorError('stale_generation')
    if (
      snapshot.accountGeneration === prior.account_generation &&
      snapshot.commitSequence < prior.commit_sequence
    )
      throw new JitMirrorError('stale_revision')
    if (
      snapshot.accountGeneration === prior.account_generation &&
      snapshot.commitSequence === prior.commit_sequence &&
      snapshot.snapshotRevision !== prior.snapshot_revision
    )
      throw new JitMirrorError('conflicting_revision')
  }
  return runTransaction(db, () => {
    if (
      prior &&
      (snapshot.accountGeneration > prior.account_generation || prior.owner_id !== snapshot.ownerId)
    ) {
      // A generation/owner transition is not permission to drop local pins:
      // those rows carry the only durable authority to unlink old-account image
      // files after a crash or sign-out.  Materialize a retry entry for every
      // pin, then let the independent cleanup worker retire both rows only after
      // unlink success (or ENOENT).
      for (const pin of listAllJitKeyframePinDetails(db)) {
        enqueueJitKeyframeCleanup(db, pin, now)
      }
      db.prepare('DELETE FROM jit_wakeup_receipt').run()
      db.prepare('DELETE FROM jit_proactivity_reservation_receipt').run()
      db.prepare('DELETE FROM jit_ambient_context_state').run()
      db.prepare('DELETE FROM jit_temporary_frame').run()
      db.prepare('DELETE FROM jit_fact_mirror').run()
      db.prepare('DELETE FROM jit_history_mirror').run()
      db.prepare('DELETE FROM jit_playbook_mirror').run()
      db.prepare('DELETE FROM jit_alias_mirror').run()
    }
    for (const row of snapshot.rows) {
      db.prepare(
        `INSERT INTO jit_trigger_mirror (memory_id, account_generation, item_revision, updated_at, condition_json, action_type, action_prompt, wakeup_budget_per_day, snoozed_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(memory_id) DO UPDATE SET account_generation=excluded.account_generation, item_revision=excluded.item_revision, updated_at=excluded.updated_at, condition_json=excluded.condition_json, action_type=excluded.action_type, action_prompt=excluded.action_prompt, wakeup_budget_per_day=excluded.wakeup_budget_per_day, snoozed_until=excluded.snoozed_until`
      ).run(
        row.memoryId,
        snapshot.accountGeneration,
        row.itemRevision,
        row.updatedAt,
        row.triggerConditionJson,
        row.action.type,
        row.action.prompt,
        row.wakeupBudgetPerDay,
        row.snoozedUntil ?? null
      )
    }
    if (snapshot.rows.length === 0) db.prepare('DELETE FROM jit_trigger_mirror').run()
    else {
      const placeholders = snapshot.rows.map(() => '?').join(',')
      db.prepare(`DELETE FROM jit_trigger_mirror WHERE memory_id NOT IN (${placeholders})`).run(
        ...snapshot.rows.map((row) => row.memoryId)
      )
    }
    db.prepare('DELETE FROM jit_snapshot_receipt WHERE owner_id != ?').run(snapshot.ownerId)
    db.prepare(
      `INSERT INTO jit_snapshot_receipt (owner_id, account_generation, head_commit_id, commit_sequence, snapshot_revision, trigger_row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET account_generation=excluded.account_generation, head_commit_id=excluded.head_commit_id, commit_sequence=excluded.commit_sequence, snapshot_revision=excluded.snapshot_revision, trigger_row_count=excluded.trigger_row_count, updated_at=excluded.updated_at`
    ).run(
      snapshot.ownerId,
      snapshot.accountGeneration,
      snapshot.headCommitId,
      snapshot.commitSequence,
      snapshot.snapshotRevision,
      snapshot.rows.length,
      nowIso(now)
    )
    return {
      ownerId: snapshot.ownerId,
      accountGeneration: snapshot.accountGeneration,
      commitSequence: snapshot.commitSequence,
      snapshotRevision: snapshot.snapshotRevision,
      rowCount: snapshot.rows.length
    }
  })
}

export function readCompiledJitTriggers(
  db: JitMirrorDb,
  receipt: JitMirrorReceipt
): JitCompiledTrigger[] {
  const current = db
    .prepare(
      'SELECT snapshot_revision, account_generation, commit_sequence FROM jit_snapshot_receipt WHERE owner_id = ?'
    )
    .get(receipt.ownerId) as
    | { snapshot_revision: string; account_generation: number; commit_sequence: number }
    | undefined
  if (
    !current ||
    current.snapshot_revision !== receipt.snapshotRevision ||
    current.account_generation !== receipt.accountGeneration ||
    current.commit_sequence !== receipt.commitSequence
  )
    throw new JitMirrorError('stale_revision')
  const rows = db
    .prepare(
      'SELECT memory_id AS memoryId, item_revision AS itemRevision, updated_at AS updatedAt, condition_json AS triggerConditionJson, action_type AS actionType, action_prompt AS actionPrompt, wakeup_budget_per_day AS wakeupBudgetPerDay, snoozed_until AS snoozedUntil FROM jit_trigger_mirror ORDER BY memory_id'
    )
    .all() as Array<{
    memoryId: string
    itemRevision: number
    updatedAt: string
    triggerConditionJson: string
    actionType: 'agent_prompt'
    actionPrompt: string
    wakeupBudgetPerDay: number | null
    snoozedUntil: string | null
  }>
  try {
    return rows.map((row) =>
      compileTriggerSnapshotRow({
        memoryId: row.memoryId,
        itemRevision: row.itemRevision,
        updatedAt: row.updatedAt,
        triggerConditionJson: row.triggerConditionJson,
        action: { type: row.actionType, prompt: row.actionPrompt },
        wakeupBudgetPerDay: row.wakeupBudgetPerDay,
        snoozedUntil: row.snoozedUntil
      })
    )
  } catch {
    throw new JitMirrorError('malformed_row')
  }
}

export type JitMirrorKnowledgeItem = {
  id: string
  revision: number
  payload: Record<string, unknown>
}

export type JitHistoryQueryOptions = {
  limit?: number
  cursor?: string | null
  /** Audit is an explicit agent choice; ordinary history omits hidden/rejected rows. */
  audit?: boolean
}

export type JitHistoryQueryPage = {
  items: JitMirrorKnowledgeItem[]
  nextCursor: string | null
  /** True only when the cursor reached the end of the mirror. */
  complete: boolean
  /** True when this page stopped after satisfying its requested item limit. */
  truncated: boolean
  audit: boolean
}

function readKnowledgeRows(
  db: JitMirrorDb,
  table: 'jit_fact_mirror' | 'jit_playbook_mirror' | 'jit_history_mirror',
  idColumn: 'memory_id' | 'playbook_id' | 'history_id',
  ownerId: string,
  accountGeneration: number,
  limit: number
): JitMirrorKnowledgeItem[] {
  safeIdentifier(ownerId)
  if (!Number.isInteger(accountGeneration) || accountGeneration < 0)
    throw new JitMirrorError('invalid_identity')
  const receipt = db
    .prepare('SELECT owner_id, account_generation FROM jit_ledger_snapshot_receipt LIMIT 1')
    .get() as { owner_id: string; account_generation: number } | undefined
  if (!receipt || receipt.owner_id !== ownerId || receipt.account_generation !== accountGeneration)
    throw new JitMirrorError('stale_generation')
  const bounded = Math.max(1, Math.min(200, Math.trunc(limit)))
  const rows = db
    .prepare(
      `SELECT ${idColumn} AS id, item_revision AS revision, payload_json AS payload FROM ${table} WHERE account_generation = ? ORDER BY ${idColumn} LIMIT ?`
    )
    .all(accountGeneration, bounded) as Array<{ id: string; revision: number; payload: string }>
  return rows.map((row) => {
    try {
      const payload = JSON.parse(row.payload)
      if (!payload || typeof payload !== 'object' || Array.isArray(payload))
        throw new Error('payload')
      return { id: row.id, revision: row.revision, payload: payload as Record<string, unknown> }
    } catch {
      throw new JitMirrorError('malformed_row')
    }
  })
}

/** Read only the active, projected facts/playbooks for the signed-in mirror. */
export function readActiveJitFacts(
  db: JitMirrorDb,
  ownerId: string,
  accountGeneration: number,
  limit = 100
): JitMirrorKnowledgeItem[] {
  return readKnowledgeRows(db, 'jit_fact_mirror', 'memory_id', ownerId, accountGeneration, limit)
}

export function readActiveJitPlaybooks(
  db: JitMirrorDb,
  ownerId: string,
  accountGeneration: number,
  limit = 100
): JitMirrorKnowledgeItem[] {
  return readKnowledgeRows(
    db,
    'jit_playbook_mirror',
    'playbook_id',
    ownerId,
    accountGeneration,
    limit
  )
}

/** Agent-directed history lookup. The host never guesses when this should run. */
export function queryJitHistory(
  db: JitMirrorDb,
  ownerId: string,
  accountGeneration: number,
  query: string,
  limit = 20,
  options: Omit<JitHistoryQueryOptions, 'limit'> = {}
): JitMirrorKnowledgeItem[] {
  return queryJitHistoryPage(db, ownerId, accountGeneration, query, { ...options, limit }).items
}

/**
 * Exhaustive, cursor-paged history lookup. The host never decides to search
 * history: the agent invokes this tool explicitly, and must opt into audit
 * rows. We scan in bounded SQL pages but never impose a total-row cap or
 * silently discard a matching row.
 */
export function queryJitHistoryPage(
  db: JitMirrorDb,
  ownerId: string,
  accountGeneration: number,
  query: string,
  options: JitHistoryQueryOptions = {}
): JitHistoryQueryPage {
  const needle = query.trim().toLocaleLowerCase()
  if (!needle) throw new JitMirrorError('malformed_row')
  const limit = Math.max(1, Math.min(50, Math.trunc(options.limit ?? 20)))
  const audit = options.audit === true
  const cursor = options.cursor?.trim() || null
  safeIdentifier(ownerId)
  if (!Number.isInteger(accountGeneration) || accountGeneration < 0)
    throw new JitMirrorError('invalid_identity')
  const receipt = db
    .prepare('SELECT owner_id, account_generation FROM jit_ledger_snapshot_receipt LIMIT 1')
    .get() as { owner_id: string; account_generation: number } | undefined
  if (!receipt || receipt.owner_id !== ownerId || receipt.account_generation !== accountGeneration)
    throw new JitMirrorError('stale_generation')
  const aliases = db
    .prepare('SELECT payload_json AS payload FROM jit_alias_mirror WHERE account_generation = ?')
    .all(accountGeneration) as Array<{ payload: string }>
  const canonicalByAlias = new Map<string, string>()
  for (const row of aliases) {
    try {
      const alias = JSON.parse(row.payload) as Record<string, unknown>
      if (typeof alias.aliasMemoryId === 'string' && typeof alias.canonicalMemoryId === 'string')
        canonicalByAlias.set(alias.aliasMemoryId, alias.canonicalMemoryId)
    } catch {
      throw new JitMirrorError('malformed_row')
    }
  }
  let scanCursor = cursor
  const items: JitMirrorKnowledgeItem[] = []
  let complete = false
  const scanPageSize = 64
  while (!complete && items.length < limit) {
    const rows = db
      .prepare(
        `SELECT history_id AS id, item_revision AS revision, payload_json AS payload FROM jit_history_mirror WHERE account_generation = ? AND (? IS NULL OR history_id > ?) ORDER BY history_id LIMIT ?`
      )
      // Read one sentinel row. A full final batch (exactly 64 rows) is not
      // complete merely because SQLite returned 64 rows; without the
      // sentinel the caller receives a misleading cursor and must make a
      // phantom extra request to discover EOF.
      .all(accountGeneration, scanCursor, scanCursor, scanPageSize + 1) as Array<{
      id: string
      revision: number
      payload: string
    }>
    const hasMore = rows.length > scanPageSize
    let consumedBatch = true
    if (rows.length === 0) break
    const batch = rows.slice(0, scanPageSize)
    for (const [index, row] of batch.entries()) {
      scanCursor = row.id
      let payload: Record<string, unknown>
      try {
        const parsed = JSON.parse(row.payload)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
          throw new Error('payload')
        payload = parsed as Record<string, unknown>
      } catch {
        throw new JitMirrorError('malformed_row')
      }
      const status = String(payload.status ?? '').toLowerCase()
      if (!audit && (status === 'hidden' || status === 'rejected')) continue
      if (!JSON.stringify(payload).toLocaleLowerCase().includes(needle)) continue
      items.push({
        id: row.id,
        revision: row.revision,
        payload: {
          ...payload,
          canonical_memory_id: canonicalByAlias.get(row.id) ?? payload.canonical_memory_id ?? null
        }
      })
      if (items.length >= limit) {
        // A page that ends on the final consumed row is complete when the
        // sentinel was absent. The old `items.length >= limit` check marked
        // an exact 64-row/64-match final batch truncated even though there
        // was no next cursor. If rows remain in this batch (or the sentinel
        // exists), retain the cursor and report a real continuation.
        consumedBatch = index === batch.length - 1 && !hasMore
        break
      }
    }
    complete = !hasMore && consumedBatch
  }
  return {
    items,
    nextCursor: complete ? null : scanCursor,
    complete,
    truncated: !complete && items.length >= limit,
    audit
  }
}

function ledgerPayload(row: JitLedgerMirrorRow): string {
  const payload = JSON.stringify({
    ...(row.memory ?? {}),
    memory_id: row.memoryId,
    item_revision: row.itemRevision,
    status: row.status,
    source_state: row.sourceState,
    canonical_memory_id: row.canonicalMemoryId,
    content_purged: row.contentPurged
  })
  if (payload.length > 128_000) throw new JitMirrorError('malformed_row')
  return payload
}

function classifyLedgerRows(page: JitLedgerMirrorPage): {
  facts: Array<{ id: string; revision: number; payload: string }>
  history: Array<{ id: string; revision: number; payload: string }>
  playbooks: Array<{ id: string; revision: number; payload: string }>
} {
  const facts: Array<{ id: string; revision: number; payload: string }> = []
  const history: Array<{ id: string; revision: number; payload: string }> = []
  const playbooks: Array<{ id: string; revision: number; payload: string }> = []
  const seen = new Set<string>()
  for (const row of page.rows) {
    const id = safeIdentifier(row.memoryId)
    if (seen.has(id) || !Number.isInteger(row.itemRevision) || row.itemRevision < 1)
      throw new JitMirrorError('malformed_row')
    seen.add(id)
    const terminalStatus =
      row.status === 'superseded' ||
      row.status === 'hidden' ||
      row.status === 'rejected' ||
      row.status === 'tombstoned'
    const validStatus = row.status === 'active' || terminalStatus
    const liveSource = row.sourceState === 'active' || row.sourceState === 'missing'
    const purgedSource = row.sourceState === 'tombstoned' || row.sourceState === 'purged'
    const validSource = liveSource || purgedSource
    if (!validStatus || !validSource) throw new JitMirrorError('malformed_row')
    // Tombstones are the only content-free terminal rows. A live/superseded
    // item must carry its source content, and a purged source must be a
    // tombstone. Accepting an impossible status/state pair would let a
    // malformed projection become an agent-visible fact.
    const expectedPurged = row.status === 'tombstoned' && purgedSource
    if (
      row.contentPurged !== expectedPurged ||
      purgedSource !== (row.status === 'tombstoned') ||
      liveSource !== (row.status !== 'tombstoned')
    )
      throw new JitMirrorError('malformed_row')
    if (row.contentPurged ? row.memory !== null : row.memory === null)
      throw new JitMirrorError('malformed_row')
    const payload = ledgerPayload(row)
    const kind = typeof row.memory?.kind === 'string' ? row.memory.kind : null
    if (row.status === 'active' && !row.contentPurged && kind === 'fact') {
      facts.push({ id, revision: row.itemRevision, payload })
    } else if (row.status === 'active' && !row.contentPurged && kind === 'document') {
      const body = row.memory?.body
      if (typeof body !== 'string' || !body.trim() || body.length > 24_000)
        throw new JitMirrorError('malformed_row')
      playbooks.push({ id, revision: row.itemRevision, payload })
    } else {
      // Closed/tombstoned rows remain local handles for historical lookup; their
      // payload is metadata-only once the authority marks content as purged.
      history.push({ id, revision: row.itemRevision, payload })
    }
  }
  return { facts, history, playbooks }
}

export function reconcileJitLedgerMirror(
  db: JitMirrorDb,
  input: {
    fence: Omit<
      JitLedgerMirrorPage,
      'rows' | 'aliases' | 'nextCursor' | 'finalPage' | 'failureReason'
    >
    rows: JitLedgerMirrorRow[]
    aliases: JitLedgerMirrorAlias[]
  },
  ownerId: string,
  now = Date.now()
): JitLedgerMirrorReceipt {
  const fence = input.fence
  if (
    fence.ownerId !== ownerId ||
    !safeIdentifier(ownerId) ||
    !safeIdentifier(fence.headCommitId) ||
    !safeIdentifier(fence.epochId) ||
    !safeIdentifier(fence.pageRevision) ||
    fence.accountGeneration < 0 ||
    fence.sourceGeneration < 0 ||
    fence.writerEpoch < 0 ||
    fence.commitSequence < 0
  )
    throw new JitMirrorError('invalid_identity')

  const classified = classifyLedgerRows({
    ...fence,
    rows: input.rows,
    aliases: input.aliases,
    nextCursor: null,
    finalPage: true,
    failureReason: null
  })
  const aliases = input.aliases.map((alias) => {
    const aliasMemoryId = safeIdentifier(alias.aliasMemoryId)
    const canonicalMemoryId = safeIdentifier(alias.canonicalMemoryId)
    const sourceMemoryId = safeIdentifier(alias.sourceMemoryId)
    if (
      aliasMemoryId === canonicalMemoryId ||
      sourceMemoryId !== aliasMemoryId ||
      alias.reason === undefined
    )
      throw new JitMirrorError('malformed_row')
    return { aliasMemoryId, canonicalMemoryId, sourceMemoryId, reason: alias.reason }
  })
  const aliasIds = new Set<string>()
  for (const alias of aliases) {
    const aliasId = `${alias.aliasMemoryId}:${alias.canonicalMemoryId}:${alias.reason}`
    if (!aliasIds.add(aliasId)) throw new JitMirrorError('malformed_row')
  }
  if (
    (fence as JitLedgerMirrorPage).schemaVersion !== 'knowledge_ledger_mirror.v1' ||
    !/^\S+$/.test(fence.chainRevision) ||
    !Number.isInteger(fence.scannedCount) ||
    !Number.isInteger(fence.projectedCount) ||
    !Number.isInteger(fence.terminalCount) ||
    fence.scannedCount < input.rows.length ||
    fence.projectedCount < 0 ||
    fence.projectedCount > fence.scannedCount ||
    fence.terminalCount < 0 ||
    fence.terminalCount > fence.scannedCount
  )
    throw new JitMirrorError('malformed_row')
  const prior = db
    .prepare(
      `SELECT owner_id, schema_version, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count FROM jit_ledger_snapshot_receipt LIMIT 1`
    )
    .get() as LedgerReceiptRow | undefined
  if (prior) {
    if (fence.accountGeneration < prior.account_generation)
      throw new JitMirrorError('stale_generation')
    if (
      fence.accountGeneration === prior.account_generation &&
      fence.commitSequence < prior.commit_sequence
    )
      throw new JitMirrorError('stale_revision')
    if (
      fence.accountGeneration === prior.account_generation &&
      fence.commitSequence === prior.commit_sequence &&
      (fence.epochId !== prior.epoch_id || fence.pageRevision !== prior.page_revision)
    )
      throw new JitMirrorError('conflicting_revision')
  }
  return runTransaction(db, () => {
    if (
      prior &&
      (fence.accountGeneration > prior.account_generation || prior.owner_id !== fence.ownerId)
    ) {
      // Keep install-scoped pins as physical-file cleanup authority across an
      // account/generation transition. The retry worker, not this projection
      // transaction, retires them after unlink success or ENOENT.
      for (const pin of listAllJitKeyframePinDetails(db)) {
        enqueueJitKeyframeCleanup(db, pin, now)
      }
      db.prepare('DELETE FROM jit_trigger_mirror').run()
      db.prepare('DELETE FROM jit_snapshot_receipt').run()
      db.prepare('DELETE FROM jit_wakeup_receipt').run()
      db.prepare('DELETE FROM jit_proactivity_reservation_receipt').run()
      db.prepare('DELETE FROM jit_ambient_context_state').run()
      db.prepare('DELETE FROM jit_temporary_frame').run()
      db.prepare('DELETE FROM jit_feedback_outbox').run()
    }
    db.prepare('DELETE FROM jit_fact_mirror').run()
    db.prepare('DELETE FROM jit_history_mirror').run()
    db.prepare('DELETE FROM jit_playbook_mirror').run()
    db.prepare('DELETE FROM jit_alias_mirror').run()
    for (const row of classified.facts)
      db.prepare(
        `INSERT INTO jit_fact_mirror (memory_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)`
      ).run(row.id, fence.accountGeneration, row.revision, row.payload)
    for (const row of classified.history)
      db.prepare(
        `INSERT INTO jit_history_mirror (history_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)`
      ).run(row.id, fence.accountGeneration, row.revision, row.payload)
    for (const row of classified.playbooks)
      db.prepare(
        `INSERT INTO jit_playbook_mirror (playbook_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)`
      ).run(row.id, fence.accountGeneration, row.revision, row.payload)
    for (const alias of aliases)
      db.prepare(
        `INSERT INTO jit_alias_mirror (alias_id, account_generation, item_revision, payload_json) VALUES (?, ?, ?, ?)`
      ).run(
        `${alias.aliasMemoryId}:${alias.canonicalMemoryId}:${alias.reason}`,
        fence.accountGeneration,
        1,
        JSON.stringify(alias)
      )
    db.prepare(
      `INSERT INTO jit_ledger_snapshot_receipt (owner_id, schema_version, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, chain_json, row_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET schema_version=excluded.schema_version, account_generation=excluded.account_generation, source_generation=excluded.source_generation, writer_epoch=excluded.writer_epoch, head_commit_id=excluded.head_commit_id, commit_sequence=excluded.commit_sequence, epoch_id=excluded.epoch_id, page_revision=excluded.page_revision, chain_revision=excluded.chain_revision, scanned_count=excluded.scanned_count, projected_count=excluded.projected_count, terminal_count=excluded.terminal_count, chain_json=excluded.chain_json, row_count=excluded.row_count, updated_at=excluded.updated_at`
    ).run(
      ownerId,
      'knowledge_ledger_mirror.v1',
      fence.accountGeneration,
      fence.sourceGeneration,
      fence.writerEpoch,
      fence.headCommitId,
      fence.commitSequence,
      fence.epochId,
      fence.pageRevision,
      fence.chainRevision,
      fence.scannedCount,
      fence.projectedCount,
      fence.terminalCount,
      JSON.stringify({
        chainRevision: fence.chainRevision,
        scannedCount: fence.scannedCount,
        projectedCount: fence.projectedCount,
        terminalCount: fence.terminalCount
      }),
      input.rows.length,
      nowIso(now)
    )
    return {
      ownerId,
      schemaVersion: 'knowledge_ledger_mirror.v1',
      accountGeneration: fence.accountGeneration,
      sourceGeneration: fence.sourceGeneration,
      writerEpoch: fence.writerEpoch,
      headCommitId: fence.headCommitId,
      commitSequence: fence.commitSequence,
      epochId: fence.epochId,
      pageRevision: fence.pageRevision,
      chainRevision: fence.chainRevision,
      scannedCount: fence.scannedCount,
      projectedCount: fence.projectedCount,
      terminalCount: fence.terminalCount,
      rowCount: input.rows.length
    }
  })
}

/** Return the last complete ledger fence for an authenticated owner. This is a
 * read-only view used by the agent's explicit JIT knowledge tools; it never
 * authorizes a reservation or mutates the mirror. */
export function readCurrentJitLedgerMirrorReceipt(
  db: JitMirrorDb,
  ownerId: string
): JitLedgerMirrorReceipt | null {
  safeIdentifier(ownerId)
  const row = db
    .prepare(
      'SELECT owner_id, schema_version, account_generation, source_generation, writer_epoch, head_commit_id, commit_sequence, epoch_id, page_revision, chain_revision, scanned_count, projected_count, terminal_count, row_count FROM jit_ledger_snapshot_receipt WHERE owner_id = ?'
    )
    .get(ownerId) as
    | {
        owner_id: string
        schema_version: string
        account_generation: number
        source_generation: number
        writer_epoch: number
        head_commit_id: string
        commit_sequence: number
        epoch_id: string
        page_revision: string
        chain_revision: string
        scanned_count: number
        projected_count: number
        terminal_count: number
        row_count: number
      }
    | undefined
  if (!row) return null
  if (
    row.owner_id !== ownerId ||
    row.schema_version !== 'knowledge_ledger_mirror.v1' ||
    !Number.isInteger(row.account_generation) ||
    row.account_generation < 0 ||
    !Number.isInteger(row.scanned_count) ||
    !Number.isInteger(row.projected_count) ||
    !Number.isInteger(row.terminal_count) ||
    !Number.isInteger(row.row_count) ||
    row.projected_count > row.scanned_count ||
    row.terminal_count < 0 ||
    row.row_count < 0
  )
    throw new JitMirrorError('malformed_row')
  return {
    schemaVersion: 'knowledge_ledger_mirror.v1',
    ownerId: row.owner_id,
    accountGeneration: row.account_generation,
    sourceGeneration: row.source_generation,
    writerEpoch: row.writer_epoch,
    headCommitId: row.head_commit_id,
    commitSequence: row.commit_sequence,
    epochId: row.epoch_id,
    pageRevision: row.page_revision,
    chainRevision: row.chain_revision,
    scannedCount: row.scanned_count,
    projectedCount: row.projected_count,
    terminalCount: row.terminal_count,
    rowCount: row.row_count
  }
}

export function claimJitWakeup(
  db: JitMirrorDb,
  input: {
    continuityKey: string
    triggerId: string
    lane: 'planned' | 'ambient' | 'ambient_nano'
    budgetDay: string
    snapshotRevision: string
    observationFingerprint: string
    budget: number | null
    now?: number
    globalDailyBudget?: number
  }
): JitWakeupClaim | null {
  const continuityKey = safeIdentifier(input.continuityKey)
  const triggerId = safeIdentifier(input.triggerId)
  const now = input.now ?? Date.now()
  return runTransaction(db, () => {
    const existing = db
      .prepare('SELECT state, lease_expires_at FROM jit_wakeup_receipt WHERE continuity_key = ?')
      .get(continuityKey) as { state: string; lease_expires_at: number | null } | undefined
    if (existing && existing.state === 'complete') return null
    if (existing && (existing.lease_expires_at === null || existing.lease_expires_at > now))
      return null
    // These rows are local leases and duplicate suppression only.  Daily
    // trigger, notification, nano, and full-turn budgets belong to the
    // authenticated reservation authority; applying a local count here would
    // make a stale client silently disagree with the server policy.
    const leaseToken = randomLeaseToken()
    db.prepare(
      `INSERT INTO jit_wakeup_receipt (continuity_key, trigger_id, lane, budget_day, snapshot_revision, observation_fingerprint, state, lease_token, lease_expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?) ON CONFLICT(continuity_key) DO UPDATE SET trigger_id=excluded.trigger_id, lane=excluded.lane, budget_day=excluded.budget_day, snapshot_revision=excluded.snapshot_revision, observation_fingerprint=excluded.observation_fingerprint, state='claimed', lease_token=excluded.lease_token, lease_expires_at=excluded.lease_expires_at, updated_at=excluded.updated_at`
    ).run(
      continuityKey,
      triggerId,
      input.lane,
      input.budgetDay,
      input.snapshotRevision,
      input.observationFingerprint,
      leaseToken,
      now + 5 * 60_000,
      now
    )
    return { continuityKey, triggerId, leaseToken }
  })
}

/** Persist the server receipt only as a local idempotency/dedupe aid. It never
 * grants execution authority; callers must have just received the server ack. */
export function persistJitProactivityReservation(
  db: JitMirrorDb,
  receipt: JitProactivityReservationReceipt
): void {
  if (!/^[a-f0-9]{64}$/.test(receipt.eventId) || !/^[a-f0-9]{64}$/.test(receipt.candidateId))
    throw new JitMirrorError('malformed_row')
  safeIdentifier(receipt.ownerId)
  if (!Number.isInteger(receipt.accountGeneration) || receipt.accountGeneration < 0)
    throw new JitMirrorError('invalid_identity')
  if (!/^[a-f0-9]{64}$/.test(receipt.requestHash)) throw new JitMirrorError('malformed_row')
  db.prepare(
    `INSERT INTO jit_proactivity_reservation_receipt (event_id, owner_id, account_generation, candidate_id, operation, request_hash, server_receipt_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event_id) DO UPDATE SET owner_id=excluded.owner_id, account_generation=excluded.account_generation, candidate_id=excluded.candidate_id, operation=excluded.operation, request_hash=excluded.request_hash, server_receipt_json=excluded.server_receipt_json, created_at=excluded.created_at`
  ).run(
    receipt.eventId,
    receipt.ownerId,
    receipt.accountGeneration,
    receipt.candidateId,
    receipt.operation,
    receipt.requestHash,
    receipt.serverReceiptJson,
    receipt.createdAt
  )
}

export function readJitProactivityReservation(
  db: JitMirrorDb,
  eventId: string,
  ownerId: string
): JitProactivityReservationReceipt | null {
  safeIdentifier(eventId)
  safeIdentifier(ownerId)
  const row = db
    .prepare(
      `SELECT event_id AS eventId, owner_id AS ownerId, account_generation AS accountGeneration, candidate_id AS candidateId, operation, request_hash AS requestHash, server_receipt_json AS serverReceiptJson, created_at AS createdAt FROM jit_proactivity_reservation_receipt WHERE event_id = ? AND owner_id = ?`
    )
    .get(eventId, ownerId) as JitProactivityReservationReceipt | undefined
  return row ?? null
}

export function beginJitWakeup(db: JitMirrorDb, claim: JitWakeupClaim, now = Date.now()): boolean {
  const result = db
    .prepare(
      `UPDATE jit_wakeup_receipt SET state='executing', updated_at=? WHERE continuity_key=? AND lease_token=? AND state='claimed' AND lease_expires_at>?`
    )
    .run(now, claim.continuityKey, claim.leaseToken, now)
  return (result.changes ?? 0) === 1
}

export function cancelJitWakeup(db: JitMirrorDb, claim: JitWakeupClaim, now = Date.now()): boolean {
  const result = db
    .prepare(
      `UPDATE jit_wakeup_receipt SET state='complete', updated_at=?, lease_expires_at=NULL WHERE continuity_key=? AND lease_token=? AND state='claimed'`
    )
    .run(now, claim.continuityKey, claim.leaseToken)
  return (result.changes ?? 0) === 1
}

export function completeJitWakeup(
  db: JitMirrorDb,
  claim: JitWakeupClaim,
  now = Date.now()
): boolean {
  const result = db
    .prepare(
      `UPDATE jit_wakeup_receipt SET state='complete', updated_at=?, lease_expires_at=NULL WHERE continuity_key=? AND lease_token=? AND state='executing'`
    )
    .run(now, claim.continuityKey, claim.leaseToken)
  return (result.changes ?? 0) === 1
}

export function enqueueJitFeedback(
  db: JitMirrorDb,
  entry: Omit<JitFeedbackOutboxEntry, 'attempts' | 'state' | 'lastError' | 'nextAttemptAt'>
): void {
  if (!/^[a-f0-9]{64}$/.test(entry.eventId)) throw new JitMirrorError('malformed_row')
  safeIdentifier(entry.ownerId)
  safeIdentifier(entry.subjectId)
  if (!Number.isInteger(entry.accountGeneration) || entry.accountGeneration < 0)
    throw new JitMirrorError('invalid_identity')
  if (entry.action === 'snooze' && !entry.snoozedUntil) throw new JitMirrorError('malformed_row')
  if (entry.action !== 'snooze' && entry.snoozedUntil) throw new JitMirrorError('malformed_row')
  db.prepare(
    `INSERT INTO jit_feedback_outbox (event_id, owner_id, account_generation, action, subject_id, trigger_revision, occurred_at, snoozed_until, attempts, state, last_error, next_attempt_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', NULL, ?, ?) ON CONFLICT(event_id) DO NOTHING`
  ).run(
    entry.eventId,
    entry.ownerId,
    entry.accountGeneration,
    entry.action,
    entry.subjectId,
    entry.triggerRevision,
    entry.occurredAt,
    entry.snoozedUntil,
    entry.occurredAt,
    entry.occurredAt
  )
}

export function listPendingJitFeedback(
  db: JitMirrorDb,
  limit = 32,
  now = Date.now()
): JitFeedbackOutboxEntry[] {
  // A process crash after marking sending must not strand the event forever.
  // Recovery is bounded and local; the next drain still requires an explicit
  // authenticated server receipt before marking complete.
  db.prepare(
    `UPDATE jit_feedback_outbox SET state='failed', last_error='stale sending recovered', updated_at=? WHERE state='sending' AND updated_at < ?`
  ).run(now, now - 5 * 60_000)
  const rows = db
    .prepare(
      `SELECT event_id AS eventId, owner_id AS ownerId, account_generation AS accountGeneration, action, subject_id AS subjectId, trigger_revision AS triggerRevision, occurred_at AS occurredAt, snoozed_until AS snoozedUntil, attempts, state, last_error AS lastError, next_attempt_at AS nextAttemptAt FROM jit_feedback_outbox WHERE state IN ('pending', 'failed') AND next_attempt_at <= ? ORDER BY occurred_at, event_id LIMIT ?`
    )
    .all(now, Math.max(1, Math.min(32, Math.trunc(limit)))) as Array<
    Omit<JitFeedbackOutboxEntry, 'triggerRevision'> & { triggerRevision: number | string | null }
  >
  return rows.map((row) => ({
    ...row,
    triggerRevision:
      row.triggerRevision === null || row.triggerRevision === ''
        ? null
        : Number.isInteger(Number(row.triggerRevision))
          ? Number(row.triggerRevision)
          : null
  }))
}

export function markJitFeedbackSending(db: JitMirrorDb, eventId: string, now = Date.now()): void {
  db.prepare(
    `UPDATE jit_feedback_outbox SET state='sending', attempts=attempts+1, updated_at=? WHERE event_id=? AND state IN ('pending', 'failed')`
  ).run(now, eventId)
}

export function markJitFeedbackResult(
  db: JitMirrorDb,
  eventId: string,
  sent: boolean,
  error?: string,
  now = Date.now()
): void {
  const row = db
    .prepare("SELECT attempts FROM jit_feedback_outbox WHERE event_id = ? AND state = 'sending'")
    .get(eventId) as { attempts: number } | undefined
  const attempts = row?.attempts ?? 1
  const nextAttemptAt = sent
    ? 0
    : now + Math.min(6 * 60 * 60_000, 30_000 * 2 ** Math.min(Math.max(attempts - 1, 0), 8))
  db.prepare(
    `UPDATE jit_feedback_outbox SET state=?, last_error=?, next_attempt_at=?, updated_at=? WHERE event_id=? AND state='sending'`
  ).run(
    sent ? 'complete' : 'failed',
    sent ? null : (error ?? 'feedback delivery failed').slice(0, 240),
    nextAttemptAt,
    now,
    eventId
  )
}

/** Terminal local state for a feedback row whose lane has no server contract.
 * It is deliberately not `complete`: the UI must never imply that the server
 * accepted an ambient action that carries no trigger revision. Keeping the row
 * also makes the unsupported decision auditable without retrying forever. */
export function markJitFeedbackUnsupported(
  db: JitMirrorDb,
  eventId: string,
  reason: string,
  now = Date.now()
): void {
  db.prepare(
    `UPDATE jit_feedback_outbox SET state='unsupported', last_error=?, next_attempt_at=0, updated_at=? WHERE event_id=? AND state IN ('pending', 'failed', 'sending')`
  ).run(reason.slice(0, 240), now, eventId)
}
