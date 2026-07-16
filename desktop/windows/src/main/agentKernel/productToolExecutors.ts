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
// read is local. Errors are RETURNED as `"Error: …"` strings, never thrown past the
// relay's tool_result contract. The one network-touching read (semantic_search's
// query embedding) honors ctx.signal.

import type { ProductToolContext, ProductToolExecutor } from './toolRelayBridge'
import type { ActionItemRecord, RewindFrame } from '../../shared/types'
import type { TaskSearchResult } from '../assistants/tasks/toolBackends'

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

    const description = typeof input.description === 'string' ? input.description : undefined
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
