// Track 3 — local task storage (action_items + staged_tasks), a faithful port of
// macOS ActionItemStorage.swift + StagedTaskStorage.swift + their RewindDatabase
// tables. Kept driver-agnostic (no better-sqlite3 / electron import) so both the
// DDL and the CRUD are unit-testable under plain-node vitest with node:sqlite —
// db.ts's native better-sqlite3 dep is built for Electron's ABI and can't load
// there. Same pattern as liveNotesStore.ts / voiceTurnOutbox.ts / dbWipe.ts.
//
// Both the schema (TASK_TABLES_SCHEMA) and the CRUD live here so production (db.ts)
// and the tests run byte-identical statements: a re-declared test copy drifts
// silently (it has, twice in this program — see rewindEmbeddingSql.ts /
// liveNotesStore.ts). db.ts execs TASK_TABLES_SCHEMA and re-exports thin get()-
// bound wrappers over these functions; the tests import the same symbols.
// dbWipe.test.ts's drift guard also scans this file, so action_items and
// staged_tasks are required in USER_DATA_TABLES.
//
// Windows conventions vs Mac: timestamps are epoch-ms INTEGERs (Mac uses DATETIME);
// booleans are 0/1 INTEGERs; the 3072-Float32 embedding is stored as a LE BLOB via
// taskEmbeddingVector.ts and never mapped onto the record (read only via the
// getAll*Embeddings accessors). The lean schema deliberately OMITS Mac's agent-
// session, chat-session, recurrence, and canonical-candidate columns (out of scope
// for this port — an additive ALTER can add any a later wave needs).
//
// Three bug FIXES over Mac are baked in (see the function doc-comments):
//   (i)   staged delete-by-id / delete-by-backend-id are exposed + wired.
//   (ii)  every hard-delete RETURNS the deleted local ids so the caller can evict
//         them from the in-memory embedding index (Mac never did → stale index).
//   (iii) markSyncedActionItem uses the DEFENSIVE dedup-merge (Mac's action_items
//         version could throw on a duplicate backend_id; ported from staged).

import type {
  ActionItemInput,
  ActionItemRecord,
  MarkSyncedResult,
  StagedTaskInput,
  StagedTaskRecord,
  SyncActionItem,
  TaskEmbeddingRow,
  TaskRerank
} from '../../shared/types'
import { bufferToVector, vectorToBuffer } from './taskEmbeddingVector'

// Minimal DB surface these functions need — satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests). Bind params
// are positional `?` (no named-param dialect differences between the drivers);
// booleans are pre-converted to 0/1 (neither driver binds a JS boolean).
export interface TaskStoreDb {
  exec(sql: string): void
  prepare(sql: string): {
    run: (...params: unknown[]) => { changes: number | bigint; lastInsertRowid: number | bigint }
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

// Score sentinel used when ordering active tasks: unscored rows sort last. Mirrors
// Mac's `COALESCE(relevanceScore, 999999)`.
const UNSCORED_SORT = 999999

// ---------------------------------------------------------------------------
// Schema — both tables + their FTS5 external-content indexes + triggers.
// The FTS block mirrors rewind_frames_fts (db.ts) and Mac's action_items_fts /
// staged_tasks_fts. The AFTER UPDATE trigger fires `OF description` only (the sole
// indexed column) so relevance-score bumps don't needlessly churn the FTS shadow
// tables — matches Mac's staged_tasks_fts_au.
// ---------------------------------------------------------------------------
export const TASK_TABLES_SCHEMA = `
  CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_id TEXT UNIQUE,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    deleted_by TEXT,
    source TEXT,
    conversation_id TEXT,
    priority TEXT,
    category TEXT,
    tags_json TEXT,
    due_at INTEGER,
    screenshot_id INTEGER,
    confidence REAL,
    source_app TEXT,
    window_title TEXT,
    context_summary TEXT,
    current_activity TEXT,
    metadata_json TEXT,
    embedding BLOB,
    relevance_score INTEGER,
    scored_at INTEGER,
    from_staged INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER,
    indent_level INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_action_items_backend_id ON action_items(backend_id);
  CREATE INDEX IF NOT EXISTS idx_action_items_created_at ON action_items(created_at);
  CREATE INDEX IF NOT EXISTS idx_action_items_completed ON action_items(completed);
  CREATE INDEX IF NOT EXISTS idx_action_items_backend_synced ON action_items(backend_synced);
  CREATE INDEX IF NOT EXISTS idx_action_items_deleted ON action_items(deleted);
  CREATE INDEX IF NOT EXISTS idx_action_items_due_at ON action_items(due_at);

  CREATE VIRTUAL TABLE IF NOT EXISTS action_items_fts USING fts5(
    description, content='action_items', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER IF NOT EXISTS action_items_ai AFTER INSERT ON action_items BEGIN
    INSERT INTO action_items_fts(rowid, description) VALUES (new.id, new.description);
  END;
  CREATE TRIGGER IF NOT EXISTS action_items_ad AFTER DELETE ON action_items BEGIN
    INSERT INTO action_items_fts(action_items_fts, rowid, description)
    VALUES ('delete', old.id, old.description);
  END;
  CREATE TRIGGER IF NOT EXISTS action_items_au AFTER UPDATE OF description ON action_items BEGIN
    INSERT INTO action_items_fts(action_items_fts, rowid, description)
    VALUES ('delete', old.id, old.description);
    INSERT INTO action_items_fts(rowid, description) VALUES (new.id, new.description);
  END;

  CREATE TABLE IF NOT EXISTS staged_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_id TEXT UNIQUE,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    deleted_by TEXT,
    source TEXT,
    conversation_id TEXT,
    priority TEXT,
    category TEXT,
    tags_json TEXT,
    due_at INTEGER,
    screenshot_id INTEGER,
    confidence REAL,
    source_app TEXT,
    window_title TEXT,
    context_summary TEXT,
    current_activity TEXT,
    metadata_json TEXT,
    embedding BLOB,
    relevance_score INTEGER,
    scored_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_staged_tasks_backend_id ON staged_tasks(backend_id);
  CREATE INDEX IF NOT EXISTS idx_staged_tasks_score ON staged_tasks(relevance_score);
  CREATE INDEX IF NOT EXISTS idx_staged_tasks_created ON staged_tasks(created_at);
  CREATE INDEX IF NOT EXISTS idx_staged_tasks_completed ON staged_tasks(completed);
  CREATE INDEX IF NOT EXISTS idx_staged_tasks_deleted ON staged_tasks(deleted);

  CREATE VIRTUAL TABLE IF NOT EXISTS staged_tasks_fts USING fts5(
    description, content='staged_tasks', content_rowid='id', tokenize='unicode61'
  );
  CREATE TRIGGER IF NOT EXISTS staged_tasks_ai AFTER INSERT ON staged_tasks BEGIN
    INSERT INTO staged_tasks_fts(rowid, description) VALUES (new.id, new.description);
  END;
  CREATE TRIGGER IF NOT EXISTS staged_tasks_ad AFTER DELETE ON staged_tasks BEGIN
    INSERT INTO staged_tasks_fts(staged_tasks_fts, rowid, description)
    VALUES ('delete', old.id, old.description);
  END;
  CREATE TRIGGER IF NOT EXISTS staged_tasks_au AFTER UPDATE OF description ON staged_tasks BEGIN
    INSERT INTO staged_tasks_fts(staged_tasks_fts, rowid, description)
    VALUES ('delete', old.id, old.description);
    INSERT INTO staged_tasks_fts(rowid, description) VALUES (new.id, new.description);
  END;
`

// ---------------------------------------------------------------------------
// Column lists + row types + mappers. The SELECT lists deliberately omit
// `embedding` (a 3072-float BLOB): it is read only via the getAll*Embeddings
// accessors, never on a normal record read.
// ---------------------------------------------------------------------------

const ACTION_COLUMNS =
  'id, backend_id AS backendId, backend_synced AS backendSynced, description, completed, ' +
  'deleted, deleted_by AS deletedBy, source, conversation_id AS conversationId, priority, ' +
  'category, tags_json AS tagsJson, due_at AS dueAt, screenshot_id AS screenshotId, confidence, ' +
  'source_app AS sourceApp, window_title AS windowTitle, context_summary AS contextSummary, ' +
  'current_activity AS currentActivity, metadata_json AS metadataJson, ' +
  'relevance_score AS relevanceScore, scored_at AS scoredAt, from_staged AS fromStaged, ' +
  'sort_order AS sortOrder, indent_level AS indentLevel, created_at AS createdAt, updated_at AS updatedAt'

// staged_tasks has no from_staged / sort_order / indent_level.
const STAGED_COLUMNS =
  'id, backend_id AS backendId, backend_synced AS backendSynced, description, completed, ' +
  'deleted, deleted_by AS deletedBy, source, conversation_id AS conversationId, priority, ' +
  'category, tags_json AS tagsJson, due_at AS dueAt, screenshot_id AS screenshotId, confidence, ' +
  'source_app AS sourceApp, window_title AS windowTitle, context_summary AS contextSummary, ' +
  'current_activity AS currentActivity, metadata_json AS metadataJson, ' +
  'relevance_score AS relevanceScore, scored_at AS scoredAt, created_at AS createdAt, updated_at AS updatedAt'

type ActionItemRow = {
  id: number
  backendId: string | null
  backendSynced: number
  description: string
  completed: number
  deleted: number
  deletedBy: string | null
  source: string | null
  conversationId: string | null
  priority: string | null
  category: string | null
  tagsJson: string | null
  dueAt: number | null
  screenshotId: number | null
  confidence: number | null
  sourceApp: string | null
  windowTitle: string | null
  contextSummary: string | null
  currentActivity: string | null
  metadataJson: string | null
  relevanceScore: number | null
  scoredAt: number | null
  fromStaged: number
  sortOrder: number | null
  indentLevel: number | null
  createdAt: number
  updatedAt: number
}

type StagedTaskRow = Omit<ActionItemRow, 'fromStaged' | 'sortOrder' | 'indentLevel'>

/** JSON string array → string[] (empty on null/invalid — never throws). */
function parseTags(json: string | null): string[] {
  if (!json) return []
  try {
    const v = JSON.parse(json)
    return Array.isArray(v) ? (v.filter((t) => typeof t === 'string') as string[]) : []
  } catch {
    return []
  }
}

/** string[] → JSON string, or null when empty (matches Mac's nil tagsJson). */
function serializeTags(tags: string[] | undefined): string | null {
  return tags && tags.length > 0 ? JSON.stringify(tags) : null
}

function mapAction(r: ActionItemRow): ActionItemRecord {
  return {
    id: r.id,
    backendId: r.backendId,
    backendSynced: r.backendSynced !== 0,
    description: r.description,
    completed: r.completed !== 0,
    deleted: r.deleted !== 0,
    deletedBy: r.deletedBy,
    source: r.source,
    conversationId: r.conversationId,
    priority: r.priority,
    category: r.category,
    tags: parseTags(r.tagsJson),
    dueAt: r.dueAt,
    screenshotId: r.screenshotId,
    confidence: r.confidence,
    sourceApp: r.sourceApp,
    windowTitle: r.windowTitle,
    contextSummary: r.contextSummary,
    currentActivity: r.currentActivity,
    metadataJson: r.metadataJson,
    relevanceScore: r.relevanceScore,
    scoredAt: r.scoredAt,
    fromStaged: r.fromStaged !== 0,
    sortOrder: r.sortOrder,
    indentLevel: r.indentLevel,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt
  }
}

function mapStaged(r: StagedTaskRow): StagedTaskRecord {
  return {
    id: r.id,
    backendId: r.backendId,
    backendSynced: r.backendSynced !== 0,
    description: r.description,
    completed: r.completed !== 0,
    deleted: r.deleted !== 0,
    deletedBy: r.deletedBy,
    source: r.source,
    conversationId: r.conversationId,
    priority: r.priority,
    category: r.category,
    tags: parseTags(r.tagsJson),
    dueAt: r.dueAt,
    screenshotId: r.screenshotId,
    confidence: r.confidence,
    sourceApp: r.sourceApp,
    windowTitle: r.windowTitle,
    contextSummary: r.contextSummary,
    currentActivity: r.currentActivity,
    metadataJson: r.metadataJson,
    relevanceScore: r.relevanceScore,
    scoredAt: r.scoredAt,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt
  }
}

// GRDB's `.ascNullsLast` = `ORDER BY col IS NULL, col ASC`. The list/dashboard reads
// sort by sortOrder → dueAt → createdAt DESC (matches Mac's action_items order).
const ACTION_LIST_ORDER =
  'ORDER BY sort_order IS NULL, sort_order ASC, due_at IS NULL, due_at ASC, created_at DESC'

/** Run `fn` inside a transaction, rolling back on any error. These functions are
 *  top-level storage operations (db.ts calls them on the autocommit connection),
 *  so a plain BEGIN is safe — do not call them nested inside another transaction. */
function tx<T>(d: TaskStoreDb, fn: () => T): T {
  d.exec('BEGIN')
  try {
    const out = fn()
    d.exec('COMMIT')
    return out
  } catch (e) {
    d.exec('ROLLBACK')
    throw e
  }
}

// The two task tables share identical delete/markSynced/rerank logic (only the
// table name differs), so those bodies live in table-parameterized helpers here
// and the per-table exports below are thin wrappers. `table` is one of these two
// compile-time constants — never user input — so interpolating it into the SQL is
// safe (same idiom as the `${fts}` names in db.ts).
type TaskTable = 'action_items' | 'staged_tasks'

/** HARD-delete rows by backend_id inside a tx; returns the deleted local ids (FIX
 *  ii — so the caller can evict them from the in-memory embedding index). */
function deleteByBackendIdOn(d: TaskStoreDb, table: TaskTable, backendId: string): number[] {
  return tx(d, () => {
    const ids = (
      d.prepare(`SELECT id FROM ${table} WHERE backend_id = ?`).all(backendId) as { id: number }[]
    ).map((r) => r.id)
    if (ids.length > 0) d.prepare(`DELETE FROM ${table} WHERE backend_id = ?`).run(backendId)
    return ids
  })
}

/** Defensive markSynced dedup-merge (FIX iii / Mac's staged version): if any OTHER
 *  row already holds `backendId`, mark THAT row synced and delete this one; else set
 *  this row's backend_id, catching the UNIQUE-constraint race the same way. Never
 *  throws on a duplicate backend_id. Returns which row survived. */
function markSyncedOn(
  d: TaskStoreDb,
  table: TaskTable,
  localId: number,
  backendId: string,
  now: number
): MarkSyncedResult {
  return tx(d, () => {
    const existing = d
      .prepare(`SELECT id FROM ${table} WHERE backend_id = ? AND id != ?`)
      .get(backendId, localId) as { id: number } | undefined
    if (existing) {
      d.prepare(`UPDATE ${table} SET backend_synced = 1, updated_at = ? WHERE id = ?`).run(
        now,
        existing.id
      )
      d.prepare(`DELETE FROM ${table} WHERE id = ?`).run(localId)
      return { merged: true, keptId: existing.id }
    }
    try {
      d.prepare(
        `UPDATE ${table} SET backend_id = ?, backend_synced = 1, updated_at = ? WHERE id = ?`
      ).run(backendId, now, localId)
      return { merged: false, keptId: localId }
    } catch (e) {
      // Expected only as the UNIQUE-constraint race: another row grabbed backendId
      // between the SELECT and the UPDATE. Fold this freshly-synced duplicate into
      // the canonical row. If NO other row holds backendId, the error was something
      // else entirely — never delete this row on an unknown failure (silent task
      // loss); re-throw and let the transaction roll back.
      const winner = d
        .prepare(`SELECT id FROM ${table} WHERE backend_id = ? AND id != ?`)
        .get(backendId, localId) as { id: number } | undefined
      if (!winner) throw e
      d.prepare(`DELETE FROM ${table} WHERE id = ?`).run(localId)
      return { merged: true, keptId: winner.id }
    }
  })
}

/** Selective re-rank: pull the re-ranked rows out of the current score order,
 *  reinsert them at their new 1-based positions, then renumber every active row
 *  1..N (relevance_score = position, scored_at = updated_at = now). */
function applyRerankingOn(
  d: TaskStoreDb,
  table: TaskTable,
  reranks: TaskRerank[],
  now: number
): void {
  tx(d, () => {
    const rows = d
      .prepare(
        `SELECT backend_id AS backendId FROM ${table}
           WHERE completed = 0 AND deleted = 0
           ORDER BY COALESCE(relevance_score, ${UNSCORED_SORT}) ASC`
      )
      .all() as { backendId: string | null }[]
    let ordered = rows.map((r) => r.backendId).filter((b): b is string => b != null)
    const rerankedSet = new Set(reranks.map((r) => r.backendId))
    ordered = ordered.filter((b) => !rerankedSet.has(b))
    const sorted = [...reranks].sort((a, b) => a.newPosition - b.newPosition)
    for (const r of sorted) {
      const idx = Math.max(0, Math.min(r.newPosition - 1, ordered.length))
      ordered.splice(idx, 0, r.backendId)
    }
    const stmt = d.prepare(
      `UPDATE ${table} SET relevance_score = ?, scored_at = ?, updated_at = ? WHERE backend_id = ?`
    )
    ordered.forEach((backendId, index) => stmt.run(index + 1, now, now, backendId))
  })
}

// ===========================================================================
// action_items
// ===========================================================================

const ACTION_INSERT_COLUMNS =
  '(backend_id, backend_synced, description, completed, deleted, deleted_by, source, ' +
  'conversation_id, priority, category, tags_json, due_at, screenshot_id, confidence, ' +
  'source_app, window_title, context_summary, current_activity, metadata_json, embedding, ' +
  'relevance_score, scored_at, from_staged, sort_order, indent_level, created_at, updated_at)'

const ACTION_INSERT_PLACEHOLDERS =
  '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'

/** Positional bind values for an action_items INSERT, honoring `backendSyncedOverride`. */
function actionInsertParams(input: ActionItemInput, backendSynced: boolean): unknown[] {
  return [
    input.backendId ?? null,
    backendSynced ? 1 : 0,
    input.description,
    input.completed ? 1 : 0,
    input.deleted ? 1 : 0,
    input.deletedBy ?? null,
    input.source ?? null,
    input.conversationId ?? null,
    input.priority ?? null,
    input.category ?? null,
    serializeTags(input.tags),
    input.dueAt ?? null,
    input.screenshotId ?? null,
    input.confidence ?? null,
    input.sourceApp ?? null,
    input.windowTitle ?? null,
    input.contextSummary ?? null,
    input.currentActivity ?? null,
    input.metadataJson ?? null,
    input.embedding ? vectorToBuffer(input.embedding) : null,
    input.relevanceScore ?? null,
    input.scoredAt ?? null,
    input.fromStaged ? 1 : 0,
    input.sortOrder ?? null,
    input.indentLevel ?? null,
    input.createdAt,
    input.updatedAt
  ]
}

function getActionByIdOn(d: TaskStoreDb, id: number): ActionItemRecord | null {
  const row = d.prepare(`SELECT ${ACTION_COLUMNS} FROM action_items WHERE id = ?`).get(id) as
    | ActionItemRow
    | undefined
  return row ? mapAction(row) : null
}

/** Insert a locally-extracted action item (forces backend_synced = 0). On an FTS/
 *  constraint error, rebuild the FTS index and retry once (Mac's FTS-repair-retry).
 *  Returns the inserted record (with its assigned id + column defaults applied). */
export function insertLocalActionItemOn(d: TaskStoreDb, input: ActionItemInput): ActionItemRecord {
  const sql = `INSERT INTO action_items ${ACTION_INSERT_COLUMNS} VALUES ${ACTION_INSERT_PLACEHOLDERS}`
  const params = actionInsertParams(input, false)
  let id: number
  try {
    id = Number(d.prepare(sql).run(...params).lastInsertRowid)
  } catch {
    // The only recoverable failure here is a corrupt action_items_fts shadow table;
    // rebuild it from the base rows and retry the insert once (any other error rethrows).
    d.exec("INSERT INTO action_items_fts(action_items_fts) VALUES('rebuild')")
    id = Number(d.prepare(sql).run(...params).lastInsertRowid)
  }
  const rec = getActionByIdOn(d, id)
  if (!rec) throw new Error('insertLocalActionItem: row vanished after insert')
  return rec
}

/** Read local action items for display. WHERE deleted = 0 [AND completed = ?],
 *  ordered by sortOrder → dueAt → createdAt DESC, with LIMIT/OFFSET. */
export function getLocalActionItemsOn(
  d: TaskStoreDb,
  opts: { limit?: number; offset?: number; completed?: boolean } = {}
): ActionItemRecord[] {
  const { limit = 50, offset = 0, completed } = opts
  const params: unknown[] = []
  let where = 'WHERE deleted = 0'
  if (completed !== undefined) {
    where += ' AND completed = ?'
    params.push(completed ? 1 : 0)
  }
  params.push(limit, offset)
  const rows = d
    .prepare(
      `SELECT ${ACTION_COLUMNS} FROM action_items ${where} ${ACTION_LIST_ORDER} LIMIT ? OFFSET ?`
    )
    .all(...params) as ActionItemRow[]
  return rows.map(mapAction)
}

/** Recent ACTIVE action items ordered strictly by recency (created_at DESC).
 *  Unlike getLocalActionItems (sortOrder→due→created list order), this gives the
 *  task-extraction context "recent-N by recency" it wants (Mac's
 *  getRecentActiveTasks, TA:1409). Active = completed = 0 AND deleted = 0. */
export function getRecentActiveActionItemsOn(d: TaskStoreDb, limit = 30): ActionItemRecord[] {
  const rows = d
    .prepare(
      `SELECT ${ACTION_COLUMNS} FROM action_items
         WHERE deleted = 0 AND completed = 0 ORDER BY created_at DESC LIMIT ?`
    )
    .all(limit) as ActionItemRow[]
  return rows.map(mapAction)
}

/** Dashboard slices (overdue / today / no-due). Always active (completed = 0,
 *  deleted = 0), filtered by a due_at window. `dueIsNull` true → only tasks with no
 *  due date; false → only tasks with a due date. */
export function getFilteredActionItemsOn(
  d: TaskStoreDb,
  opts: {
    dueAfter?: number | null
    dueBefore?: number | null
    dueIsNull?: boolean
    limit?: number
    offset?: number
  } = {}
): ActionItemRecord[] {
  const { dueAfter, dueBefore, dueIsNull, limit = 200, offset = 0 } = opts
  const params: unknown[] = []
  let where = 'WHERE deleted = 0 AND completed = 0'
  if (dueAfter != null) {
    where += ' AND due_at >= ?'
    params.push(dueAfter)
  }
  if (dueBefore != null) {
    where += ' AND due_at < ?'
    params.push(dueBefore)
  }
  if (dueIsNull !== undefined)
    where += dueIsNull ? ' AND due_at IS NULL' : ' AND due_at IS NOT NULL'
  params.push(limit, offset)
  const rows = d
    .prepare(
      `SELECT ${ACTION_COLUMNS} FROM action_items ${where} ${ACTION_LIST_ORDER} LIMIT ? OFFSET ?`
    )
    .all(...params) as ActionItemRow[]
  return rows.map(mapAction)
}

/** Optimistically set completion by backend_id, bumping updated_at = now so the 60s
 *  conflict guard in syncTaskActionItems protects it from a stale auto-refresh. */
export function updateCompletionStatusOn(
  d: TaskStoreDb,
  backendId: string,
  completed: boolean,
  now: number
): void {
  d.prepare('UPDATE action_items SET completed = ?, updated_at = ? WHERE backend_id = ?').run(
    completed ? 1 : 0,
    now,
    backendId
  )
}

/** Optimistically edit task fields by backend_id (bumps updated_at = now). Only the
 *  provided fields change; `clearDueAt` wins over `dueAt`. */
export function updateActionItemFieldsOn(
  d: TaskStoreDb,
  backendId: string,
  fields: {
    description?: string
    priority?: string
    category?: string
    tags?: string[]
    dueAt?: number | null
    clearDueAt?: boolean
  },
  now: number
): void {
  const sets: string[] = []
  const params: unknown[] = []
  if (fields.description !== undefined) {
    sets.push('description = ?')
    params.push(fields.description)
  }
  if (fields.priority !== undefined) {
    sets.push('priority = ?')
    params.push(fields.priority)
  }
  if (fields.category !== undefined) {
    sets.push('category = ?')
    params.push(fields.category)
  }
  if (fields.tags !== undefined) {
    sets.push('tags_json = ?')
    params.push(serializeTags(fields.tags))
  }
  if (fields.clearDueAt) {
    sets.push('due_at = NULL')
  } else if (fields.dueAt !== undefined) {
    sets.push('due_at = ?')
    params.push(fields.dueAt)
  }
  sets.push('updated_at = ?')
  params.push(now, backendId)
  d.prepare(`UPDATE action_items SET ${sets.join(', ')} WHERE backend_id = ?`).run(...params)
}

/** HARD-delete an action item by backend_id (Mac's "delete" is a raw DELETE, not a
 *  soft flag). FIX (ii): returns the deleted local ids so the caller can evict them
 *  from the in-memory embedding index. `deletedBy` is accepted for call-site parity
 *  but unused (a hard delete keeps no tombstone). */
export function deleteActionItemByBackendIdOn(
  d: TaskStoreDb,
  backendId: string,
  _deletedBy?: string | null
): number[] {
  return deleteByBackendIdOn(d, 'action_items', backendId)
}

/** Mark a locally-inserted action item synced with its backend id, bumping
 *  updated_at = now. FIX (iii) — DEFENSIVE dedup-merge (ported from staged): if any
 *  OTHER row already holds `backendId`, mark THAT row synced and delete this one
 *  (idempotent merge), and catch the UNIQUE-constraint race the same way. Never
 *  throws on a duplicate backend_id. Returns which row survived. */
export function markSyncedActionItemOn(
  d: TaskStoreDb,
  localId: number,
  backendId: string,
  now: number
): MarkSyncedResult {
  return markSyncedOn(d, 'action_items', localId, backendId, now)
}

// Compute the post-`updateFrom` column values for an existing action row from an
// incoming backend item (Mac's ActionItemRecord.updateFrom(TaskActionItem)):
//  - updated_at = max(local, incoming) (monotonic — never regresses)
//  - relevance_score adopted from API only when local has none
//  - sort_order / indent_level overwritten from API when present
//  - tags overwritten only when the incoming set is non-empty
//  - completed / deleted / deletedBy / source / … always taken from API
function applyActionUpdateFrom(
  d: TaskStoreDb,
  existing: ActionItemRow,
  item: SyncActionItem
): void {
  const incoming = item.updatedAt ?? item.createdAt
  const updatedAt = Math.max(existing.updatedAt, incoming)
  const relevanceScore =
    existing.relevanceScore == null && item.relevanceScore != null
      ? item.relevanceScore
      : existing.relevanceScore
  const sortOrder = item.sortOrder != null ? item.sortOrder : existing.sortOrder
  const indentLevel = item.indentLevel != null ? item.indentLevel : existing.indentLevel
  const fromStaged = item.fromStaged != null ? (item.fromStaged ? 1 : 0) : existing.fromStaged
  const tagsJson = item.tags && item.tags.length > 0 ? serializeTags(item.tags) : existing.tagsJson
  d.prepare(
    `UPDATE action_items SET
       backend_id = ?, backend_synced = 1, description = ?, completed = ?, deleted = ?,
       deleted_by = ?, source = ?, conversation_id = ?, priority = ?, category = ?,
       due_at = ?, metadata_json = ?, tags_json = ?, from_staged = ?, relevance_score = ?,
       sort_order = ?, indent_level = ?, updated_at = ?
     WHERE id = ?`
  ).run(
    item.backendId,
    item.description,
    item.completed ? 1 : 0,
    item.deleted ? 1 : 0,
    item.deletedBy ?? null,
    item.source ?? null,
    item.conversationId ?? null,
    item.priority ?? null,
    item.category ?? null,
    item.dueAt ?? null,
    item.metadataJson ?? null,
    tagsJson,
    fromStaged,
    relevanceScore ?? null,
    sortOrder ?? null,
    indentLevel ?? null,
    updatedAt,
    existing.id
  )
}

/** PULL / upsert backend action items into local storage with the conflict rule
 *  (ported from Mac's syncTaskActionItems):
 *   - For an existing backend_id: SKIP when the local change is recent (< 60s) AND
 *     strictly newer than the incoming item AND not a staged-override; else apply
 *     `updateFrom`.
 *   - ORPHAN ADOPTION: when the backend_id is new but an unsynced local row
 *     (backend_id NULL/'') has the SAME description, adopt it (link the backend_id)
 *     instead of inserting a duplicate — heals a crash between save and markSynced.
 *   - Otherwise insert a fresh synced row; an item arriving without a score gets
 *     max(active scores)+1 so it sorts to the bottom.
 *  `overrideStagedDeletions` lets a full sync override local "staged" deletions. */
export function syncTaskActionItemsOn(
  d: TaskStoreDb,
  items: SyncActionItem[],
  opts: { overrideStagedDeletions?: boolean; now: number }
): { skipped: number; adopted: number; inserted: number; updated: number } {
  const overrideStagedDeletions = opts.overrideStagedDeletions ?? false
  const now = opts.now
  return tx(d, () => {
    let skipped = 0
    let adopted = 0
    let inserted = 0
    let updated = 0
    for (const item of items) {
      const existing = d
        .prepare(`SELECT ${ACTION_COLUMNS} FROM action_items WHERE backend_id = ?`)
        .get(item.backendId) as ActionItemRow | undefined
      if (existing) {
        const incoming = item.updatedAt ?? item.createdAt
        const isLocalStagedGuess = overrideStagedDeletions && existing.deletedBy === 'staged'
        const isRecentLocalChange = now - existing.updatedAt < 60_000
        if (isRecentLocalChange && existing.updatedAt > incoming && !isLocalStagedGuess) {
          skipped++
          continue
        }
        applyActionUpdateFrom(d, existing, item)
        updated++
        continue
      }
      const orphan = d
        .prepare(
          `SELECT ${ACTION_COLUMNS} FROM action_items
             WHERE backend_synced = 0 AND (backend_id IS NULL OR backend_id = '')
               AND description = ? LIMIT 1`
        )
        .get(item.description) as ActionItemRow | undefined
      if (orphan) {
        applyActionUpdateFrom(d, orphan, item)
        adopted++
        continue
      }
      // Fresh synced insert. Auto-assign max+1 score for a scoreless arrival.
      let relevanceScore = item.relevanceScore ?? null
      let scoredAt: number | null = null
      if (relevanceScore == null) {
        const max =
          (
            d
              .prepare(
                `SELECT COALESCE(MAX(relevance_score), 0) AS m FROM action_items
                   WHERE completed = 0 AND deleted = 0 AND relevance_score IS NOT NULL`
              )
              .get() as { m: number }
          ).m ?? 0
        relevanceScore = max + 1
        scoredAt = now
      }
      d.prepare(
        `INSERT INTO action_items ${ACTION_INSERT_COLUMNS} VALUES ${ACTION_INSERT_PLACEHOLDERS}`
      ).run(
        ...actionInsertParams(
          {
            backendId: item.backendId,
            description: item.description,
            completed: item.completed,
            deleted: item.deleted ?? false,
            deletedBy: item.deletedBy ?? null,
            source: item.source ?? null,
            conversationId: item.conversationId ?? null,
            priority: item.priority ?? null,
            category: item.category ?? null,
            tags: item.tags,
            dueAt: item.dueAt ?? null,
            sourceApp: item.sourceApp ?? null,
            windowTitle: item.windowTitle ?? null,
            metadataJson: item.metadataJson ?? null,
            relevanceScore,
            scoredAt,
            fromStaged: item.fromStaged ?? false,
            sortOrder: item.sortOrder ?? null,
            indentLevel: item.indentLevel ?? null,
            createdAt: item.createdAt,
            updatedAt: item.updatedAt ?? item.createdAt
          },
          true
        )
      )
      inserted++
    }
    return { skipped, adopted, inserted, updated }
  })
}

/** Hard-delete synced, active local tasks whose backend_id is NOT in `apiIds`
 *  (cleans up tasks deleted / moved to staged on the backend). GUARD: an EMPTY
 *  `apiIds` is a NO-OP — never wipe all local data on an empty-200 response. FIX
 *  (ii): returns the deleted local ids for embedding-index eviction. */
export function hardDeleteAbsentTasksOn(d: TaskStoreDb, apiIds: string[]): number[] {
  if (apiIds.length === 0) return []
  return tx(d, () => {
    const candidates = d
      .prepare(
        `SELECT id, backend_id AS backendId FROM action_items
           WHERE completed = 0 AND deleted = 0 AND backend_id IS NOT NULL AND backend_synced = 1`
      )
      .all() as { id: number; backendId: string | null }[]
    const keep = new Set(apiIds)
    const toDelete = candidates
      .filter((c) => c.backendId && !keep.has(c.backendId))
      .map((c) => c.id)
    for (const id of toDelete) d.prepare('DELETE FROM action_items WHERE id = ?').run(id)
    return toDelete
  })
}

/** Unsynced local action items (backend_synced = 0 AND backend_id NULL/''), active,
 *  oldest-first. By default excludes rows created in the last 30s (an API call may be
 *  in-flight); `includeRecent` skips that age filter. */
export function getUnsyncedActionItemsOn(
  d: TaskStoreDb,
  opts: { includeRecent?: boolean; now: number }
): ActionItemRecord[] {
  const params: unknown[] = []
  let where = "WHERE backend_synced = 0 AND (backend_id IS NULL OR backend_id = '') AND deleted = 0"
  if (!opts.includeRecent) {
    where += ' AND created_at < ?'
    params.push(opts.now - 30_000)
  }
  const rows = d
    .prepare(`SELECT ${ACTION_COLUMNS} FROM action_items ${where} ORDER BY created_at ASC`)
    .all(...params) as ActionItemRow[]
  return rows.map(mapAction)
}

/** All action-item embeddings for loading the in-memory index. */
export function getAllActionItemEmbeddingsOn(d: TaskStoreDb): TaskEmbeddingRow[] {
  const rows = d
    .prepare('SELECT id, embedding FROM action_items WHERE embedding IS NOT NULL')
    .all() as { id: number; embedding: Buffer | Uint8Array }[]
  return rows.map((r) => ({ id: r.id, embedding: bufferToVector(r.embedding) }))
}

/** Store the embedding BLOB for one action item. */
export function updateActionItemEmbeddingOn(
  d: TaskStoreDb,
  id: number,
  vector: Float32Array
): void {
  d.prepare('UPDATE action_items SET embedding = ? WHERE id = ?').run(vectorToBuffer(vector), id)
}

/** Active action items still missing an embedding (backfill), newest-first. */
export function getActionItemsMissingEmbeddingsOn(
  d: TaskStoreDb,
  limit = 100
): { id: number; description: string }[] {
  return d
    .prepare(
      `SELECT id, description FROM action_items
         WHERE embedding IS NULL AND deleted = 0 ORDER BY created_at DESC LIMIT ?`
    )
    .all(limit) as { id: number; description: string }[]
}

/** Insert an action item at a specific relevance_score, shifting existing active
 *  tasks at that score-or-lower down by 1 to keep scores dense + unique (score 1 =
 *  top). Forces backend_synced = 0. Returns the inserted record. */
export function insertActionItemWithScoreShiftOn(
  d: TaskStoreDb,
  input: ActionItemInput
): ActionItemRecord {
  return tx(d, () => {
    if (input.relevanceScore != null) {
      d.prepare(
        `UPDATE action_items SET relevance_score = relevance_score + 1
           WHERE relevance_score IS NOT NULL AND relevance_score >= ?
             AND completed = 0 AND deleted = 0`
      ).run(input.relevanceScore)
    }
    const id = Number(
      d
        .prepare(
          `INSERT INTO action_items ${ACTION_INSERT_COLUMNS} VALUES ${ACTION_INSERT_PLACEHOLDERS}`
        )
        .run(...actionInsertParams(input, false)).lastInsertRowid
    )
    const rec = getActionByIdOn(d, id)
    if (!rec) throw new Error('insertActionItemWithScoreShift: row vanished after insert')
    return rec
  })
}

/** Selective re-rank: pull the re-ranked tasks out of the current score order,
 *  reinsert them at their new 1-based positions, then renumber every active task
 *  1..N (relevance_score = position, scored_at = updated_at = now). */
export function applyActionItemRerankingOn(
  d: TaskStoreDb,
  reranks: TaskRerank[],
  now: number
): void {
  applyRerankingOn(d, 'action_items', reranks, now)
}

/** Highest-relevance active tasks (lowest score = most important). */
export function getTopRelevanceActionItemsOn(
  d: TaskStoreDb,
  limit = 30
): { id: number; description: string; priority: string | null; relevanceScore: number | null }[] {
  return d
    .prepare(
      `SELECT id, description, priority, relevance_score AS relevanceScore FROM action_items
         WHERE completed = 0 AND deleted = 0 AND relevance_score IS NOT NULL
         ORDER BY relevance_score ASC LIMIT ?`
    )
    .all(limit) as {
    id: number
    description: string
    priority: string | null
    relevanceScore: number | null
  }[]
}

// FTS5 query sanitizer (Mac's): keep letters/digits/`*`/space, collapse the rest to
// spaces, split on whitespace, rejoin single-spaced. Empty → no query.
function sanitizeFtsQuery(query: string): string {
  return query
    .split('')
    .map((c) => (/[A-Za-z0-9*]/.test(c) ? c : ' '))
    .join('')
    .split(/\s+/)
    .filter((t) => t.length > 0)
    .join(' ')
}

/** Full-text search over action-item descriptions, BM25-ranked. Excludes deleted
 *  rows always; `includeCompleted` (default false) keeps the historical
 *  active-only behavior — set true so the task-extraction dedup tool
 *  (`search_keywords`) also sees COMPLETED action items (Mac parity: Mac's
 *  keyword search runs with `includeCompleted:true`; Windows has no deleted rows
 *  to add). Default false preserves every existing caller's behavior exactly. */
export function searchActionItemsFTSOn(
  d: TaskStoreDb,
  query: string,
  limit = 20,
  includeCompleted = false
): {
  id: number
  description: string
  completed: boolean
  deleted: boolean
  deletedBy: string | null
  relevanceScore: number | null
}[] {
  const q = sanitizeFtsQuery(query)
  if (!q) return []
  const completedClause = includeCompleted ? '' : 'AND a.completed = 0 '
  const rows = d
    .prepare(
      `SELECT a.id, a.description, a.completed, a.deleted, a.deleted_by AS deletedBy,
              a.relevance_score AS relevanceScore
         FROM action_items a JOIN action_items_fts fts ON fts.rowid = a.id
         WHERE action_items_fts MATCH ? ${completedClause}AND a.deleted = 0
         ORDER BY bm25(action_items_fts) ASC LIMIT ?`
    )
    .all(q, limit) as {
    id: number
    description: string
    completed: number
    deleted: number
    deletedBy: string | null
    relevanceScore: number | null
  }[]
  return rows.map((r) => ({
    id: r.id,
    description: r.description,
    completed: r.completed !== 0,
    deleted: r.deleted !== 0,
    deletedBy: r.deletedBy,
    relevanceScore: r.relevanceScore
  }))
}

// ===========================================================================
// staged_tasks
// ===========================================================================

const STAGED_INSERT_COLUMNS =
  '(backend_id, backend_synced, description, completed, deleted, deleted_by, source, ' +
  'conversation_id, priority, category, tags_json, due_at, screenshot_id, confidence, ' +
  'source_app, window_title, context_summary, current_activity, metadata_json, embedding, ' +
  'relevance_score, scored_at, created_at, updated_at)'

const STAGED_INSERT_PLACEHOLDERS =
  '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'

function stagedInsertParams(input: StagedTaskInput, backendSynced: boolean): unknown[] {
  return [
    input.backendId ?? null,
    backendSynced ? 1 : 0,
    input.description,
    input.completed ? 1 : 0,
    input.deleted ? 1 : 0,
    input.deletedBy ?? null,
    input.source ?? null,
    input.conversationId ?? null,
    input.priority ?? null,
    input.category ?? null,
    serializeTags(input.tags),
    input.dueAt ?? null,
    input.screenshotId ?? null,
    input.confidence ?? null,
    input.sourceApp ?? null,
    input.windowTitle ?? null,
    input.contextSummary ?? null,
    input.currentActivity ?? null,
    input.metadataJson ?? null,
    input.embedding ? vectorToBuffer(input.embedding) : null,
    input.relevanceScore ?? null,
    input.scoredAt ?? null,
    input.createdAt,
    input.updatedAt
  ]
}

function getStagedByIdRow(d: TaskStoreDb, id: number): StagedTaskRow | undefined {
  return d.prepare(`SELECT ${STAGED_COLUMNS} FROM staged_tasks WHERE id = ?`).get(id) as
    | StagedTaskRow
    | undefined
}

/** Insert a locally-extracted staged task (forces backend_synced = 0). */
export function insertLocalStagedTaskOn(d: TaskStoreDb, input: StagedTaskInput): StagedTaskRecord {
  const id = Number(
    d
      .prepare(
        `INSERT INTO staged_tasks ${STAGED_INSERT_COLUMNS} VALUES ${STAGED_INSERT_PLACEHOLDERS}`
      )
      .run(...stagedInsertParams(input, false)).lastInsertRowid
  )
  const row = getStagedByIdRow(d, id)
  if (!row) throw new Error('insertLocalStagedTask: row vanished after insert')
  return mapStaged(row)
}

/** Insert a staged task at a specific relevance_score, shifting existing active
 *  staged tasks at that score-or-lower down by 1. Forces backend_synced = 0. */
export function insertStagedTaskWithScoreShiftOn(
  d: TaskStoreDb,
  input: StagedTaskInput
): StagedTaskRecord {
  return tx(d, () => {
    if (input.relevanceScore != null) {
      d.prepare(
        `UPDATE staged_tasks SET relevance_score = relevance_score + 1
           WHERE relevance_score IS NOT NULL AND relevance_score >= ?
             AND completed = 0 AND deleted = 0`
      ).run(input.relevanceScore)
    }
    const id = Number(
      d
        .prepare(
          `INSERT INTO staged_tasks ${STAGED_INSERT_COLUMNS} VALUES ${STAGED_INSERT_PLACEHOLDERS}`
        )
        .run(...stagedInsertParams(input, false)).lastInsertRowid
    )
    const row = getStagedByIdRow(d, id)
    if (!row) throw new Error('insertStagedTaskWithScoreShift: row vanished after insert')
    return mapStaged(row)
  })
}

/** Mark a locally-inserted staged task synced (Mac's already-DEFENSIVE dedup-merge,
 *  ported verbatim): if another row already holds `backendId`, keep it and delete
 *  this duplicate; catch the UNIQUE-constraint race the same way. `source` is
 *  accepted for call-site parity (unused). Returns which row survived. */
export function markSyncedStagedTaskOn(
  d: TaskStoreDb,
  localId: number,
  backendId: string,
  now: number,
  _source?: string | null
): MarkSyncedResult {
  return markSyncedOn(d, 'staged_tasks', localId, backendId, now)
}

/** HARD-delete a staged task by local id. FIX (i): exposed + wired (Mac has it but
 *  never calls it). FIX (ii): returns the deleted ids for embedding-index eviction. */
export function deleteStagedTaskByIdOn(d: TaskStoreDb, id: number): number[] {
  const changes = Number(d.prepare('DELETE FROM staged_tasks WHERE id = ?').run(id).changes)
  return changes > 0 ? [id] : []
}

/** HARD-delete a staged task by backend_id. FIX (i) + FIX (ii) (see deleteStagedTaskById). */
export function deleteStagedTaskByBackendIdOn(d: TaskStoreDb, backendId: string): number[] {
  return deleteByBackendIdOn(d, 'staged_tasks', backendId)
}

/** Unsynced staged tasks for retry (backend_synced = 0, active), newest-first. */
export function getUnsyncedStagedTasksOn(d: TaskStoreDb, limit = 50): StagedTaskRecord[] {
  const rows = d
    .prepare(
      `SELECT ${STAGED_COLUMNS} FROM staged_tasks
         WHERE backend_synced = 0 AND deleted = 0 ORDER BY created_at DESC LIMIT ?`
    )
    .all(limit) as StagedTaskRow[]
  return rows.map(mapStaged)
}

/** Active staged tasks, newest-first. */
export function getAllStagedTasksOn(d: TaskStoreDb, limit = 10000): StagedTaskRecord[] {
  const rows = d
    .prepare(
      `SELECT ${STAGED_COLUMNS} FROM staged_tasks
         WHERE deleted = 0 AND completed = 0 ORDER BY created_at DESC LIMIT ?`
    )
    .all(limit) as StagedTaskRow[]
  return rows.map(mapStaged)
}

/** Scored active staged tasks with backend ids, for syncing scores to the backend. */
export function getAllScoredStagedTasksOn(
  d: TaskStoreDb
): { backendId: string; relevanceScore: number }[] {
  return d
    .prepare(
      `SELECT backend_id AS backendId, relevance_score AS relevanceScore FROM staged_tasks
         WHERE backend_id IS NOT NULL AND relevance_score IS NOT NULL
           AND deleted = 0 AND completed = 0`
    )
    .all() as { backendId: string; relevanceScore: number }[]
}

/** One staged task by local id, or null if it is completed/deleted (spec: active-only). */
export function getStagedTaskOn(d: TaskStoreDb, id: number): StagedTaskRecord | null {
  const row = getStagedByIdRow(d, id)
  if (!row || row.completed !== 0 || row.deleted !== 0) return null
  return mapStaged(row)
}

/** All staged-task embeddings for the in-memory index (active only, per spec). */
export function getAllStagedTaskEmbeddingsOn(d: TaskStoreDb): TaskEmbeddingRow[] {
  const rows = d
    .prepare(
      'SELECT id, embedding FROM staged_tasks WHERE embedding IS NOT NULL AND completed = 0 AND deleted = 0'
    )
    .all() as { id: number; embedding: Buffer | Uint8Array }[]
  return rows.map((r) => ({ id: r.id, embedding: bufferToVector(r.embedding) }))
}

/** Store the embedding BLOB for one staged task. */
export function updateStagedTaskEmbeddingOn(
  d: TaskStoreDb,
  id: number,
  vector: Float32Array
): void {
  d.prepare('UPDATE staged_tasks SET embedding = ? WHERE id = ?').run(vectorToBuffer(vector), id)
}

/** Active staged tasks still missing an embedding (backfill), newest-first. */
export function getStagedTasksMissingEmbeddingsOn(
  d: TaskStoreDb,
  limit = 100
): { id: number; description: string }[] {
  return d
    .prepare(
      `SELECT id, description FROM staged_tasks
         WHERE embedding IS NULL AND deleted = 0 ORDER BY created_at DESC LIMIT ?`
    )
    .all(limit) as { id: number; description: string }[]
}

/** Selective re-rank of staged tasks (same algorithm as applyActionItemReranking). */
export function applyStagedTaskRerankingOn(
  d: TaskStoreDb,
  reranks: TaskRerank[],
  now: number
): void {
  applyRerankingOn(d, 'staged_tasks', reranks, now)
}

/** Count active (non-completed, non-deleted) staged tasks. */
export function countActiveStagedTasksOn(d: TaskStoreDb): number {
  return (
    d
      .prepare('SELECT COUNT(*) AS n FROM staged_tasks WHERE completed = 0 AND deleted = 0')
      .get() as { n: number }
  ).n
}

/** Full-text search over active staged-task descriptions, BM25-ranked. */
export function searchStagedTasksFTSOn(
  d: TaskStoreDb,
  query: string,
  limit = 20
): { id: number; description: string; relevanceScore: number | null }[] {
  const q = sanitizeFtsQuery(query)
  if (!q) return []
  return d
    .prepare(
      `SELECT s.id, s.description, s.relevance_score AS relevanceScore
         FROM staged_tasks s JOIN staged_tasks_fts fts ON fts.rowid = s.id
         WHERE staged_tasks_fts MATCH ? AND s.completed = 0 AND s.deleted = 0
         ORDER BY bm25(staged_tasks_fts) ASC LIMIT ?`
    )
    .all(q, limit) as { id: number; description: string; relevanceScore: number | null }[]
}
