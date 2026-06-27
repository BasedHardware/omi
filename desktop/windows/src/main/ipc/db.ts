import Database from 'better-sqlite3'
import { app } from 'electron'
import { basename, join } from 'path'
import { categorize } from '../usage/category'
import { isNewLocalDay } from '../usage/usageDay'
import type {
  AppUsageRecord,
  ChatMessage,
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
  RewindFrame,
  UsageCategory
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

// Add a column only if it doesn't already exist, so existing databases (which
// predate the `kind`/`messages` columns) migrate forward without data loss.
function ensureColumn(d: Database.Database, table: string, col: string, decl: string): void {
  const cols = d.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]
  if (!cols.some((c) => c.name === col)) {
    d.exec(`ALTER TABLE ${table} ADD COLUMN ${col} ${decl}`)
  }
}

// Drop a table whose on-disk schema predates the current one (detected by a
// missing expected column), so the CREATE TABLE IF NOT EXISTS below can recreate
// it fresh. Used for the local_kg_* tables: an abandoned experiment left an
// incompatible schema (node_id/edge_id PKs, no summary/source columns) that
// silently broke every INSERT. These tables are a derived cache with no user
// data worth migrating, so recreating them is safe.
function dropIfMissingColumn(d: Database.Database, table: string, col: string): void {
  const exists = d
    .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?")
    .get(table)
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
  // For the throwaway bench DB only, relax durability so seeding ~7k rows isn't
  // dominated by a per-insert fsync (otherwise it swamps the startup measurement).
  if (process.env.OMI_DB_PATH) {
    db.pragma('journal_mode = WAL')
    db.pragma('synchronous = NORMAL')
  }
  // Migrate away the incompatible local_kg_* schema from the parked KG experiment.
  dropIfMissingColumn(db, 'local_kg_nodes', 'summary')
  dropIfMissingColumn(db, 'local_kg_edges', 'id')
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
    title: row.title ?? null
  }
}

const LOCAL_CONVERSATION_COLUMNS =
  'id, started_at AS startedAt, ended_at AS endedAt, transcript, created_at AS createdAt, kind, messages, title'

export function insertLocalConversation(c: LocalConversation): void {
  get()
    .prepare(
      'INSERT OR REPLACE INTO local_conversation (id, started_at, ended_at, transcript, created_at, kind, messages, title) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    )
    .run(
      c.id,
      c.startedAt,
      c.endedAt,
      c.transcript,
      c.createdAt,
      c.kind ?? 'recording',
      c.messages ? JSON.stringify(c.messages) : null,
      c.title ?? null
    )
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
      .prepare(`SELECT ${LOCAL_CONVERSATION_COLUMNS} FROM local_conversation ORDER BY created_at DESC`)
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

// Full-replace the local graph: clear both tables and batch-insert in a single
// transaction (matches replaceIndexedFiles cadence). 500-row batches keep
// large graphs off a single mega-statement.
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
  const columns = rows.length
    ? Object.keys(rows[0])
    : (stmt.columns().map((c) => c.name) ?? [])
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
  if (nodes.length === 0) return { nodes: [], edges: [] }
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
export function searchIndexedFiles(
  q: string,
  fileType?: string,
  limit = 20
): IndexedFileRecord[] {
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
  return timed('listRewindFrames', () =>
    get()
      .prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE ts BETWEEN ? AND ? ORDER BY ts`)
      .all(from, to) as RewindFrame[]
  )
}

export function searchRewindFrames(query: string, limit = 500): RewindFrame[] {
  return timed('searchRewindFrames', () => {
    const like = `%${query}%`
    return get()
      .prepare(
        `SELECT ${REWIND_COLUMNS} FROM rewind_frames
       WHERE ocr_text LIKE ? OR window_title LIKE ? OR app LIKE ?
       ORDER BY ts DESC LIMIT ?`
      )
      .all(like, like, like, limit) as RewindFrame[]
  })
}

export function rewindDayBounds(): { min: number; max: number } | null {
  const row = get()
    .prepare('SELECT MIN(ts) AS min, MAX(ts) AS max FROM rewind_frames')
    .get() as { min: number | null; max: number | null }
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

export function setRewindFrameOcr(id: number, ocrText: string): void {
  get().prepare('UPDATE rewind_frames SET ocr_text = ?, indexed = 1 WHERE id = ?').run(ocrText, id)
}

export function deleteRewindFramesOlderThan(cutoffTs: number): RewindFrame[] {
  const d = get()
  const select = d.prepare(`SELECT ${REWIND_COLUMNS} FROM rewind_frames WHERE ts < ?`)
  const del = d.prepare('DELETE FROM rewind_frames WHERE ts < ?')
  const pruneOlderThan = d.transaction((cutoff: number) => {
    const doomed = select.all(cutoff) as RewindFrame[]
    del.run(cutoff)
    return doomed // caller deletes the image files
  })
  return pruneOlderThan(cutoffTs)
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
