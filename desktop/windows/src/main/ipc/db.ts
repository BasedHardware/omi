import Database from 'better-sqlite3'
import { app } from 'electron'
import { basename, join } from 'path'
import { categorize } from '../usage/category'
import { isNewLocalDay } from '../usage/usageDay'
import { buildRewindFtsMatch } from '../rewind/rewindSearchQuery'
import { addColumnIfMissing as ensureColumn, runMigrations } from './dbMigrations'
import { applyRewindEmbeddingSchema } from './rewindEmbeddingSchema'
import { wipeUserDataOn } from './dbWipe'
import {
  insertVoiceTurnOn,
  listPendingVoiceTurnsOn,
  markVoiceTurnAckedOn,
  recordVoiceTurnFailureOn,
  type VoiceTurnOutboxDb
} from './voiceTurnOutbox'
import { bufferToVector, vectorToBuffer } from './taskEmbeddingVector'
import {
  listConversationFoldersOn,
  replaceConversationFoldersOn,
  upsertConversationFolderOn,
  deleteConversationFolderOn,
  type ConversationFoldersDb
} from './conversationFolders'
import { scanTopKBySimilarity } from '../rewind/embedVector'
// The privacy/backfill/scan SQL lives in one importable module so production and
// the SQL tests run byte-identical statements — a re-declared test copy drifts
// (it did, twice). See rewindEmbeddingSql.ts.
import {
  DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL,
  DROP_ORPHANED_EMBEDDING_VECTORS_SQL,
  REWIND_COLUMNS_QUALIFIED,
  rewindFramesNeedingEmbeddingSql,
  searchEmbeddingPageSql
} from './rewindEmbeddingSql'
import type {
  AiUserProfileInput,
  AiUserProfileRecord,
  FocusSessionInput,
  FocusSessionRecord,
  TaskEmbeddingRecord,
  AppUsageRecord,
  ChatMessage,
  ConversationFolder,
  ConversationSyncPatch,
  ConversationSyncState,
  FileIndexDigest,
  IndexedAppRecord,
  IndexedFileRecord,
  InsightPayload,
  InsightRecord,
  KgSqlResult,
  KnowledgeGraph,
  LocalConversation,
  LocalKGStatus,
  LocalKnowledgeGraph,
  OnboardingGraphNode,
  OnboardingGraphEdge,
  OcrLine,
  RewindFrame,
  SyncSegment,
  UsageCategory,
  VoiceTurnOutboxEntry,
  VoiceTurnOutboxInput
} from '../../shared/types'
import { perfMark } from '../../shared/perf'

// Time a synchronous DB helper and emit a perf mark with its duration in ms.
// Always-on (perfMark is a no-op unless OMI_PERF_LOG is set), so the bench can
// measure DB read throughput without affecting normal runs.
function timed<T>(name: string, fn: () => T): T {
  const t = performance.now()
  try {
    return fn()
  } finally {
    perfMark(`db:${name}`, { ms: performance.now() - t })
  }
}

let db: Database.Database | null = null
let roDb: Database.Database | null = null

// (ensureColumn — add a column only if missing, so existing databases migrate
// forward without data loss — is dbMigrations.addColumnIfMissing, shared with
// the versioned migrations so the idiom exists once.)

// Drop a table whose on-disk schema predates the current one (detected by a
// missing expected column), so the CREATE TABLE IF NOT EXISTS below can recreate
// it fresh. Used for the local_kg_* tables: an abandoned experiment left an
// incompatible schema (node_id/edge_id PKs, no summary/source columns) that
// silently broke every INSERT. These tables are a derived cache with no user
// data worth migrating, so recreating them is safe.
function dropIfMissingColumn(d: Database.Database, table: string, col: string): void {
  const exists = d.prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?").get(table)
  if (!exists) return
  const cols = d.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]
  if (!cols.some((c) => c.name === col)) d.exec(`DROP TABLE ${table}`)
}

function get(): Database.Database {
  if (db) return db
  // OMI_DB_PATH lets the bench harness point at a throwaway DB so benchmarking
  // never reads or writes the user's real omi.db.
  const file = process.env.OMI_DB_PATH ?? join(app.getPath('userData'), 'omi.db')
  db = new Database(file)
  // WAL mode: allows main-thread reads to proceed concurrently while the KG
  // write worker holds the write lock. Synchronous stays at the default FULL so
  // non-KG tables (local_conversation etc.) are not at power-loss risk.
  // The worker sets synchronous=NORMAL only on its own connection.
  db.pragma('journal_mode = WAL')
  // Migrate away the incompatible local_kg_* schema from the parked KG experiment.
  dropIfMissingColumn(db, 'local_kg_nodes', 'summary')
  dropIfMissingColumn(db, 'local_kg_edges', 'id')
  // Track 4 (Rewind semantic search): drop-then-create, as one ordered unit, in a
  // module the schema tests can actually load. See rewindEmbeddingSchema.ts — a
  // PR0-era rewind_embeddings has no `hash` column, and indexing it would throw
  // out of this bootstrap and take every db-backed IPC handler down with it.
  applyRewindEmbeddingSchema(db)
  db.exec(`
    CREATE TABLE IF NOT EXISTS caption_event (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id TEXT NOT NULL,
      ts INTEGER NOT NULL,
      caption TEXT NOT NULL,
      ocr_text TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_caption_convo ON caption_event(conversation_id, ts);

    CREATE TABLE IF NOT EXISTS local_conversation (
      id TEXT PRIMARY KEY,
      started_at INTEGER NOT NULL,
      ended_at INTEGER NOT NULL,
      transcript TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      kind TEXT NOT NULL DEFAULT 'recording',
      messages TEXT,
      title TEXT
    );

    CREATE TABLE IF NOT EXISTS indexed_files (
      path TEXT PRIMARY KEY,
      filename TEXT NOT NULL,
      extension TEXT NOT NULL,
      file_type TEXT NOT NULL,
      size_bytes INTEGER NOT NULL,
      folder TEXT NOT NULL,
      depth INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      modified_at INTEGER NOT NULL,
      indexed_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_indexed_files_type ON indexed_files(file_type);

    CREATE TABLE IF NOT EXISTS local_kg_nodes (
      id TEXT PRIMARY KEY,
      label TEXT NOT NULL,
      node_type TEXT NOT NULL,
      summary TEXT NOT NULL,
      source TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_local_kg_nodes_label ON local_kg_nodes(label);
    CREATE INDEX IF NOT EXISTS idx_local_kg_nodes_type ON local_kg_nodes(node_type);

    CREATE TABLE IF NOT EXISTS local_kg_edges (
      id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      target_id TEXT NOT NULL,
      label TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );

    -- Onboarding brain-map graph (sandbox/ui). Separate tables from the chat-KG
    -- local_kg_* above; disposable progressive-reveal data only.
    CREATE TABLE IF NOT EXISTS onboarding_kg_nodes (
      node_id TEXT PRIMARY KEY,
      label TEXT NOT NULL,
      node_type TEXT NOT NULL,
      aliases_json TEXT,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS onboarding_kg_edges (
      edge_id TEXT PRIMARY KEY,
      source_id TEXT NOT NULL,
      target_id TEXT NOT NULL,
      label TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS app_usage (
      exe_path TEXT PRIMARY KEY,
      exe_name TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'other',
      total_seconds INTEGER NOT NULL DEFAULT 0,
      last_used INTEGER NOT NULL DEFAULT 0,
      distinct_days INTEGER NOT NULL DEFAULT 0,
      first_seen INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS rewind_frames (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      app TEXT NOT NULL DEFAULT '',
      window_title TEXT NOT NULL DEFAULT '',
      process_name TEXT NOT NULL DEFAULT '',
      ocr_text TEXT NOT NULL DEFAULT '',
      image_path TEXT NOT NULL,
      width INTEGER NOT NULL DEFAULT 0,
      height INTEGER NOT NULL DEFAULT 0,
      indexed INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_rewind_frames_ts ON rewind_frames(ts);
    CREATE INDEX IF NOT EXISTS idx_rewind_frames_indexed ON rewind_frames(indexed);

    CREATE TABLE IF NOT EXISTS insights (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      headline TEXT NOT NULL,
      advice TEXT NOT NULL,
      reasoning TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL DEFAULT 'other',
      source_app TEXT NOT NULL DEFAULT '',
      confidence REAL NOT NULL DEFAULT 0,
      dismissed INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_insights_ts ON insights(ts);

    -- --- Track 4: Rewind FTS5 (full-text search over rewind_frames) ---
    -- External-content FTS index mirroring rewind_frames(id): the triggers below
    -- keep it in sync on every write, so search reads BM25-ranked matches without
    -- a full-table LIKE scan. Existing rows are backfilled once by dbMigrations v2
    -- (which runs AFTER this block — see runMigrations call in get()).
    CREATE VIRTUAL TABLE IF NOT EXISTS rewind_frames_fts USING fts5(
      ocr_text, window_title, app,
      content='rewind_frames', content_rowid='id', tokenize='unicode61'
    );
    CREATE TRIGGER IF NOT EXISTS rewind_frames_ai AFTER INSERT ON rewind_frames BEGIN
      INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
      VALUES (new.id, new.ocr_text, new.window_title, new.app);
    END;
    CREATE TRIGGER IF NOT EXISTS rewind_frames_ad AFTER DELETE ON rewind_frames BEGIN
      INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
      VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
    END;
    CREATE TRIGGER IF NOT EXISTS rewind_frames_au AFTER UPDATE ON rewind_frames BEGIN
      INSERT INTO rewind_frames_fts(rewind_frames_fts, rowid, ocr_text, window_title, app)
      VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app);
      INSERT INTO rewind_frames_fts(rowid, ocr_text, window_title, app)
      VALUES (new.id, new.ocr_text, new.window_title, new.app);
    END;

    -- (Track 4's rewind_embeddings / rewind_embedding_vectors are created by
    -- applyRewindEmbeddingSchema() above, not here — they need a drop-first
    -- migration that must not be interleaved with this block.)

    -- --- Track 4: Conversation folders ---
    CREATE TABLE IF NOT EXISTS conversation_folders (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      color TEXT,
      icon TEXT,
      order_idx INTEGER NOT NULL DEFAULT 0,
      is_system INTEGER NOT NULL DEFAULT 0,
      conversation_count INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER
    );

    -- --- Track 4: Per-conversation speaker names ---
    CREATE TABLE IF NOT EXISTS conversation_speaker_names (
      conversation_id TEXT NOT NULL,
      speaker_id INTEGER NOT NULL,
      name TEXT,
      person_id TEXT,
      is_user INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (conversation_id, speaker_id)
    );

    -- --- Track 4: Live notes (meeting minutes; AI-generated or manual) ---
    CREATE TABLE IF NOT EXISTS live_notes (
      id TEXT PRIMARY KEY,
      session_id TEXT NOT NULL,
      text TEXT NOT NULL,
      is_ai INTEGER NOT NULL DEFAULT 0,
      seg_start INTEGER,
      seg_end INTEGER,
      created_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_live_notes_session ON live_notes(session_id);

    -- --- Track 4: Crash-rescue live-segment buffer ---
    CREATE TABLE IF NOT EXISTS rescue_segments (
      session_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      segment_json TEXT NOT NULL,
      ts INTEGER NOT NULL,
      PRIMARY KEY (session_id, seq)
    );

    -- --- Track 4: File-index scan state (last_scan_at per root, etc.) ---
    CREATE TABLE IF NOT EXISTS file_index_meta (
      key TEXT PRIMARY KEY,
      value TEXT
    );

    -- --- Track 4: App-level flags (clean-exit, launch-at-login migrated). NOT
    -- user-scoped — deliberately excluded from USER_DATA_TABLES so it survives
    -- sign-out. ---
    CREATE TABLE IF NOT EXISTS app_meta (
      key TEXT PRIMARY KEY,
      value TEXT
    );

    -- Track 2: Voice & PTT depth (voice turn outbox)
    -- Durable outbox for a voice turn (PTT or realtime-session utterance) that
    -- must survive an app restart mid-flight. Mirrors the macOS
    -- RealtimeVoiceTurnOutbox 1:1: idempotency_key is the natural per-turn dedup
    -- key (one UUID reused across the turn's completed / interrupted / optimistic
    -- variants), a positive kernel ack deletes the row, and the drain scans
    -- pending rows oldest-first. Unconsumed until Phase B / Track 1 wire the
    -- kernel-write path — the table lands early to claim the shared additive file.
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
  `)
  /* ---- Track 3 (proactive intelligence & memory) ---- */
  // Net-new tables — CREATE TABLE IF NOT EXISTS only, no numbered migration, so
  // sibling tracks never collide on a user_version bump. See shared/types.ts for
  // the record shapes and the readers/writers at the end of this file.
  db.exec(`
    CREATE TABLE IF NOT EXISTS ai_user_profiles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      profile_text TEXT NOT NULL,
      data_sources_used TEXT,
      generated_at INTEGER NOT NULL,
      backend_synced INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_ai_user_profiles_generated_at ON ai_user_profiles(generated_at);

    CREATE TABLE IF NOT EXISTS focus_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      screenshot_id TEXT,
      status TEXT NOT NULL,
      app_or_site TEXT,
      description TEXT,
      message TEXT,
      duration_seconds INTEGER NOT NULL DEFAULT 0,
      backend_id TEXT,
      backend_synced INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL,
      window_title TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_focus_sessions_created_at ON focus_sessions(created_at);

    CREATE TABLE IF NOT EXISTS task_embeddings (
      source TEXT NOT NULL,
      item_id TEXT NOT NULL,
      vector BLOB NOT NULL,
      text TEXT NOT NULL,
      model TEXT NOT NULL,
      updated_at INTEGER NOT NULL,
      PRIMARY KEY (source, item_id)
    );
  `)
  // Migrate older databases that have local_conversation without these columns.
  ensureColumn(db, 'local_conversation', 'kind', "TEXT NOT NULL DEFAULT 'recording'")
  ensureColumn(db, 'local_conversation', 'messages', 'TEXT')
  ensureColumn(db, 'local_conversation', 'title', 'TEXT')
  // Node provenance for the LLM-synthesized graph (additive).
  ensureColumn(db, 'local_kg_nodes', 'aliases_json', 'TEXT')
  ensureColumn(db, 'local_kg_nodes', 'source_refs', 'TEXT')
  // Resolved .lnk target exe, for joining indexed apps to app_usage (additive).
  ensureColumn(db, 'indexed_files', 'target_path', 'TEXT')
  // --- Track 4: additive columns on existing tables ---
  // Per-line OCR bounding boxes (JSON) for a future on-image highlight overlay.
  ensureColumn(db, 'rewind_frames', 'ocr_lines_json', 'TEXT')
  // Conversation starring + folder assignment (local mirror of the cloud fields).
  ensureColumn(db, 'local_conversation', 'starred', 'INTEGER NOT NULL DEFAULT 0')
  ensureColumn(db, 'local_conversation', 'folder_id', 'TEXT')
  // (rewind_embeddings is migrated by migrateRewindEmbeddingSchema, BEFORE the
  // exec above — an ensureColumn here would run far too late to save it.)
  // Versioned migrations (PRAGMA user_version) — everything beyond the additive
  // baseline above. Ordered + exactly-once; see dbMigrations.ts.
  runMigrations(db)
  return db
}

type LocalConversationRow = {
  id: string
  startedAt: number
  endedAt: number
  transcript: string
  createdAt: number
  kind: string | null
  messages: string | null
  title: string | null
  syncState: string | null
  segmentsJson: string | null
  cloudId: string | null
  syncAttempts: number | null
  syncError: string | null
}

const SYNC_STATES: ConversationSyncState[] = [
  'local_only',
  'pending',
  'posting',
  'done',
  'failed',
  'unconfirmed'
]

function parseSegments(json: string | null): SyncSegment[] | null {
  if (!json) return null
  try {
    const v = JSON.parse(json)
    return Array.isArray(v) ? (v as SyncSegment[]) : null
  } catch {
    return null
  }
}

function mapLocalConversation(row: LocalConversationRow): LocalConversation {
  return {
    id: row.id,
    startedAt: row.startedAt,
    endedAt: row.endedAt,
    transcript: row.transcript,
    createdAt: row.createdAt,
    kind: row.kind === 'chat' ? 'chat' : 'recording',
    messages: row.messages ? (JSON.parse(row.messages) as ChatMessage[]) : undefined,
    title: row.title ?? null,
    syncState: SYNC_STATES.includes(row.syncState as ConversationSyncState)
      ? (row.syncState as ConversationSyncState)
      : 'local_only',
    // Tolerate a corrupt segments blob: one bad row must not throw and break the
    // whole listLocalConversations() read.
    segments: parseSegments(row.segmentsJson),
    cloudId: row.cloudId ?? null,
    syncAttempts: row.syncAttempts ?? 0,
    syncError: row.syncError ?? null
  }
}

const LOCAL_CONVERSATION_COLUMNS =
  'id, started_at AS startedAt, ended_at AS endedAt, transcript, created_at AS createdAt, kind, messages, title, ' +
  'sync_state AS syncState, segments_json AS segmentsJson, cloud_id AS cloudId, sync_attempts AS syncAttempts, sync_error AS syncError'

export function insertLocalConversation(c: LocalConversation): void {
  get()
    .prepare(
      'INSERT OR REPLACE INTO local_conversation (id, started_at, ended_at, transcript, created_at, kind, messages, title, sync_state, segments_json, cloud_id, sync_attempts, sync_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
    )
    .run(
      c.id,
      c.startedAt,
      c.endedAt,
      c.transcript,
      c.createdAt,
      c.kind ?? 'recording',
      c.messages ? JSON.stringify(c.messages) : null,
      c.title ?? null,
      c.syncState ?? 'local_only',
      c.segments && c.segments.length > 0 ? JSON.stringify(c.segments) : null,
      c.cloudId ?? null,
      c.syncAttempts ?? 0,
      c.syncError ?? null
    )
}

/** Persist an outbox transition (see ConversationSyncState / lib/sync/outbox.ts).
 *  cloudId/syncError only change when present in the patch; incrementAttempts
 *  bumps the counter atomically with the state write. */
export function updateLocalConversationSync(id: string, patch: ConversationSyncPatch): void {
  const sets = ['sync_state = ?']
  const params: unknown[] = [patch.syncState]
  if (patch.cloudId !== undefined) {
    sets.push('cloud_id = ?')
    params.push(patch.cloudId)
  }
  if (patch.syncError !== undefined) {
    sets.push('sync_error = ?')
    params.push(patch.syncError)
  }
  if (patch.incrementAttempts) sets.push('sync_attempts = sync_attempts + 1')
  params.push(id)
  get()
    .prepare(`UPDATE local_conversation SET ${sets.join(', ')} WHERE id = ?`)
    .run(...params)
}

/**
 * Atomically claim a row for POSTing: flip it to 'posting' (and bump attempts)
 * ONLY if it is still in a claimable state. Returns true iff this call won the
 * claim. This is the compare-and-swap that makes the pending→posting transition
 * safe against a stale-snapshot second driver (e.g. the Conversations retry pass
 * running with a row it read before an earlier sync moved it on): the loser sees
 * `changes === 0` and backs off instead of re-POSTing (which prod would
 * duplicate, since it ignores client_session_id). 'posting' is intentionally
 * excluded — a row already posting is owned by a live driver; a genuinely
 * crash-orphaned 'posting' row is first recovered to 'unconfirmed' (which IS
 * claimable) by the caller. Optionally resets sync_attempts (manual re-sync).
 */
export function claimConversationForPosting(id: string, resetAttempts = false): boolean {
  const attemptsExpr = resetAttempts ? '1' : 'sync_attempts + 1'
  const r = get()
    .prepare(
      `UPDATE local_conversation SET sync_state = 'posting', sync_attempts = ${attemptsExpr}
         WHERE id = ? AND sync_state IN ('pending', 'failed', 'unconfirmed')`
    )
    .run(id)
  return r.changes > 0
}

// --- Track 4: conversation folders / starred ---
// Thin wrappers over the driver-agnostic CRUD in conversationFolders.ts (extracted
// so the SQL is unit-testable under plain-node vitest with node:sqlite; see that
// file + its test). get() returns a better-sqlite3 Database whose prepared
// statements satisfy the ConversationFoldersDb shape structurally — cast to bridge
// the driver duck-typing, same idiom the voice-turn-outbox wrappers use.
function foldersDb(): ConversationFoldersDb {
  return get() as unknown as ConversationFoldersDb
}

export function listConversationFolders(): ConversationFolder[] {
  return listConversationFoldersOn(foldersDb())
}

export function replaceConversationFolders(folders: ConversationFolder[]): void {
  replaceConversationFoldersOn(foldersDb(), folders)
}

export function upsertConversationFolder(folder: ConversationFolder): void {
  upsertConversationFolderOn(foldersDb(), folder)
}

export function deleteConversationFolder(id: string): void {
  deleteConversationFolderOn(foldersDb(), id)
}

export function updateLocalConversationTitle(id: string, title: string): void {
  get()
    .prepare('UPDATE local_conversation SET title = ? WHERE id = ?')
    .run(title.trim() || null, id)
}

export function getLocalConversation(id: string): LocalConversation | null {
  return timed('getLocalConversation', () => {
    const row = get()
      .prepare(`SELECT ${LOCAL_CONVERSATION_COLUMNS} FROM local_conversation WHERE id = ?`)
      .get(id) as LocalConversationRow | undefined
    return row ? mapLocalConversation(row) : null
  })
}

export function listLocalConversations(): LocalConversation[] {
  return timed('listLocalConversations', () => {
    const rows = get()
      .prepare(
        `SELECT ${LOCAL_CONVERSATION_COLUMNS} FROM local_conversation ORDER BY created_at DESC`
      )
      .all() as LocalConversationRow[]
    return rows.map(mapLocalConversation)
  })
}

export function deleteLocalConversation(id: string): void {
  get().prepare('DELETE FROM local_conversation WHERE id = ?').run(id)
}

export function remapConversationId(fromId: string, toId: string): number {
  const r = get()
    .prepare('UPDATE caption_event SET conversation_id = ? WHERE conversation_id = ?')
    .run(toId, fromId)
  return r.changes
}

// Replace the whole index in batches of 500 (matches macOS commit cadence),
// wrapped per batch in a transaction for speed.
export function replaceIndexedFiles(records: IndexedFileRecord[]): void {
  const d = get()
  const insert = d.prepare(
    `INSERT OR REPLACE INTO indexed_files
       (path, filename, extension, file_type, size_bytes, folder, depth, created_at, modified_at, target_path, indexed_at)
     VALUES (@path, @filename, @extension, @fileType, @sizeBytes, @folder, @depth, @createdAt, @modifiedAt, @targetPath, @indexedAt)`
  )
  const indexedAt = Date.now()
  const writeBatch = d.transaction((rows: IndexedFileRecord[]) => {
    // Default the optional field so better-sqlite3 never sees `undefined`.
    for (const r of rows) insert.run({ ...r, targetPath: r.targetPath ?? null, indexedAt })
  })
  for (let i = 0; i < records.length; i += 500) writeBatch(records.slice(i, i + 500))
}

export function clearIndexedFiles(): void {
  get().prepare('DELETE FROM indexed_files').run()
}

// Clear every user-scoped table on sign-out (see dbWipe.ts for scope + rationale).
// wipeUserDataOn lives in the better-sqlite3-free dbWipe.ts so it is unit-testable
// under plain-node vitest, which can't load this module's Electron-ABI native dep.
export function wipeUserData(): void {
  wipeUserDataOn(get())
}

export function getFileIndexStats(): { filesIndexed: number; byType: Record<string, number> } {
  const total = get().prepare('SELECT COUNT(*) AS n FROM indexed_files').get() as { n: number }
  const rows = get()
    .prepare('SELECT file_type AS t, COUNT(*) AS n FROM indexed_files GROUP BY file_type')
    .all() as { t: string; n: number }[]
  const byType: Record<string, number> = {}
  for (const r of rows) byType[r.t] = r.n
  return { filesIndexed: total.n, byType }
}

// The indexed installed apps (Start-Menu .lnk shortcuts captured as
// file_type='application'), newest-modified first. Used by the renderer to
// synthesize "Uses <App>" memories. modified_at is the .lnk mtime — an
// imperfect usage proxy (see appSelection.rankApps).
type IndexedAppRow = { name: string; path: string; modifiedAt: number; targetPath: string | null }

export function getIndexedApps(limit = 200): IndexedAppRecord[] {
  // Installed apps come ONLY from Start-Menu shortcuts (.lnk) — the Windows
  // analog of /Applications. file_type='application' also covers loose .exe/.msi
  // (installers in Downloads, venv script-shims, firmware updaters), which are
  // NOT installed apps and otherwise dominate by recency. Restrict to .lnk.
  const rows = get()
    .prepare(
      `SELECT filename AS name, path, modified_at AS modifiedAt, target_path AS targetPath
         FROM indexed_files
        WHERE file_type = 'application' AND extension = 'lnk'
        ORDER BY modified_at DESC
        LIMIT ?`
    )
    .all(limit) as IndexedAppRow[]
  return rows.map((r) => ({
    name: r.name,
    path: r.path,
    modifiedAt: r.modifiedAt,
    targetPath: r.targetPath ?? undefined
  }))
}

// --- App usage (foreground-time tracking) ---

// Add `seconds` of foreground time to an app, creating the row if needed and
// bumping distinct_days when `at` falls on a new local day. Called from the
// foreground monitor's flush loop.
export function addAppUsage(exePath: string, seconds: number, at: number): void {
  if (seconds <= 0) return
  const d = get()
  const existing = d
    .prepare(
      'SELECT total_seconds AS totalSeconds, last_used AS lastUsed, distinct_days AS distinctDays FROM app_usage WHERE exe_path = ?'
    )
    .get(exePath) as { totalSeconds: number; lastUsed: number; distinctDays: number } | undefined
  const exeName = basename(exePath)
  const category: UsageCategory = categorize(exeName)
  if (!existing) {
    d.prepare(
      `INSERT INTO app_usage (exe_path, exe_name, category, total_seconds, last_used, distinct_days, first_seen)
       VALUES (?, ?, ?, ?, ?, 1, ?)`
    ).run(exePath, exeName, category, Math.round(seconds), at, at)
    return
  }
  const days = existing.distinctDays + (isNewLocalDay(existing.lastUsed, at) ? 1 : 0)
  d.prepare(
    'UPDATE app_usage SET total_seconds = ?, last_used = ?, distinct_days = ?, category = ? WHERE exe_path = ?'
  ).run(existing.totalSeconds + Math.round(seconds), at, days, category, exePath)
}

// Seed a single app_usage row from historical UserAssist data at onboarding, so
// the first brain-map build ranks by REAL past foreground time (not install
// recency). Keyed by a synthetic `userassist:<name>` exe_path so it never
// collides with live monitor rows (which key by the real exe path), and carries
// the friendly app NAME in exe_name (rankApps matches that to the indexed app).
// `at` is stamped as last_used/first_seen so retention keeps the snapshot for the
// full window. INSERT OR IGNORE: never clobber an existing (e.g. already-seeded)
// row. See usage/userAssist.ts.
export function seedAppUsage(name: string, seconds: number, at: number): void {
  if (seconds <= 0 || !name.trim()) return
  get()
    .prepare(
      `INSERT OR IGNORE INTO app_usage (exe_path, exe_name, category, total_seconds, last_used, distinct_days, first_seen)
       VALUES (?, ?, ?, ?, ?, 1, ?)`
    )
    .run(`userassist:${name}`, name, categorize(name), Math.round(seconds), at, at)
}

export function listAppUsage(): AppUsageRecord[] {
  return get()
    .prepare(
      `SELECT exe_path AS exePath, exe_name AS exeName, category, total_seconds AS totalSeconds,
              last_used AS lastUsed, distinct_days AS distinctDays
         FROM app_usage ORDER BY total_seconds DESC`
    )
    .all() as AppUsageRecord[]
}

// Drop app_usage rows last foregrounded before `cutoff` (ms epoch). Bounds table
// growth and stops long-unused apps from influencing the ranking. Returns the
// number of rows removed.
export function pruneAppUsage(cutoff: number): number {
  return get().prepare('DELETE FROM app_usage WHERE last_used < ?').run(cutoff).changes
}

// --- Local knowledge graph (M2) ---

// replaceLocalGraph — superseded by KgWriteQueue + kgWorker.ts (off-thread WAL
// replace). Retained here so the schema initialisation path in get() and any
// future rollback of the worker approach does not require re-adding this.
export function replaceLocalGraph(graph: LocalKnowledgeGraph): void {
  const d = get()
  const insertNode = d.prepare(
    `INSERT OR REPLACE INTO local_kg_nodes (id, label, node_type, summary, source, created_at, aliases_json, source_refs)
     VALUES (@id, @label, @nodeType, @summary, @source, @createdAt, @aliasesJson, @sourceRefs)`
  )
  const insertEdge = d.prepare(
    `INSERT OR REPLACE INTO local_kg_edges (id, source_id, target_id, label, created_at)
     VALUES (@id, @sourceId, @targetId, @label, @createdAt)`
  )
  const write = d.transaction((g: LocalKnowledgeGraph) => {
    d.prepare('DELETE FROM local_kg_edges').run()
    d.prepare('DELETE FROM local_kg_nodes').run()
    // Map each node to bind params: aliases/sourceRefs are arrays (not bindable),
    // so JSON-encode them (or null). Avoids passing extra object keys too, which
    // better-sqlite3 rejects.
    for (const n of g.nodes) {
      insertNode.run({
        id: n.id,
        label: n.label,
        nodeType: n.nodeType,
        summary: n.summary,
        source: n.source,
        createdAt: n.createdAt,
        aliasesJson: n.aliases?.length ? JSON.stringify(n.aliases) : null,
        sourceRefs: n.sourceRefs?.length ? JSON.stringify(n.sourceRefs) : null
      })
    }
    for (const e of g.edges) insertEdge.run(e)
  })
  write(graph)
}

export function getLocalKGStatus(): LocalKGStatus {
  const d = get()
  const nodes = d.prepare('SELECT COUNT(*) AS n FROM local_kg_nodes').get() as { n: number }
  const edges = d.prepare('SELECT COUNT(*) AS n FROM local_kg_edges').get() as { n: number }
  const last = d.prepare('SELECT MAX(created_at) AS t FROM local_kg_nodes').get() as {
    t: number | null
  }
  return { nodeCount: nodes.n, edgeCount: edges.n, lastBuiltAt: last.t ?? null }
}

// Separate connection opened read-only so the chat agent's execute_sql tool
// physically cannot mutate the DB (defense in depth behind sqlGuard). Lazily
// created; reuses the same omi.db file. ensureSchema runs on the writable
// connection first (get()) so the file/tables exist before we open it.
function getReadonly(): Database.Database {
  if (roDb) return roDb
  get() // ensure the db file + schema exist before opening read-only
  roDb = new Database(join(app.getPath('userData'), 'omi.db'), { readonly: true })
  return roDb
}

// Run a single SELECT (caller MUST pass sqlGuard-validated SQL) and return
// columns + row objects. Throws on a non-SELECT or SQL error; callers treat that
// as "no context". The readonly connection makes writes impossible at the driver.
export function execSafeSelect(sql: string): KgSqlResult {
  const stmt = getReadonly().prepare(sql)
  const rows = stmt.all() as Record<string, unknown>[]
  const columns = rows.length ? Object.keys(rows[0]) : (stmt.columns().map((c) => c.name) ?? [])
  return { columns, rows }
}

type LocalKGNodeRow = {
  id: string
  label: string
  nodeType: string
  summary: string
  source: string
  createdAt: number
  aliasesJson: string | null
  sourceRefs: string | null
}

// Nodes whose label/summary match q, plus every edge incident to a matched
// node. The query is tokenized on whitespace and matched as OR-of-LIKE per
// token, so a multi-word agent query ("projects work tasks") matches a node
// whose label/summary contains ANY token — not only the whole phrase. An empty
// query returns the most recent nodes (used by the chat fallback snapshot).
const SELECT_KG_NODE =
  'SELECT id, label, node_type AS nodeType, summary, source, created_at AS createdAt, aliases_json AS aliasesJson, source_refs AS sourceRefs FROM local_kg_nodes'

// Parse a JSON string[] column, tolerating null/garbage.
function parseJsonArray(s: string | null): string[] | undefined {
  if (!s) return undefined
  try {
    const v = JSON.parse(s)
    return Array.isArray(v) ? (v as string[]) : undefined
  } catch {
    return undefined
  }
}

export function queryKgNodes(q: string, limit = 12): LocalKnowledgeGraph {
  const d = get()
  const tokens = q
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2)
  let nodeRows: LocalKGNodeRow[]
  if (tokens.length === 0) {
    nodeRows = d
      .prepare(`${SELECT_KG_NODE} ORDER BY created_at DESC LIMIT ?`)
      .all(limit) as LocalKGNodeRow[]
  } else {
    const clause = tokens.map(() => '(label LIKE ? OR summary LIKE ?)').join(' OR ')
    const params: unknown[] = []
    for (const t of tokens) params.push(`%${t}%`, `%${t}%`)
    params.push(limit)
    nodeRows = d
      .prepare(`${SELECT_KG_NODE} WHERE ${clause} ORDER BY created_at DESC LIMIT ?`)
      .all(...params) as LocalKGNodeRow[]
  }
  const nodes = nodeRows.map((r) => ({
    id: r.id,
    label: r.label,
    nodeType: r.nodeType as LocalKnowledgeGraph['nodes'][number]['nodeType'],
    summary: r.summary,
    source: r.source as LocalKnowledgeGraph['nodes'][number]['source'],
    createdAt: r.createdAt,
    aliases: parseJsonArray(r.aliasesJson),
    sourceRefs: parseJsonArray(r.sourceRefs)
  }))
  if (nodes.length === 0) {
    return { nodes: [], edges: [] }
  }
  const ids = nodes.map((n) => n.id)
  const placeholders = ids.map(() => '?').join(',')
  const edges = d
    .prepare(
      `SELECT id, source_id AS sourceId, target_id AS targetId, label, created_at AS createdAt
         FROM local_kg_edges
        WHERE source_id IN (${placeholders}) OR target_id IN (${placeholders})`
    )
    .all(...ids, ...ids) as LocalKnowledgeGraph['edges']
  return { nodes, edges }
}

// indexed_files whose filename/folder match q. Excludes apps (file_type
// 'application') unless explicitly requested via fileType.
export function searchIndexedFiles(q: string, fileType?: string, limit = 20): IndexedFileRecord[] {
  const like = `%${q}%`
  const cols =
    'path, filename, extension, file_type AS fileType, size_bytes AS sizeBytes, folder, depth, created_at AS createdAt, modified_at AS modifiedAt'
  const d = get()
  if (fileType) {
    return d
      .prepare(
        `SELECT ${cols} FROM indexed_files
          WHERE (filename LIKE ? OR folder LIKE ?) AND file_type = ?
          ORDER BY modified_at DESC LIMIT ?`
      )
      .all(like, like, fileType, limit) as IndexedFileRecord[]
  }
  return d
    .prepare(
      `SELECT ${cols} FROM indexed_files
        WHERE (filename LIKE ? OR folder LIKE ?) AND file_type != 'application'
        ORDER BY modified_at DESC LIMIT ?`
    )
    .all(like, like, limit) as IndexedFileRecord[]
}

// Aggregate indexed_files into a synthesis digest. Files exclude apps; apps are
// listed separately via getIndexedApps.
export function getFileIndexDigest(): FileIndexDigest {
  const d = get()
  const total = d
    .prepare("SELECT COUNT(*) AS n FROM indexed_files WHERE file_type != 'application'")
    .get() as { n: number }
  const typeRows = d
    .prepare(
      "SELECT file_type AS t, COUNT(*) AS n FROM indexed_files WHERE file_type != 'application' GROUP BY file_type"
    )
    .all() as { t: string; n: number }[]
  const extRows = d
    .prepare(
      "SELECT extension AS e, COUNT(*) AS n FROM indexed_files WHERE file_type != 'application' AND extension != '' GROUP BY extension"
    )
    .all() as { e: string; n: number }[]
  const folderRows = d
    .prepare(
      `SELECT folder, COUNT(*) AS count FROM indexed_files
        WHERE file_type != 'application'
        GROUP BY folder ORDER BY count DESC LIMIT 15`
    )
    .all() as { folder: string; count: number }[]
  const sampleRows = d
    .prepare(
      `SELECT filename FROM indexed_files
        WHERE file_type != 'application'
        ORDER BY modified_at DESC LIMIT 20`
    )
    .all() as { filename: string }[]
  // Recently-active WORKING folders: the macOS-style "what are you working on
  // now" signal. Only folders whose CODE/DOCUMENT files were modified in the
  // last 30 days count, which filters out stale game/media folders (their
  // recent files are config/other, not code/docs). Future-dated files
  // (modified_at > now — bad mtimes like a 2050 stamp) are excluded so they
  // can't masquerade as "recent".
  const now = Date.now()
  const since = now - 30 * 86_400_000
  const activeRows = d
    .prepare(
      `SELECT folder, COUNT(*) AS recentCount, MAX(modified_at) AS lastModified
         FROM indexed_files
        WHERE file_type IN ('code', 'document')
          AND modified_at <= ? AND modified_at > ?
        GROUP BY folder
        ORDER BY recentCount DESC, lastModified DESC
        LIMIT 15`
    )
    .all(now, since) as { folder: string; recentCount: number; lastModified: number }[]
  const byType: Record<string, number> = {}
  for (const r of typeRows) byType[r.t] = r.n
  const byExtension: Record<string, number> = {}
  for (const r of extRows) byExtension[r.e] = r.n
  return {
    totalFiles: total.n,
    byType,
    byExtension,
    topFolders: folderRows,
    activeFolders: activeRows,
    apps: getIndexedApps(100).map((a) => a.name),
    sampleFiles: sampleRows.map((r) => r.filename)
  }
}

// --- Onboarding brain-map graph (sandbox/ui; mirrors macOS KnowledgeGraphStorage) ---
// Separate onboarding_kg_* tables from the chat-KG local_kg_* above. Returns the
// server-shaped KnowledgeGraph (memoryIds: []) so the brain-map renderer can
// consume it with the same shape as the backend graph.

export function loadLocalGraph(): KnowledgeGraph {
  const d = get()
  const nodeRows = d
    .prepare('SELECT node_id, label, node_type, aliases_json FROM onboarding_kg_nodes')
    .all() as { node_id: string; label: string; node_type: string; aliases_json: string | null }[]
  const edgeRows = d
    .prepare('SELECT edge_id, source_id, target_id, label FROM onboarding_kg_edges')
    .all() as { edge_id: string; source_id: string; target_id: string; label: string }[]
  return {
    nodes: nodeRows.map((r) => ({
      id: r.node_id,
      label: r.label,
      nodeType: r.node_type,
      aliases: r.aliases_json ? (JSON.parse(r.aliases_json) as string[]) : [],
      memoryIds: []
    })),
    edges: edgeRows.map((r) => ({
      id: r.edge_id,
      sourceId: r.source_id,
      targetId: r.target_id,
      label: r.label,
      memoryIds: []
    }))
  }
}

// Idempotent upsert by id. Returns the full graph after writing so the renderer
// can update in one round-trip.
export function upsertLocalGraph(
  nodes: OnboardingGraphNode[],
  edges: OnboardingGraphEdge[]
): KnowledgeGraph {
  const d = get()
  const now = Date.now()
  const insertNode = d.prepare(
    `INSERT INTO onboarding_kg_nodes (node_id, label, node_type, aliases_json, created_at, updated_at)
     VALUES (@id, @label, @nodeType, @aliasesJson, @now, @now)
     ON CONFLICT(node_id) DO UPDATE SET label=@label, node_type=@nodeType, aliases_json=@aliasesJson, updated_at=@now`
  )
  const insertEdge = d.prepare(
    `INSERT INTO onboarding_kg_edges (edge_id, source_id, target_id, label, created_at)
     VALUES (@id, @sourceId, @targetId, @label, @now)
     ON CONFLICT(edge_id) DO UPDATE SET source_id=@sourceId, target_id=@targetId, label=@label`
  )
  const write = d.transaction(() => {
    for (const n of nodes) {
      insertNode.run({
        id: n.id,
        label: n.label,
        nodeType: n.nodeType,
        aliasesJson: n.aliases && n.aliases.length ? JSON.stringify(n.aliases) : null,
        now
      })
    }
    for (const e of edges) {
      insertEdge.run({ id: e.id, sourceId: e.sourceId, targetId: e.targetId, label: e.label, now })
    }
  })
  write()
  return loadLocalGraph()
}

export function clearLocalGraph(): void {
  const d = get()
  d.prepare('DELETE FROM onboarding_kg_edges').run()
  d.prepare('DELETE FROM onboarding_kg_nodes').run()
}

// --- Rewind: screen-history timeline ---

const REWIND_COLUMNS =
  'id, ts, app, window_title AS windowTitle, process_name AS processName, ocr_text AS ocrText, image_path AS imagePath, width, height, indexed'

export function insertRewindFrame(f: Omit<RewindFrame, 'id'>): number {
  const r = get()
    .prepare(
      `INSERT INTO rewind_frames (ts, app, window_title, process_name, ocr_text, image_path, width, height, indexed)
       VALUES (@ts, @app, @windowTitle, @processName, @ocrText, @imagePath, @width, @height, @indexed)`
    )
    .run(f)
  return r.lastInsertRowid as number
}

export function listRewindFrames(from: number, to: number): RewindFrame[] {
  return timed(
    'listRewindFrames',
    () =>
      get()
        .prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE ts BETWEEN ? AND ? ORDER BY ts`)
        .all(from, to) as RewindFrame[]
  )
}

// --- Track 4: Rewind FTS5 search ---
// REWIND_COLUMNS_QUALIFIED (columns qualified to `rewind_frames.`, so the FTS
// join's identically named ocr_text/window_title/app aren't ambiguous) is shared
// with the backfill work-query and now lives in rewindEmbeddingSql.ts.
export function searchRewindFrames(query: string, limit = 500): RewindFrame[] {
  return timed('searchRewindFrames', () => {
    const match = buildRewindFtsMatch(query)
    if (!match) return []
    return get()
      .prepare(
        `SELECT ${REWIND_COLUMNS_QUALIFIED} FROM rewind_frames
           JOIN rewind_frames_fts ON rewind_frames.id = rewind_frames_fts.rowid
          WHERE rewind_frames_fts MATCH ?
          ORDER BY bm25(rewind_frames_fts) ASC, rewind_frames.ts DESC
          LIMIT ?`
      )
      .all(match, limit) as RewindFrame[]
  })
}

export function rewindDayBounds(): { min: number; max: number } | null {
  const row = get().prepare('SELECT MIN(ts) AS min, MAX(ts) AS max FROM rewind_frames').get() as {
    min: number | null
    max: number | null
  }
  return row.min == null || row.max == null ? null : { min: row.min, max: row.max }
}

/** The single most-recent captured frame (Omi's own windows are never captured),
 *  used by the chat to read "what's on screen right now". null if none yet. */
export function latestRewindFrame(): RewindFrame | null {
  const row = get()
    .prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames ORDER BY ts DESC LIMIT 1`)
    .get() as RewindFrame | undefined
  return row ?? null
}

export function unindexedRewindFrames(limit = 20): RewindFrame[] {
  return get()
    .prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE indexed = 0 ORDER BY ts LIMIT ?`)
    .all(limit) as RewindFrame[]
}

// `ocrLinesJson` (Track 4) is the JSON-serialized per-line bounding boxes for the
// on-image highlight overlay. Optional + additive: existing 2-arg callers keep
// working (lines stored as NULL). The AFTER UPDATE trigger re-syncs the FTS index.
export function setRewindFrameOcr(id: number, ocrText: string, ocrLinesJson?: string | null): void {
  get()
    .prepare('UPDATE rewind_frames SET ocr_text = ?, ocr_lines_json = ?, indexed = 1 WHERE id = ?')
    .run(ocrText, ocrLinesJson ?? null, id)
}

/** Per-line OCR bounding boxes for a frame (empty when none stored or malformed). */
export function getRewindFrameOcrLines(id: number): OcrLine[] {
  const row = get().prepare('SELECT ocr_lines_json FROM rewind_frames WHERE id = ?').get(id) as
    | { ocr_lines_json: string | null }
    | undefined
  if (!row?.ocr_lines_json) return []
  try {
    const parsed = JSON.parse(row.ocr_lines_json)
    return Array.isArray(parsed) ? (parsed as OcrLine[]) : []
  } catch {
    return []
  }
}

/** Image paths of frames captured in [fromMs, toMs) — used by the orphaned-JPEG
 *  sweep to tell a crash-orphaned file apart from one with a live DB row. */
export function rewindImagePathsBetween(fromMs: number, toMs: number): string[] {
  return (
    get()
      .prepare('SELECT image_path FROM rewind_frames WHERE ts >= ? AND ts < ?')
      .all(fromMs, toMs) as { image_path: string }[]
  ).map((r) => r.image_path)
}

export function deleteRewindFramesOlderThan(cutoffTs: number): RewindFrame[] {
  const d = get()
  const select = d.prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE ts < ?`)
  const del = d.prepare('DELETE FROM rewind_frames WHERE ts < ?')
  const pruneOlderThan = d.transaction((cutoff: number) => {
    const doomed = select.all(cutoff) as RewindFrame[]
    del.run(cutoff)
    // Embeddings are DERIVED FROM THE USER'S SCREEN CONTENT, so retention has to
    // reach them too — there is no FK/CASCADE here (foreign_keys is off), and a
    // vector that outlives its frame is exactly the data the user asked us to
    // forget. Same transaction as the frame delete: retention is all-or-nothing.
    dropOrphanedEmbeddingsOn(d)
    return doomed // caller deletes the image files
  })
  return pruneOlderThan(cutoffTs)
}

// --- Track 4: Rewind semantic search ---
// Frame -> content hash -> ONE L2-normalized Float32 vector per unique hash.
// Because the vectors are stored normalized, a dot product IS the cosine
// similarity — see rewind/embedVector.ts.

/** Delete embedding rows whose frame is gone, then any vector no frame references.
 *  Ordered: the mapping is cleared first so the vector GC sees the truth. The two
 *  statements live in rewindEmbeddingSql.ts so the privacy test runs exactly them. */
function dropOrphanedEmbeddingsOn(d: Database.Database): void {
  d.prepare(DROP_ORPHANED_EMBEDDING_MAPPINGS_SQL).run()
  d.prepare(DROP_ORPHANED_EMBEDDING_VECTORS_SQL).run()
}

/**
 * One-time sweep for embeddings left behind by a frame delete that did not clean
 * them up — i.e. anything an earlier build of this feature already accumulated,
 * plus the (rare) frames dropped outside `deleteRewindFramesOlderThan`. Runs at
 * startup; a no-op on a healthy database.
 */
export function pruneOrphanedRewindEmbeddings(): number {
  const d = get()
  // Count BOTH tables: the vectors dropped by the second DELETE are the ones that
  // actually held screen-derived content, and counting only the mapping rows made
  // the startup log understate what had been cleaned.
  const count = (): number =>
    (
      d
        .prepare(
          `SELECT (SELECT COUNT(*) FROM rewind_embeddings)
                + (SELECT COUNT(*) FROM rewind_embedding_vectors) AS n`
        )
        .get() as { n: number }
    ).n
  const before = count()
  d.transaction(() => dropOrphanedEmbeddingsOn(d))()
  return before - count()
}

/** Frames that have OCR text but no embedding yet, newest first (the frames a
 *  user is most likely to search for). `excludeIds` drops frames the caller has
 *  already given up on this launch — without it, a batch that failed would be
 *  handed back forever and the sweep could never advance past it.
 *
 *  The length floor MUST match the queue's `MIN_EMBED_TEXT_LEN`. When it didn't,
 *  every too-short frame (lock screen, video, blank desktop) was returned here,
 *  refused by the queue, never given an embedding row — and so returned again,
 *  forever, monopolising the newest-first page until the backfill stalled outright.
 *  Whitespace-only text is caught by TRIM here and by `.trim()` there. */
export function rewindFramesNeedingEmbedding(
  limit: number,
  excludeIds: number[] = []
): RewindFrame[] {
  return timed('rewindFramesNeedingEmbedding', () => {
    return get()
      .prepare(rewindFramesNeedingEmbeddingSql(excludeIds.length))
      .all(...excludeIds, limit) as RewindFrame[]
  })
}

/**
 * Point a frame at its content's vector, storing that vector only if this is the
 * first frame to carry the content. Duplicate frames therefore cost one small
 * mapping row instead of another 12KB copy, while staying just as findable.
 */
export function upsertRewindEmbedding(
  frameId: number,
  hash: string,
  vec: Float32Array,
  model: string
): void {
  const d = get()
  d.transaction(() => {
    d.prepare(
      `INSERT INTO rewind_embedding_vectors (hash, dim, model, vec, created_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(hash) DO UPDATE SET
         dim = excluded.dim, model = excluded.model, vec = excluded.vec, created_at = excluded.created_at`
    ).run(hash, vec.length, model, vectorToBuffer(vec), Date.now())
    d.prepare(
      `INSERT INTO rewind_embeddings (frame_id, hash) VALUES (?, ?)
       ON CONFLICT(frame_id) DO UPDATE SET hash = excluded.hash`
    ).run(frameId, hash)
  })()
}

/** Map a frame to the content's vector WITHOUT re-storing the vector — the
 *  cache-hit path, when an identical screen was embedded earlier. Returns false
 *  when that vector is gone (retention pruned it), so the caller re-embeds. */
export function linkRewindEmbedding(frameId: number, hash: string): boolean {
  const d = get()
  const exists = d
    .prepare('SELECT 1 AS ok FROM rewind_embedding_vectors WHERE hash = ?')
    .get(hash) as { ok: number } | undefined
  if (!exists) return false
  d.prepare(
    `INSERT INTO rewind_embeddings (frame_id, hash) VALUES (?, ?)
     ON CONFLICT(frame_id) DO UPDATE SET hash = excluded.hash`
  ).run(frameId, hash)
  return true
}

/**
 * Rank stored content against `query` and return the matching frames, strongest
 * first — WITHOUT blocking the main process.
 *
 * better-sqlite3 is synchronous, so scanning every vector in one statement would
 * hold the main thread (and thus IPC, capture ingestion and the UI) for the whole
 * scan. The scan is therefore paged and yields between pages; see
 * `scanTopKBySimilarity`. The candidate set is bounded by retention: only content
 * some live frame still references is scanned, and retention deletes the rest.
 */
export async function searchRewindEmbeddings(
  query: Float32Array,
  limit: number
): Promise<{ frameId: number; similarity: number }[]> {
  const d = get()
  // EXISTS against idx_rewind_embeddings_hash: skips vectors no live frame points
  // at, so an orphan that slipped through can't cost us a similarity computation.
  //
  // The vec guard is IN THE SQL (searchEmbeddingPageSql), not a .filter() on the
  // page. `vec` is nullable, and scanTopKBySimilarity treats a short page as
  // end-of-store — so filtering after the fact meant one partially-written row
  // anywhere in the table silently truncated the scan there, and every vector past
  // it went unranked. Filtering in the query keeps LIMIT and "rows returned"
  // describing the same set.
  const page = d.prepare(searchEmbeddingPageSql())

  const scored = await scanTopKBySimilarity(
    (offset, size) =>
      (page.all(size, offset) as { hash: string; vec: Uint8Array }[]).map((r) => ({
        hash: r.hash,
        vec: bufferToVector(r.vec)
      })),
    query,
    limit,
    () => new Promise<void>((resolve) => setImmediate(resolve))
  )
  if (scored.length === 0) return []

  // Expand each winning hash back to the frames that carry that content. One
  // hash can name many frames (that is the whole point of the dedup), so the
  // result is capped at `limit` frames, strongest first then newest first.
  const placeholders = scored.map(() => '?').join(',')
  const rows = d
    .prepare(
      `SELECT e.frame_id AS frameId, e.hash AS hash, f.ts AS ts FROM rewind_embeddings e
         JOIN rewind_frames f ON f.id = e.frame_id
        WHERE e.hash IN (${placeholders})`
    )
    .all(...scored.map((s) => s.hash)) as { frameId: number; hash: string; ts: number }[]

  const similarityByHash = new Map(scored.map((s) => [s.hash, s.similarity]))
  return rows
    .map((r) => ({ frameId: r.frameId, similarity: similarityByHash.get(r.hash) ?? 0, ts: r.ts }))
    .sort((a, b) => b.similarity - a.similarity || b.ts - a.ts)
    .slice(0, limit)
    .map(({ frameId, similarity }) => ({ frameId, similarity }))
}

/** Hydrate frames by id, in the given order (ids with no row are skipped). */
export function rewindFramesByIds(ids: number[]): RewindFrame[] {
  if (ids.length === 0) return []
  const placeholders = ids.map(() => '?').join(',')
  const frames = get()
    .prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE id IN (${placeholders})`)
    .all(...ids) as RewindFrame[]
  const byId = new Map(frames.map((f) => [f.id, f]))
  return ids.map((id) => byId.get(id)).filter((f): f is RewindFrame => f !== undefined)
}

// --- Proactive Insights ---

const INSIGHT_COLUMNS =
  'id, ts, headline, advice, reasoning, category AS category, source_app AS sourceApp, confidence, dismissed'

export function insertInsight(p: InsightPayload): number {
  const info = get()
    .prepare(
      `INSERT INTO insights (ts, headline, advice, reasoning, category, source_app, confidence)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .run(Date.now(), p.headline, p.advice, p.reasoning, p.category, p.sourceApp, p.confidence)
  return info.lastInsertRowid as number
}

export function recentInsights(limit = 30): InsightRecord[] {
  return get()
    .prepare(`SELECT ${INSIGHT_COLUMNS} FROM insights ORDER BY ts DESC LIMIT ?`)
    .all(limit) as InsightRecord[]
}

// --- Track 2: Voice & PTT depth (voice turn outbox) ---
// Thin wrappers over the driver-agnostic CRUD in voiceTurnOutbox.ts (extracted so
// the SQL is unit-testable under plain-node vitest; see that file + its test).
// get() returns a better-sqlite3 Database whose prepared statements satisfy the
// VoiceTurnOutboxDb shape structurally — cast to bridge the driver duck-typing,
// same idiom the migration/wipe tests use for node:sqlite.
function voiceTurnDb(): VoiceTurnOutboxDb {
  return get() as unknown as VoiceTurnOutboxDb
}

export function insertVoiceTurn(entry: VoiceTurnOutboxInput): void {
  insertVoiceTurnOn(voiceTurnDb(), entry, Date.now())
}

export function listPendingVoiceTurns(limit?: number): VoiceTurnOutboxEntry[] {
  return listPendingVoiceTurnsOn(voiceTurnDb(), limit)
}

export function markVoiceTurnAcked(idempotencyKey: string): void {
  markVoiceTurnAckedOn(voiceTurnDb(), idempotencyKey)
}

export function recordVoiceTurnFailure(idempotencyKey: string, error: string): void {
  recordVoiceTurnFailureOn(voiceTurnDb(), idempotencyKey, error, Date.now())
}

/* ---- Track 3 (proactive intelligence & memory) ---- */

// --- AI User Profile history ---
// Local history of the daily-synthesized AI User Profile. Backend is the source
// of truth; these rows feed the stage-2 consolidation (reads up to 5 past ones).

const AI_USER_PROFILE_COLUMNS =
  'id, profile_text AS profileText, data_sources_used AS dataSourcesUsed, generated_at AS generatedAt, backend_synced AS backendSynced'

type AiUserProfileRow = {
  id: number
  profileText: string
  dataSourcesUsed: string | null
  generatedAt: number
  backendSynced: number
}

function mapAiUserProfile(row: AiUserProfileRow): AiUserProfileRecord {
  return {
    id: row.id,
    profileText: row.profileText,
    dataSourcesUsed: parseJsonArray(row.dataSourcesUsed) ?? [],
    generatedAt: row.generatedAt,
    backendSynced: row.backendSynced !== 0
  }
}

export function insertAiUserProfile(rec: AiUserProfileInput): number {
  const info = get()
    .prepare(
      `INSERT INTO ai_user_profiles (profile_text, data_sources_used, generated_at, backend_synced)
       VALUES (?, ?, ?, ?)`
    )
    .run(
      rec.profileText,
      rec.dataSourcesUsed && rec.dataSourcesUsed.length
        ? JSON.stringify(rec.dataSourcesUsed)
        : null,
      rec.generatedAt,
      rec.backendSynced ? 1 : 0
    )
  return info.lastInsertRowid as number
}

// Newest first, for the consolidation read (default 5).
export function listAiUserProfiles(limit = 5): AiUserProfileRecord[] {
  const rows = get()
    .prepare(
      `SELECT ${AI_USER_PROFILE_COLUMNS} FROM ai_user_profiles ORDER BY generated_at DESC, id DESC LIMIT ?`
    )
    .all(limit) as AiUserProfileRow[]
  return rows.map(mapAiUserProfile)
}

export function latestAiUserProfile(): AiUserProfileRecord | null {
  const row = get()
    .prepare(
      `SELECT ${AI_USER_PROFILE_COLUMNS} FROM ai_user_profiles ORDER BY generated_at DESC, id DESC LIMIT 1`
    )
    .get() as AiUserProfileRow | undefined
  return row ? mapAiUserProfile(row) : null
}

export function updateAiUserProfileText(id: number, text: string): void {
  get().prepare('UPDATE ai_user_profiles SET profile_text = ? WHERE id = ?').run(text, id)
}

export function markAiUserProfileSynced(id: number): void {
  get().prepare('UPDATE ai_user_profiles SET backend_synced = 1 WHERE id = ?').run(id)
}

export function deleteAiUserProfile(id: number): void {
  get().prepare('DELETE FROM ai_user_profiles WHERE id = ?').run(id)
}

export function deleteAllAiUserProfiles(): void {
  get().prepare('DELETE FROM ai_user_profiles').run()
}

// --- Focus sessions ---
// One row per Focus-assistant analysis. No backend focus API on Mac; sessions
// live locally (and are dual-written as memories elsewhere).

const FOCUS_SESSION_COLUMNS =
  'id, screenshot_id AS screenshotId, status, app_or_site AS appOrSite, description, message, ' +
  'duration_seconds AS durationSeconds, backend_id AS backendId, backend_synced AS backendSynced, ' +
  'created_at AS createdAt, window_title AS windowTitle'

type FocusSessionRow = {
  id: number
  screenshotId: string | null
  status: string
  appOrSite: string | null
  description: string | null
  message: string | null
  durationSeconds: number
  backendId: string | null
  backendSynced: number
  createdAt: number
  windowTitle: string | null
}

function mapFocusSession(row: FocusSessionRow): FocusSessionRecord {
  return {
    id: row.id,
    screenshotId: row.screenshotId,
    status: row.status === 'distracted' ? 'distracted' : 'focused',
    appOrSite: row.appOrSite,
    description: row.description,
    message: row.message,
    durationSeconds: row.durationSeconds,
    backendId: row.backendId,
    backendSynced: row.backendSynced !== 0,
    createdAt: row.createdAt,
    windowTitle: row.windowTitle
  }
}

export function insertFocusSession(rec: FocusSessionInput): number {
  const info = get()
    .prepare(
      `INSERT INTO focus_sessions
         (screenshot_id, status, app_or_site, description, message, duration_seconds, backend_id, backend_synced, created_at, window_title)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      rec.screenshotId ?? null,
      rec.status,
      rec.appOrSite ?? null,
      rec.description ?? null,
      rec.message ?? null,
      rec.durationSeconds ?? 0,
      rec.backendId ?? null,
      rec.backendSynced ? 1 : 0,
      rec.createdAt,
      rec.windowTitle ?? null
    )
  return info.lastInsertRowid as number
}

// Newest first; optionally filtered to created_at >= sinceEpochMs and capped.
export function listFocusSessions(sinceEpochMs?: number, limit?: number): FocusSessionRecord[] {
  const params: unknown[] = []
  let sql = `SELECT ${FOCUS_SESSION_COLUMNS} FROM focus_sessions`
  if (sinceEpochMs !== undefined) {
    sql += ' WHERE created_at >= ?'
    params.push(sinceEpochMs)
  }
  sql += ' ORDER BY created_at DESC, id DESC'
  if (limit !== undefined) {
    sql += ' LIMIT ?'
    params.push(limit)
  }
  const rows = get()
    .prepare(sql)
    .all(...params) as FocusSessionRow[]
  return rows.map(mapFocusSession)
}

export function markFocusSessionSynced(id: number, backendId: string): void {
  get()
    .prepare('UPDATE focus_sessions SET backend_synced = 1, backend_id = ? WHERE id = ?')
    .run(backendId, id)
}

// --- Task embeddings (semantic ranking) ---
// 3072-dim Gemini vectors keyed by (source, item_id) so ids from different
// source tables can't collide. Vectors stored as a Float32 little-endian BLOB
// (see taskEmbeddingVector.ts), exposed as Float32Array.

const TASK_EMBEDDING_COLUMNS =
  'source, item_id AS itemId, vector, text, model, updated_at AS updatedAt'

type TaskEmbeddingRow = {
  source: string
  itemId: string
  vector: Buffer | Uint8Array
  text: string
  model: string
  updatedAt: number
}

function mapTaskEmbedding(row: TaskEmbeddingRow): TaskEmbeddingRecord {
  return {
    source: row.source === 'staged_task' ? 'staged_task' : 'action_item',
    itemId: row.itemId,
    vector: bufferToVector(row.vector),
    text: row.text,
    model: row.model,
    updatedAt: row.updatedAt
  }
}

export function upsertTaskEmbedding(rec: TaskEmbeddingRecord): void {
  get()
    .prepare(
      `INSERT INTO task_embeddings (source, item_id, vector, text, model, updated_at)
       VALUES (@source, @itemId, @vector, @text, @model, @updatedAt)
       ON CONFLICT(source, item_id) DO UPDATE SET
         vector = excluded.vector, text = excluded.text, model = excluded.model, updated_at = excluded.updated_at`
    )
    .run({
      source: rec.source,
      itemId: rec.itemId,
      vector: vectorToBuffer(rec.vector),
      text: rec.text,
      model: rec.model,
      updatedAt: rec.updatedAt
    })
}

export function getTaskEmbedding(source: string, itemId: string): TaskEmbeddingRecord | null {
  const row = get()
    .prepare(
      `SELECT ${TASK_EMBEDDING_COLUMNS} FROM task_embeddings WHERE source = ? AND item_id = ?`
    )
    .get(source, itemId) as TaskEmbeddingRow | undefined
  return row ? mapTaskEmbedding(row) : null
}

export function allTaskEmbeddings(): TaskEmbeddingRecord[] {
  const rows = get()
    .prepare(`SELECT ${TASK_EMBEDDING_COLUMNS} FROM task_embeddings`)
    .all() as TaskEmbeddingRow[]
  return rows.map(mapTaskEmbedding)
}

export function deleteTaskEmbedding(source: string, itemId: string): void {
  get().prepare('DELETE FROM task_embeddings WHERE source = ? AND item_id = ?').run(source, itemId)
}
