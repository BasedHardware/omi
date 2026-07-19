// The Tier-A product-tool executors — the thin tasks + screen-search bundle that
// the pi-mono relay (and, later, the in-process voice hub dispatcher) dispatches
// to. Windows analogue of the macOS ChatToolExecutor cases for these tools; the
// return strings are matched to Mac where Mac is local (complete_task/delete_task)
// and kept in the same prose register otherwise.
//
// WHY A FACTORY-PER-TOOL. Same shape as captureScreenExecutor.ts: each executor is
// built by a `createXExecutor(deps?)` factory whose impure edges (the SQLite store,
// the task sync engine, the embedding service) are INJECTED. Production binds them
// to the real modules via CALL-TIME dynamic `import()`, so this module — which
// toolRelayBridge.ts imports at load to build defaultProductToolExecutors — never
// drags better-sqlite3 / Electron into the vitest import graph (the same discipline
// as assistants/tasks/toolBackends.ts). Tests inject fakes and never touch native.
//
// INV-AGENT. Executors run under the relay's host-derived ctx (sessionId/adapterId
// from the token binding, plus an AbortSignal that fires on client disconnect).
// They add no authority surface: task writes go through the same taskSyncEngine the
// Tasks UI uses (local-first + background REST under the relayed session), and every
// read is local. Executors aim to RETURN `"Error: …"` strings rather than throw, so
// the relay's tool_result contract holds; the relay bridge also catches a stray
// throw as a final backstop. The one network-touching read (semantic_search's query
// embedding) honors ctx.signal.

import type { ProductToolContext, ProductToolExecutor } from './toolRelayBridge'
import type {
  ActionItemRecord,
  FocusSessionRecord,
  InsightRecord,
  LocalConversation,
  OnboardingGraphEdge,
  OnboardingGraphNode,
  RewindFrame
} from '../../shared/types'
import type { TaskSearchResult } from '../assistants/tasks/toolBackends'
import { executeReadOnlySql } from '../assistants/insight/sql'
import type { BackendJsonResult, BackendToolRequest } from './backendTools'

// --- shared arg helpers ------------------------------------------------------

/** Read a string arg, trimmed; '' when missing/blank. */
function stringArg(input: Record<string, unknown>, key: string): string {
  const v = input[key]
  return typeof v === 'string' ? v.trim() : ''
}

/** Mac `intArgument` — accepts Int, Double, or numeric String (ChatToolExecutor:1088). */
function intArg(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.trunc(value)
  if (typeof value === 'string') {
    const n = Number(value.trim())
    return Number.isFinite(n) ? Math.trunc(n) : null
  }
  return null
}

/** Mac `validateISODate` (ChatToolExecutor:1941): parse an ISO-8601 date with a
 *  timezone offset. Returns `{ ms }` on success (ms `undefined` when the field is
 *  absent — optional) or `{ error }` with Mac's exact message. */
function parseIsoDate(value: unknown, paramName: string): { ms?: number | null; error?: string } {
  if (value === undefined || value === null) return { ms: undefined }
  if (typeof value !== 'string' || value.trim().length === 0) return { ms: undefined }
  const t = Date.parse(value)
  if (Number.isNaN(t)) {
    return {
      error: `Error: ${paramName} must be ISO format with timezone offset (e.g. 2024-01-19T15:00:00-08:00 or 2024-01-19T15:00:00+07:00). Got: ${value}`
    }
  }
  return { ms: t }
}

/** True when the caller (relay socket) already went away. */
function aborted(ctx: ProductToolContext): boolean {
  return ctx.signal.aborted
}

function formatDate(ts: number): string {
  try {
    return new Date(ts).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return new Date(ts).toISOString()
  }
}

// --- semantic_search / search_screen_history ---------------------------------

export interface SemanticSearchDeps {
  /** Embed the query text (RETRIEVAL_QUERY); null when signed-out / empty / backend down. */
  embedQuery: (text: string) => Promise<Float32Array | null>
  /** Vector search over rewind-frame embeddings. */
  search: (query: Float32Array, limit: number) => Promise<{ frameId: number; similarity: number }[]>
  /** Resolve frame rows by id. */
  framesByIds: (ids: number[]) => Promise<RewindFrame[]>
}

const DAY_MS = 24 * 60 * 60 * 1000
/** Mac keeps only hits strictly above this cosine similarity (ChatToolExecutor:1025). */
const SEMANTIC_SIMILARITY_THRESHOLD = 0.3

function bindSemanticSearchDeps(deps?: Partial<SemanticSearchDeps>): SemanticSearchDeps {
  return {
    embedQuery:
      deps?.embedQuery ??
      (async (text) => (await import('../rewind/embeddingService')).embedRewindQuery(text)),
    search:
      deps?.search ??
      (async (q, limit) => (await import('../ipc/db')).searchRewindEmbeddings(q, limit)),
    framesByIds:
      deps?.framesByIds ?? (async (ids) => (await import('../ipc/db')).rewindFramesByIds(ids))
  }
}

/**
 * `semantic_search` / `search_screen_history`. Embeds the query, ranks rewind-frame
 * embeddings, keeps hits above 0.3, applies the `days` + `app_filter` narrowing, and
 * formats Mac's prose block (ChatToolExecutor:1036-1055): a header line then one
 * `N. [date] app - title (screenshot_id, similarity)` row per hit with a 300-char
 * OCR `Content:` preview.
 */
export function createSemanticSearchExecutor(
  deps?: Partial<SemanticSearchDeps>
): ProductToolExecutor {
  const d = bindSemanticSearchDeps(deps)
  return async (input, ctx) => {
    const query = stringArg(input, 'query')
    if (!query) return 'Error: query is required'
    const days = Math.max(1, intArg(input.days) ?? 7)
    const appFilter = typeof input.app_filter === 'string' ? input.app_filter.trim() : null
    const limit = Math.min(Math.max(1, intArg(input.limit) ?? 15), 50)

    const vec = await d.embedQuery(query)
    if (!vec || aborted(ctx)) return emptySemanticSearchMessage(query, days, appFilter)

    const scored = await d.search(vec, Math.max(limit * 2, 20))
    if (aborted(ctx)) return emptySemanticSearchMessage(query, days, appFilter)
    const frames = await d.framesByIds(scored.map((s) => s.frameId))
    const byId = new Map(frames.map((f) => [f.id, f] as const))
    const cutoff = Date.now() - days * DAY_MS
    const appNeedle = appFilter?.toLowerCase() ?? null

    const hits: { frame: RewindFrame; similarity: number }[] = []
    for (const s of scored) {
      if (!(s.similarity > SEMANTIC_SIMILARITY_THRESHOLD)) continue
      const frame = byId.get(s.frameId)
      if (!frame) continue
      if (frame.ts < cutoff) continue
      if (appNeedle && !(frame.app ?? '').toLowerCase().includes(appNeedle)) continue
      hits.push({ frame, similarity: s.similarity })
      if (hits.length >= limit) break
    }
    if (hits.length === 0) return emptySemanticSearchMessage(query, days, appFilter)

    const lines: string[] = [`Found ${hits.length} screenshot(s) matching "${query}":`]
    hits.forEach((hit, i) => {
      const f = hit.frame
      const titlePart = f.windowTitle ? ` - ${f.windowTitle}` : ''
      lines.push(
        `\n${i + 1}. [${formatDate(f.ts)}] ${f.app || 'Unknown'}${titlePart} (screenshot_id: ${f.id}, similarity: ${hit.similarity.toFixed(2)})`
      )
      const ocr = (f.ocrText ?? '').slice(0, 300).replace(/\n/g, ' ').trim()
      if (ocr) lines.push(`   Content: ${ocr}`)
    })
    return lines.join('\n')
  }
}

function emptySemanticSearchMessage(query: string, days: number, appFilter: string | null): string {
  const appText = appFilter ? ` with app filter "${appFilter}"` : ''
  return `No matching screen-history results for "${query}" in the last ${days} day(s)${appText}. Try a broader query, a wider days window, or use execute_sql for exact app/window/OCR filters.`
}

// --- search_tasks ------------------------------------------------------------

export interface SearchTasksDeps {
  /** Vector task search (action_items + staged_tasks), Mac-ported + tested. */
  vectorSearch: (query: string) => Promise<TaskSearchResult[]>
}

/** Mac caps the rendered list at 10 (ChatToolExecutor:1150). */
const SEARCH_TASKS_CAP = 10

/**
 * `search_tasks`. Vector similarity search over tasks; drops completed unless
 * `include_completed`, caps at 10, and renders Mac's prose rows
 * (ChatToolExecutor:1131-1162): `N. [x]/[ ] description (similarity, id)`.
 * (Windows' TaskSearchResult carries `status`/`similarity` but not priority or the
 * source table, so Mac's optional ` [priority]` / `source:` segments are omitted.)
 */
export function createSearchTasksExecutor(deps?: Partial<SearchTasksDeps>): ProductToolExecutor {
  const vectorSearch =
    deps?.vectorSearch ??
    (async (q: string) => (await import('../assistants/tasks/toolBackends')).executeVectorSearch(q))
  return async (input) => {
    const query = stringArg(input, 'query')
    if (!query) return 'Error: query is required'
    const includeCompleted = input.include_completed === true

    const results = await vectorSearch(query)
    const kept = results
      .filter((r) => r.status !== 'deleted')
      .filter((r) => includeCompleted || r.status !== 'completed')
      .slice(0, SEARCH_TASKS_CAP)
    if (kept.length === 0) {
      return `No tasks found matching "${query}". No tasks have embeddings yet, or none are similar enough.`
    }
    const lines: string[] = [`Found ${kept.length} task(s) matching "${query}":`]
    kept.forEach((r, i) => {
      const check = r.status === 'completed' ? '[x]' : '[ ]'
      const sim = r.similarity != null ? r.similarity.toFixed(2) : 'n/a'
      lines.push(`${i + 1}. ${check} ${r.description} (similarity: ${sim}, id: ${r.id})`)
    })
    return lines.join('\n')
  }
}

// --- get_action_items --------------------------------------------------------

export interface TaskReadDeps {
  /** Local action-item list (the synced Windows mirror). `completed` omitted = both. */
  getItems: (opts: {
    completed?: boolean
    limit?: number
    offset?: number
  }) => Promise<ActionItemRecord[]>
}

function bindTaskReadDeps(deps?: Partial<TaskReadDeps>): TaskReadDeps {
  return {
    getItems:
      deps?.getItems ?? (async (opts) => (await import('../ipc/db')).getLocalActionItems(opts))
  }
}

function formatTaskLine(index: number, r: ActionItemRecord): string {
  const check = r.completed ? '[x]' : '[ ]'
  const due = r.dueAt != null ? formatDate(r.dueAt) : 'none'
  const id = r.backendId ?? `local:${r.id}`
  return `${index}. ${check} ${r.description} (id: ${id}, due: ${due})`
}

function dateRange(
  fromRaw: unknown,
  toRaw: unknown,
  fromName: string,
  toName: string
): { from?: number | null; to?: number | null; error?: string } {
  const from = parseIsoDate(fromRaw, fromName)
  if (from.error) return { error: from.error }
  const to = parseIsoDate(toRaw, toName)
  if (to.error) return { error: to.error }
  return { from: from.ms ?? null, to: to.ms ?? null }
}

/**
 * `get_action_items`. Reads the local synced action-item mirror with optional
 * `completed` + created/due date-range filters. Windows is local-first (the mirror
 * is kept in sync by taskSyncEngine), so this is a local read, not the backend call
 * Mac makes. Date filters narrow in-memory over the paged read.
 */
export function createGetActionItemsExecutor(deps?: Partial<TaskReadDeps>): ProductToolExecutor {
  const d = bindTaskReadDeps(deps)
  return async (input) => {
    const completed = typeof input.completed === 'boolean' ? input.completed : undefined
    const limit = Math.min(Math.max(1, intArg(input.limit) ?? 50), 500)
    const offset = Math.max(0, intArg(input.offset) ?? 0)

    const created = dateRange(input.start_date, input.end_date, 'start_date', 'end_date')
    if (created.error) return created.error
    const due = dateRange(
      input.due_start_date,
      input.due_end_date,
      'due_start_date',
      'due_end_date'
    )
    if (due.error) return due.error

    let items = await d.getItems({ completed, limit, offset })
    if (created.from != null) items = items.filter((r) => r.createdAt >= created.from!)
    if (created.to != null) items = items.filter((r) => r.createdAt <= created.to!)
    if (due.from != null) items = items.filter((r) => r.dueAt != null && r.dueAt >= due.from!)
    if (due.to != null) items = items.filter((r) => r.dueAt != null && r.dueAt <= due.to!)

    if (items.length === 0) return 'No matching tasks found.'
    const lines: string[] = [`Found ${items.length} task(s):`]
    items.forEach((r, i) => lines.push(formatTaskLine(i + 1, r)))
    return lines.join('\n')
  }
}

// --- create_action_item ------------------------------------------------------

export interface TaskCreateDeps {
  createTask: (fields: {
    description: string
    dueAt?: number | null
    conversationId?: string | null
    source?: string | null
  }) => Promise<ActionItemRecord>
}

/**
 * `create_action_item`. Creates a task through taskSyncEngine (local-first insert +
 * background REST under the relayed session), matching Mac's create surface via the
 * Windows sync engine the Tasks UI already uses.
 */
export function createCreateActionItemExecutor(
  deps?: Partial<TaskCreateDeps>
): ProductToolExecutor {
  const createTask =
    deps?.createTask ??
    (async (fields) => (await import('../tasks/taskSyncEngine')).createTask(fields))
  return async (input) => {
    const description = stringArg(input, 'description')
    if (!description) return 'Error: description is required'
    const due = parseIsoDate(input.due_at, 'due_at')
    if (due.error) return due.error
    const conversationId = typeof input.conversation_id === 'string' ? input.conversation_id : null
    await createTask({ description, dueAt: due.ms ?? null, conversationId, source: 'omi' })
    return `OK: task "${description}" created`
  }
}

// --- update / complete / delete (need a by-backendId lookup) -----------------

export interface TaskMutateDeps {
  /** Resolve a task by its backendId (the id the model was given). */
  findByBackendId: (backendId: string) => Promise<ActionItemRecord | null>
  toggleTask: (backendId: string, completed: boolean) => Promise<void>
  updateTask: (
    backendId: string,
    fields: { description?: string; dueAt?: number | null; clearDueAt?: boolean }
  ) => Promise<void>
  deleteTask: (backendId: string) => Promise<void>
}

/** Real by-backendId lookup: Windows exposes no direct action-item-by-backendId
 *  getter, so scan a wide local page (same pragma as toolBackends.ts's resolver). */
async function realFindByBackendId(backendId: string): Promise<ActionItemRecord | null> {
  const { getLocalActionItems } = await import('../ipc/db')
  return getLocalActionItems({ limit: 5000 }).find((r) => r.backendId === backendId) ?? null
}

function bindTaskMutateDeps(deps?: Partial<TaskMutateDeps>): TaskMutateDeps {
  return {
    findByBackendId: deps?.findByBackendId ?? realFindByBackendId,
    toggleTask:
      deps?.toggleTask ??
      (async (id, c) => (await import('../tasks/taskSyncEngine')).toggleTask(id, c)),
    updateTask:
      deps?.updateTask ??
      (async (id, f) => (await import('../tasks/taskSyncEngine')).updateTask(id, f)),
    deleteTask:
      deps?.deleteTask ?? (async (id) => (await import('../tasks/taskSyncEngine')).deleteTask(id))
  }
}

/**
 * `update_action_item`. Finds the task by `action_item_id` (backendId), applies
 * description/due changes via updateTask and a completion change via toggleTask (the
 * local completion path — updateTask's field set has no completed column).
 */
export function createUpdateActionItemExecutor(
  deps?: Partial<TaskMutateDeps>
): ProductToolExecutor {
  const d = bindTaskMutateDeps(deps)
  return async (input) => {
    const id = stringArg(input, 'action_item_id')
    if (!id) return 'Error: action_item_id is required'
    const due = parseIsoDate(input.due_at, 'due_at')
    if (due.error) return due.error

    const task = await d.findByBackendId(id)
    if (!task) return `Error: task not found with id '${id}'`

    // A provided description is trimmed and must be non-empty — never let an update
    // blank out a task's description (matches create_action_item's stringArg gate).
    // An absent description leaves it unchanged.
    let description: string | undefined
    if (typeof input.description === 'string') {
      const trimmed = input.description.trim()
      if (trimmed.length === 0) return 'Error: description cannot be empty'
      description = trimmed
    }
    const fields: { description?: string; dueAt?: number | null; clearDueAt?: boolean } = {}
    if (description !== undefined) fields.description = description
    if (due.ms !== undefined) fields.dueAt = due.ms
    if (Object.keys(fields).length > 0) await d.updateTask(id, fields)
    if (typeof input.completed === 'boolean') await d.toggleTask(id, input.completed)

    return `OK: task '${task.description}' updated`
  }
}

/**
 * `complete_task`. Mac-exact strings (ChatToolExecutor:1183-1198): not-found,
 * already-completed, and success. Toggles completion on via taskSyncEngine.
 */
export function createCompleteTaskExecutor(deps?: Partial<TaskMutateDeps>): ProductToolExecutor {
  const d = bindTaskMutateDeps(deps)
  return async (input) => {
    const taskId = stringArg(input, 'task_id')
    if (!taskId) return 'Error: task_id is required'
    const task = await d.findByBackendId(taskId)
    if (!task) return `Error: task not found with id '${taskId}'`
    if (task.completed) return `OK: task '${task.description}' is already completed`
    await d.toggleTask(taskId, true)
    return `OK: task '${task.description}' marked as completed`
  }
}

/**
 * `delete_task`. Mac-exact strings (ChatToolExecutor:1214-1224). Windows hard-deletes
 * locally, so Mac's "already deleted" branch is unreachable (the row is gone), but
 * the not-found branch covers it identically.
 */
export function createDeleteTaskExecutor(deps?: Partial<TaskMutateDeps>): ProductToolExecutor {
  const d = bindTaskMutateDeps(deps)
  return async (input) => {
    const taskId = stringArg(input, 'task_id')
    if (!taskId) return 'Error: task_id is required'
    const task = await d.findByBackendId(taskId)
    if (!task) return `Error: task not found with id '${taskId}'`
    await d.deleteTask(taskId)
    return `OK: task '${task.description}' deleted`
  }
}

// =============================================================================
// Tier-B executors (PR-4..7): execute_sql, memories/conversations backend tools,
// get_work_context / get_daily_recap composition, save_knowledge_graph.
// =============================================================================

/** Clamp an int arg into [min, max] with a default. */
function clampInt(value: unknown, def: number, min: number, max: number): number {
  const n = intArg(value)
  return Math.min(Math.max(n ?? def, min), max)
}

// --- execute_sql (SECURITY-SENSITIVE) ----------------------------------------

/**
 * The CLOSED allowlist of omi.db tables the agent's `execute_sql` may read. Sized
 * to the tool's stated purpose (app usage / screen time, tasks, conversations,
 * memories, aggregations, knowledge graph) and NOTHING else. Deliberately excluded:
 * key/value meta tables (`app_meta`, `file_index_meta`), the file index
 * (`indexed_files`), raw caption fragments (`caption_event`), embedding vectors
 * (`rewind_embeddings*`), and the voice outbox — none serve the tool's purpose and
 * some could leak configuration. omi.db holds NO credential/token table (backend
 * tokens live in the renderer, never on disk here), so the allowlist is safe by
 * construction; the closed allowlist keeps it that way if a secret-bearing table is
 * ever added. Read-only is enforced by executeReadOnlySql independently of this set.
 */
export const AGENT_SQL_TABLE_ALLOWLIST: ReadonlySet<string> = new Set([
  // screen history / app usage / screen time
  'rewind_frames',
  'rewind_frames_fts',
  'app_usage',
  // tasks
  'action_items',
  'staged_tasks',
  // conversations (local mirror) + metadata
  'local_conversation',
  'conversation_folders',
  'conversation_speaker_names',
  // proactive observations / focus / memories / profile
  'insights',
  'focus_sessions',
  'memories',
  'ai_user_profiles',
  // knowledge graph
  'onboarding_kg_nodes',
  'onboarding_kg_edges',
  'local_kg_nodes',
  'local_kg_edges'
])

export interface ExecuteSqlDeps {
  /** Read-only SELECT runner over omi.db (db.ts:runReadonlySelect). */
  runQuery: (sql: string) => { columns: string[]; rows: unknown[][] }
}

/**
 * `execute_sql`. Read-only in agent adapters (v1): the shared Insight safety stack
 * (single-statement, SELECT/WITH-only, LIMIT 200 auto-append, 200-row / 500-char
 * caps — executeReadOnlySql) over AGENT_SQL_TABLE_ALLOWLIST. Every write / DDL /
 * PRAGMA / ATTACH is rejected before the query reaches the DB, and the runner
 * (`runReadonlySelect`) re-checks `stmt.reader` as a second wall. Errors are
 * returned as `Error: …` strings so the tool loop continues.
 */
export function createExecuteSqlExecutor(deps?: Partial<ExecuteSqlDeps>): ProductToolExecutor {
  return async (input) => {
    const runQuery = deps?.runQuery ?? (await import('../ipc/db')).runReadonlySelect
    return executeReadOnlySql(input.query, runQuery, AGENT_SQL_TABLE_ALLOWLIST)
  }
}

// --- memories + conversations (backend /v1/tools/*) --------------------------

export type BackendToolCaller = (req: BackendToolRequest) => Promise<string>

function bindBackendCaller(caller?: BackendToolCaller): BackendToolCaller {
  return caller ?? (async (req) => (await import('./backendTools')).backendToolFetch(req))
}

/** Validate an optional ISO date arg and, when present + valid, return the original
 *  trimmed string to pass straight to the backend (which does its own parsing). */
function isoPassthrough(
  input: Record<string, unknown>,
  key: string,
  paramName: string
): { value?: string; error?: string } {
  const raw = input[key]
  const parsed = parseIsoDate(raw, paramName)
  if (parsed.error) return { error: parsed.error }
  if (parsed.ms === undefined || parsed.ms === null) return {}
  return { value: (raw as string).trim() }
}

/** `get_memories`. Lists stored facts/preferences via the backend tool endpoint
 *  under the HOST session token. */
export function createGetMemoriesExecutor(caller?: BackendToolCaller): ProductToolExecutor {
  const call = bindBackendCaller(caller)
  return async (input, ctx) => {
    const start = isoPassthrough(input, 'start_date', 'start_date')
    if (start.error) return start.error
    const end = isoPassthrough(input, 'end_date', 'end_date')
    if (end.error) return end.error
    return call({
      method: 'GET',
      path: '/v1/tools/memories',
      query: {
        limit: clampInt(input.limit, 50, 1, 5000),
        offset: clampInt(input.offset, 0, 0, 1_000_000),
        start_date: start.value,
        end_date: end.value
      },
      signal: ctx.signal
    })
  }
}

/** `search_memories`. Semantic search over memories via the backend tool endpoint. */
export function createSearchMemoriesExecutor(caller?: BackendToolCaller): ProductToolExecutor {
  const call = bindBackendCaller(caller)
  return async (input, ctx) => {
    const query = stringArg(input, 'query')
    if (!query) return 'Error: query is required'
    return call({
      method: 'POST',
      path: '/v1/tools/memories/search',
      body: { query, limit: clampInt(input.limit, 5, 1, 20) },
      signal: ctx.signal
    })
  }
}

/** `get_conversations`. Lists conversations by recency / date range via backend. */
export function createGetConversationsExecutor(caller?: BackendToolCaller): ProductToolExecutor {
  const call = bindBackendCaller(caller)
  return async (input, ctx) => {
    const start = isoPassthrough(input, 'start_date', 'start_date')
    if (start.error) return start.error
    const end = isoPassthrough(input, 'end_date', 'end_date')
    if (end.error) return end.error
    return call({
      method: 'GET',
      path: '/v1/tools/conversations',
      query: {
        limit: clampInt(input.limit, 20, 1, 5000),
        offset: clampInt(input.offset, 0, 0, 1_000_000),
        start_date: start.value,
        end_date: end.value,
        include_transcript:
          typeof input.include_transcript === 'boolean' ? input.include_transcript : undefined
      },
      signal: ctx.signal
    })
  }
}

/** `search_conversations`. Semantic search over conversations via backend. */
export function createSearchConversationsExecutor(caller?: BackendToolCaller): ProductToolExecutor {
  const call = bindBackendCaller(caller)
  return async (input, ctx) => {
    const query = stringArg(input, 'query')
    if (!query) return 'Error: query is required'
    const start = isoPassthrough(input, 'start_date', 'start_date')
    if (start.error) return start.error
    const end = isoPassthrough(input, 'end_date', 'end_date')
    if (end.error) return end.error
    const body: Record<string, unknown> = { query, limit: clampInt(input.limit, 5, 1, 20) }
    if (start.value) body.start_date = start.value
    if (end.value) body.end_date = end.value
    if (typeof input.include_transcript === 'boolean') {
      body.include_transcript = input.include_transcript
    }
    return call({
      method: 'POST',
      path: '/v1/tools/conversations/search',
      body,
      signal: ctx.signal
    })
  }
}

// --- get_goals (backend /v1/goals/all) ----------------------------------------

export type BackendJsonCaller = (req: BackendToolRequest) => Promise<BackendJsonResult>

function bindBackendJsonCaller(caller?: BackendJsonCaller): BackendJsonCaller {
  return caller ?? (async (req) => (await import('./backendTools')).backendJsonFetch(req))
}

/** The subset of the backend's GoalResponse (backend/models/goal.py) this
 *  formatter reads. `/v1/goals/all` returns a plain JSON array of these. */
interface BackendGoal {
  id?: unknown
  title?: unknown
  target_value?: unknown
  current_value?: unknown
  unit?: unknown
  is_active?: unknown
}

function formatGoalLine(index: number, g: BackendGoal): string {
  const title = typeof g.title === 'string' && g.title.trim() ? g.title.trim() : 'Untitled goal'
  const target = typeof g.target_value === 'number' ? g.target_value : null
  const current = typeof g.current_value === 'number' ? g.current_value : 0
  const unit = typeof g.unit === 'string' && g.unit.trim() ? ` ${g.unit.trim()}` : ''
  let progress = ''
  if (target != null && target > 0) {
    const pct = Math.round((current / target) * 100)
    progress = ` — progress: ${current}/${target}${unit} (${pct}%)`
  }
  const id = typeof g.id === 'string' ? ` (id: ${g.id})` : ''
  return `${index}. ${title}${progress}${id}`
}

/**
 * `get_goals`. Reads the user's goals from the SAME backend feed the Goals page
 * uses (`GET /v1/goals/all`, split active/completed by `is_active` — Goals.tsx)
 * under the HOST session token, and renders them as prose. No inputs.
 */
export function createGetGoalsExecutor(caller?: BackendJsonCaller): ProductToolExecutor {
  const call = bindBackendJsonCaller(caller)
  return async (_input, ctx) => {
    const result = await call({ method: 'GET', path: '/v1/goals/all', signal: ctx.signal })
    if (!result.ok) return result.error
    if (!Array.isArray(result.data)) return 'Error: unexpected goals response from the backend'
    const goals = result.data as BackendGoal[]
    if (goals.length === 0) {
      return 'No goals set yet. The user can create goals on the Goals page (or ask you to help pick one).'
    }
    const active = goals.filter((g) => g.is_active !== false)
    const completed = goals.filter((g) => g.is_active === false)
    const lines: string[] = [
      `Found ${goals.length} goal(s) (${active.length} active, ${completed.length} completed):`
    ]
    if (active.length > 0) {
      lines.push('', 'Active:')
      active.forEach((g, i) => lines.push(formatGoalLine(i + 1, g)))
    }
    if (completed.length > 0) {
      lines.push('', 'Completed:')
      completed.forEach((g, i) => lines.push(formatGoalLine(i + 1, g)))
    }
    return lines.join('\n')
  }
}

// --- get_work_context (composition) ------------------------------------------

/** Latest finalized frame is "fresh" up to this age; older is flagged stale. */
const WORK_CONTEXT_STALE_SECONDS = 60
const WORK_CONTEXT_TIMELINE_RUNS = 20

export interface WorkContextDeps {
  captureEnabled: () => boolean
  latestFrame: () => RewindFrame | null
  sampledFrames: (from: number, to: number) => RewindFrame[]
  now: () => number
}

// Fill missing edges for the deps-injected (test) path. Production never calls
// this — it awaits bindWorkContextProd() for the real db/settings edges.
function bindWorkContextDeps(deps?: Partial<WorkContextDeps>): WorkContextDeps {
  return {
    captureEnabled: deps?.captureEnabled ?? (() => true),
    latestFrame: deps?.latestFrame ?? (() => null),
    sampledFrames: deps?.sampledFrames ?? (() => []),
    now: deps?.now ?? (() => Date.now())
  }
}

function hhmm(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function normalizeWindow(title: string): string {
  return title.replace(/\s+/g, ' ').trim().slice(0, 80)
}

/** Collapse consecutive same-(app,window) frames into runs, most-recent-first,
 *  capped — the Mac get_work_context timeline shape (start/end clock, frames). */
function buildTimeline(frames: RewindFrame[]): Record<string, unknown>[] {
  const ordered = [...frames].sort((a, b) => a.ts - b.ts)
  const runs: { app: string; window: string; start: string; end: string; frames: number }[] = []
  for (const f of ordered) {
    const window = normalizeWindow(f.windowTitle ?? '')
    const cl = hhmm(f.ts)
    const last = runs[runs.length - 1]
    if (last && last.app === (f.app || 'Unknown') && last.window === window) {
      last.end = cl
      last.frames += 1
    } else {
      runs.push({ app: f.app || 'Unknown', window, start: cl, end: cl, frames: 1 })
    }
  }
  return runs
    .reverse()
    .slice(0, WORK_CONTEXT_TIMELINE_RUNS)
    .map((r) => ({ start: r.start, end: r.end, app: r.app, window: r.window, frames: r.frames }))
}

/**
 * `get_work_context`. Composes the user's current screen (latest rewind frame + its
 * OCR preview) plus a compressed timeline of recent on-screen activity, WITHOUT raw
 * screenshot pixels — pretty-printed JSON matching Mac's manifest shape
 * (screen_now / timeline / window_minutes / guidance). Windows failure taxonomy:
 * `capture_disabled` (Screen History off), `no_recent_capture` (nothing captured).
 * All local reads; honors ctx.signal.
 */
export function createGetWorkContextExecutor(deps?: Partial<WorkContextDeps>): ProductToolExecutor {
  return async (input, ctx) => {
    const bound = deps ? bindWorkContextDeps(deps) : await bindWorkContextProd()
    const minutes = clampInt(input.minutes, 10, 1, 120)
    if (aborted(ctx)) return 'Error: request was cancelled.'

    if (!bound.captureEnabled()) {
      return JSON.stringify(
        {
          ok: false,
          name: 'get_work_context',
          window_minutes: minutes,
          failure_code: 'capture_disabled',
          screen_now: { available: false, failure_code: 'capture_disabled' },
          timeline: [],
          guidance:
            'Screen History capture is turned off, so Omi cannot see the current screen or recent activity. Tell the user, and suggest enabling Screen History in settings if they want this.'
        },
        null,
        2
      )
    }

    const now = bound.now()
    const latest = bound.latestFrame()
    if (!latest) {
      return JSON.stringify(
        {
          ok: false,
          name: 'get_work_context',
          window_minutes: minutes,
          failure_code: 'no_recent_capture',
          screen_now: { available: false, failure_code: 'no_recent_capture' },
          timeline: [],
          guidance:
            'No screen history has been captured yet. Ask the user what they are working on instead of assuming.'
        },
        null,
        2
      )
    }

    const ageSeconds = Math.max(0, Math.round((now - latest.ts) / 1000))
    const stale = ageSeconds > WORK_CONTEXT_STALE_SECONDS
    const screenNow: Record<string, unknown> = {
      available: true,
      screenshot_id: latest.id ?? null,
      timestamp: new Date(latest.ts).toISOString(),
      app_name: latest.app || 'Unknown',
      window_title: latest.windowTitle || null,
      ocr_preview: (latest.ocrText ?? '').slice(0, 800),
      latest_capture_age_seconds: ageSeconds,
      note: stale
        ? `Latest available finalized frame is ~${ageSeconds}s old (older than ${WORK_CONTEXT_STALE_SECONDS}s); the user may have moved on. Call capture_screen only if you need raw pixels.`
        : 'Latest available finalized frame (may be up to ~1 min old). Call capture_screen with raw pixels only if the current screen contents matter.'
    }

    const timeline = buildTimeline(bound.sampledFrames(now - minutes * 60_000, now))

    return JSON.stringify(
      {
        ok: true,
        name: 'get_work_context',
        window_minutes: minutes,
        screen_now: screenNow,
        timeline,
        latest_capture_age_seconds: ageSeconds,
        freshness_threshold_seconds: WORK_CONTEXT_STALE_SECONDS,
        guidance:
          "This is the user's recent on-screen activity. Act on it directly instead of asking them to screenshot or re-explain what they were doing."
      },
      null,
      2
    )
  }
}

async function bindWorkContextProd(): Promise<WorkContextDeps> {
  const db = await import('../ipc/db')
  const { getPersistedRewindSettings } = await import('../rewind/rewindSettings')
  return {
    captureEnabled: () => getPersistedRewindSettings().captureEnabled,
    latestFrame: () => db.latestRewindFrame(),
    sampledFrames: (from, to) => db.listRewindFramesSampled(from, to),
    now: () => Date.now()
  }
}

// --- get_daily_recap (composition) -------------------------------------------

/** Windows capture is ~1 frame/second (rewindSettings default intervalMs=1000),
 *  so screenshot count ≈ seconds of activity. */
const RECAP_FRAME_SECONDS = 1

export interface DailyRecapDeps {
  now: () => number
  appActivity: (
    from: number,
    to: number
  ) => { app: string; windowTitle: string; count: number; firstSeen: number; lastSeen: number }[]
  conversations: () => LocalConversation[]
  actionItems: () => ActionItemRecord[]
  focusSessions: (sinceMs: number) => FocusSessionRecord[]
  memories: (limit: number) => { content: string; category: string }[]
  insights: (limit: number) => InsightRecord[]
}

function bindDailyRecapDeps(deps?: Partial<DailyRecapDeps>): DailyRecapDeps {
  return {
    now: deps?.now ?? (() => Date.now()),
    appActivity:
      deps?.appActivity ??
      (() => {
        throw new Error('appActivity dep required')
      }),
    conversations: deps?.conversations ?? (() => []),
    actionItems: deps?.actionItems ?? (() => []),
    focusSessions: deps?.focusSessions ?? (() => []),
    memories: deps?.memories ?? (() => []),
    insights: deps?.insights ?? (() => [])
  }
}

/** Local midnight (start of day) for the timestamp `ms`, in the host timezone. */
function startOfLocalDay(ms: number): number {
  const d = new Date(ms)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0).getTime()
}

/**
 * `get_daily_recap`. Pre-formatted markdown activity recap for a day (0=today,
 * 1=yesterday, N=past N days), composed entirely from LOCAL reads: app usage
 * (rewind aggregate), conversations, tasks created, focus sessions, recent
 * memories, and proactive observations. Matches the Mac recap's section layout.
 */
export function createGetDailyRecapExecutor(deps?: Partial<DailyRecapDeps>): ProductToolExecutor {
  return async (input, ctx) => {
    const d = deps ? bindDailyRecapDeps(deps) : await bindDailyRecapProd()
    if (aborted(ctx)) return 'Error: request was cancelled.'
    const daysAgo = Math.max(0, intArg(input.days_ago) ?? 1)
    const label = daysAgo === 0 ? 'Today' : daysAgo === 1 ? 'Yesterday' : `Past ${daysAgo} days`

    const now = d.now()
    const startToday = startOfLocalDay(now)
    const from = startToday - daysAgo * DAY_MS
    const to = daysAgo === 0 ? now : startToday
    const inWindow = (ts: number): boolean => ts >= from && ts < to

    // Apps: per-app minutes (re-aggregate the (app,window) rows by app).
    const byApp = new Map<string, { count: number; first: number; last: number }>()
    for (const r of d.appActivity(from, to)) {
      const e = byApp.get(r.app) ?? { count: 0, first: r.firstSeen, last: r.lastSeen }
      e.count += r.count
      e.first = Math.min(e.first, r.firstSeen)
      e.last = Math.max(e.last, r.lastSeen)
      byApp.set(r.app, e)
    }
    const apps = [...byApp.entries()]
      .map(([app, e]) => ({ app, ...e }))
      .sort((a, b) => b.count - a.count)

    const convos = d.conversations().filter((c) => inWindow(c.createdAt))
    const tasks = d.actionItems().filter((t) => !t.deleted && inWindow(t.createdAt))
    const focus = d.focusSessions(from).filter((f) => inWindow(f.createdAt))
    const memories = d.memories(10)
    const observations = d.insights(30).filter((i) => inWindow(i.ts))

    const out: string[] = [`# ${label} Recap`, '']

    out.push(`## Apps (${apps.length} apps)`)
    if (apps.length === 0) out.push('No screen activity recorded.')
    else {
      for (const a of apps.slice(0, 20)) {
        const minutes = Math.round((a.count * RECAP_FRAME_SECONDS) / 60)
        out.push(
          `- **${a.app}**: ${minutes} min (${a.count} captures, ${hhmm(a.first)}–${hhmm(a.last)})`
        )
      }
      if (apps.length > 20) out.push(`- ...and ${apps.length - 20} more apps`)
    }

    out.push('', `## Conversations (${convos.length})`)
    if (convos.length === 0) out.push('No conversations recorded.')
    else {
      for (const c of convos) {
        const title = c.title || (c.kind === 'chat' ? 'Chat with Omi' : 'Recording')
        const durMin = Math.max(0, Math.round((c.endedAt - c.startedAt) / 60_000))
        const dur = durMin > 0 ? ` (${durMin} min)` : ''
        const preview = (c.transcript || '').replace(/\s+/g, ' ').trim().slice(0, 120)
        out.push(`- **${title}**${dur}${preview ? `: ${preview}` : ''}`)
      }
    }

    out.push('', `## Tasks (${tasks.length})`)
    if (tasks.length === 0) out.push('No tasks created.')
    else {
      for (const t of tasks) {
        const check = t.completed ? '[x]' : '[ ]'
        const pri = t.priority ? ` (${t.priority})` : ''
        out.push(`- ${check} ${t.description}${pri}`)
      }
    }

    if (focus.length > 0) {
      const focused = focus.filter((f) => f.status === 'focused').length
      const distracted = focus.length - focused
      out.push('', `## Focus (${focused} focused, ${distracted} distracted)`)
      for (const f of focus.slice(0, 10)) {
        const icon = f.status === 'focused' ? '+' : '-'
        const durMin = Math.round(f.durationSeconds / 60)
        const durStr = durMin > 0 ? ` (${durMin}m)` : ''
        out.push(`- ${icon} ${f.appOrSite ?? 'Unknown'}${durStr}: ${f.description ?? ''}`)
      }
      if (focus.length > 10) out.push(`- ...and ${focus.length - 10} more sessions`)
    }

    if (memories.length > 0) {
      out.push('', `## Memories (${memories.length} recent)`)
      for (const m of memories) {
        const cat = m.category ? ` [${m.category}]` : ''
        out.push(`- ${m.content}${cat}`)
      }
    }

    if (observations.length > 0) {
      out.push('', `## Screen Context (${observations.length} observations)`)
      for (const o of observations.slice(0, 10)) {
        out.push(`- ${o.sourceApp || 'Unknown'}: ${o.headline}`)
      }
      if (observations.length > 10) {
        out.push(`- ...and ${observations.length - 10} more observations`)
      }
    }

    return out.join('\n')
  }
}

async function bindDailyRecapProd(): Promise<DailyRecapDeps> {
  const db = await import('../ipc/db')
  return {
    now: () => Date.now(),
    appActivity: (from, to) => db.rewindActivityAggregate(from, to),
    conversations: () => db.listLocalConversations(),
    actionItems: () => db.getLocalActionItems({ limit: 500 }),
    focusSessions: (sinceMs) => db.listFocusSessions(sinceMs),
    memories: (limit) => db.recentMemories(limit),
    insights: (limit) => db.recentInsights(limit)
  }
}

// --- save_knowledge_graph ----------------------------------------------------

export interface SaveKnowledgeGraphDeps {
  upsert: (nodes: OnboardingGraphNode[], edges: OnboardingGraphEdge[]) => void
}

const KG_NODE_TYPES = new Set(['person', 'organization', 'place', 'thing', 'concept'])

/**
 * `save_knowledge_graph`. Maps the manifest shape
 * `{nodes:[{id,label,node_type,aliases}], edges:[{source_id,target_id,label}]}`
 * onto db.ts upsertLocalGraph (onboarding_kg_*), which dedupes via ON CONFLICT.
 * Edges get a stable synthesized id so re-saves upsert rather than duplicate; edges
 * are kept only when both endpoints are among the provided nodes.
 */
export function createSaveKnowledgeGraphExecutor(
  deps?: Partial<SaveKnowledgeGraphDeps>
): ProductToolExecutor {
  return async (input) => {
    const rawNodes = Array.isArray(input.nodes) ? input.nodes : []
    const rawEdges = Array.isArray(input.edges) ? input.edges : []

    const nodes: OnboardingGraphNode[] = []
    const nodeIds = new Set<string>()
    for (const n of rawNodes) {
      if (!n || typeof n !== 'object') continue
      const o = n as Record<string, unknown>
      const id = typeof o.id === 'string' ? o.id.trim() : ''
      const labelRaw = typeof o.label === 'string' ? o.label.trim() : ''
      if (!id || !labelRaw) continue
      const nodeType =
        typeof o.node_type === 'string' && KG_NODE_TYPES.has(o.node_type) ? o.node_type : 'thing'
      const aliases = Array.isArray(o.aliases)
        ? o.aliases.filter((a): a is string => typeof a === 'string' && a.trim().length > 0)
        : undefined
      nodes.push({ id, label: labelRaw, nodeType, aliases })
      nodeIds.add(id)
    }

    const edges: OnboardingGraphEdge[] = []
    const seenEdges = new Set<string>()
    for (const e of rawEdges) {
      if (!e || typeof e !== 'object') continue
      const o = e as Record<string, unknown>
      const sourceId = typeof o.source_id === 'string' ? o.source_id.trim() : ''
      const targetId = typeof o.target_id === 'string' ? o.target_id.trim() : ''
      const edgeLabel = typeof o.label === 'string' ? o.label.trim() : ''
      if (!sourceId || !targetId || !edgeLabel) continue
      if (!nodeIds.has(sourceId) || !nodeIds.has(targetId)) continue
      const id = `${sourceId} ${targetId} ${edgeLabel}`
      if (seenEdges.has(id)) continue
      seenEdges.add(id)
      edges.push({ id, sourceId, targetId, label: edgeLabel })
    }

    if (nodes.length === 0) return 'Error: no valid nodes to save (each needs id + label).'

    const upsert = deps?.upsert ?? (await import('../ipc/db')).upsertLocalGraph
    upsert(nodes, edges)
    return `OK: saved ${nodes.length} entities and ${edges.length} relationships to your knowledge graph`
  }
}

// --- registry contribution ---------------------------------------------------

/**
 * The Tier-A executors, keyed by pi-mono tool name. Merged into
 * defaultProductToolExecutors (toolRelayBridge.ts); adding a key here auto-extends
 * WINDOWS_SERVICEABLE_PRODUCT_TOOLS (and thus the pi advertisement) with no manifest
 * or env change. `search_screen_history` is NOT keyed: pi-mono advertises the tool as
 * `semantic_search` (the alias is a local-agent-api adapter name), so the relay only
 * ever dispatches `semantic_search`.
 */
export function tierAProductToolExecutors(): [string, ProductToolExecutor][] {
  return [
    ['semantic_search', createSemanticSearchExecutor()],
    ['search_tasks', createSearchTasksExecutor()],
    ['get_action_items', createGetActionItemsExecutor()],
    ['create_action_item', createCreateActionItemExecutor()],
    ['update_action_item', createUpdateActionItemExecutor()],
    ['complete_task', createCompleteTaskExecutor()],
    ['delete_task', createDeleteTaskExecutor()]
  ]
}

/**
 * The Tier-B executors (PR-4..7), keyed by pi-mono tool name. Merged into
 * defaultProductToolExecutors alongside Tier-A; adding a key here auto-extends
 * WINDOWS_SERVICEABLE_PRODUCT_TOOLS (and the pi advertisement) with no manifest or
 * env change — identical wiring to Tier-A. Every executor keeps load-purity: the
 * native / electron edges (db.ts, backendTools' `net`, rewindSettings) are reached
 * by CALL-TIME dynamic import, never at module load.
 */
export function tierBProductToolExecutors(): [string, ProductToolExecutor][] {
  return [
    ['execute_sql', createExecuteSqlExecutor()],
    ['get_memories', createGetMemoriesExecutor()],
    ['search_memories', createSearchMemoriesExecutor()],
    ['get_conversations', createGetConversationsExecutor()],
    ['search_conversations', createSearchConversationsExecutor()],
    ['get_goals', createGetGoalsExecutor()],
    ['get_work_context', createGetWorkContextExecutor()],
    ['get_daily_recap', createGetDailyRecapExecutor()],
    ['save_knowledge_graph', createSaveKnowledgeGraphExecutor()]
  ]
}
