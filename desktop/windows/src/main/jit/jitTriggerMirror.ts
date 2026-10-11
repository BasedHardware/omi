/**
 * Driver-neutral durable mirror for the Windows JIT lane.
 *
 * All tables are prefixed with `jit_` and contain only server-authoritative JIT
 * projections or bounded receipts.  The mirror never touches legacy memory,
 * conversation, or Rewind tables.  Tests use node:sqlite and production uses
 * better-sqlite3 through db.ts.
 */
/**
 * The three mirror tables the HOST database touches outside the JIT lane: Rewind
 * retention joins the pin/temporary tables on every prune, and local-conversation
 * deletion drains the cleanup outbox. They are split out so a failed mirror
 * bootstrap can still restore them — losing the JIT lane is acceptable, silently
 * losing screen-frame retention is not.
 */
export const JIT_HOST_SURFACE_SCHEMA = `
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
`

export const JIT_TRIGGER_MIRROR_SCHEMA = `
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
${JIT_HOST_SURFACE_SCHEMA}
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

export function initializeJitTriggerMirror(db: JitMirrorDb): void {
  db.exec(JIT_TRIGGER_MIRROR_SCHEMA)
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

/**
 * Bootstrap the mirror without letting it take the whole local database down.
 * The mirror is additive: every legacy feature must survive its failure, so a
 * throw here is logged and reported, never propagated to the shared db open
 * path. Returns whether the JIT lane may run — false means no `jit_*` table can
 * be assumed and callers must stay inert. The host-facing tables (Rewind
 * retention, keyframe cleanup) are retried on their own so screen-frame
 * retention keeps working with the JIT lane switched off.
 */
export function initializeJitTriggerMirrorSafely(db: JitMirrorDb): boolean {
  try {
    initializeJitTriggerMirror(db)
    return true
  } catch (error) {
    console.error('[jit] trigger mirror bootstrap failed; JIT features stay inert', error)
    try {
      db.exec(JIT_HOST_SURFACE_SCHEMA)
    } catch (hostError) {
      console.error('[jit] host-facing mirror tables unavailable; Rewind prune may skip', hostError)
    }
    return false
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
      db.prepare('DELETE FROM jit_temporary_frame').run()
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
