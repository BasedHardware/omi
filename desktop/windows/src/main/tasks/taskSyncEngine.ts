// Track 3 — the local-first task SYNC ENGINE (main process). A faithful port of
// macOS `TasksStore`: the single source of truth for the user-facing Tasks list.
// It OWNS the local SQLite action_items store (via the ipc/db wrappers) AND
// hand-rolls the backend REST (`net.fetch` + the relayed session), exactly like
// aiUserProfile/service.ts and the focus/persist dual-write. The renderer is thin
// — it drives everything through the `tasks:*` IPC channels (see ipc/tasks.ts);
// it never calls the backend for tasks directly.
//
// TOKEN MODEL (Windows): the Firebase token lives in the RENDERER, so the engine
// reads the SHARED backend session held by assistants/core/session.ts (relayed by
// the renderer on sign-in + hourly refresh). With no session, every REST path is a
// soft no-op and reads/writes stay purely local until a session arrives.
//
// SAFETY — the epoch guard (core/session.ts): a write that follows an `await` must
// re-check `getSessionEpoch()` against the epoch pinned before the request. A
// sign-out (or user switch) mid-request bumps the epoch, so the result is dropped
// rather than written into the next user's DB. Every request also composes the
// session's `getAbortSignal()` so it dies promptly on a session change.
//
// OPTIMISTIC WRITE-THROUGH (Mac behavior, ported verbatim):
//   - create : insert local (unsynced) → POST → markSynced on success; on failure
//              stays unsynced (retried at next hydrate). NEVER reverted.
//   - toggle : flip local → PATCH; on success absorb the server echo; on failure
//              REVERT the local completion.
//   - update : edit local → PATCH; on failure keep-local (next sync reconciles).
//   - delete : HARD-delete local → DELETE; on failure keep-local-deleted.
//
// FIX (ii) — embedding eviction via DEPENDENCY INJECTION (no hard import of the
// embedding service): `setTaskDeletionListener` wires a callback that every
// hard-delete path (deleteTask + the reconcile sweep) calls with the storage-
// returned deleted ids. App startup wires the embedding index's evictor to it.
import { BrowserWindow, net } from 'electron'
import {
  deleteActionItemByBackendId,
  getAppMeta,
  getFilteredActionItems,
  getLocalActionItems,
  getUnsyncedActionItems,
  hardDeleteAbsentTasks,
  insertLocalActionItem,
  markSyncedActionItem,
  setAppMeta,
  syncTaskActionItems,
  updateActionItemFields,
  updateCompletionStatus
} from '../ipc/db'
import {
  fetchWithFreshToken,
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  type BackendSession
} from '../assistants/core/session'
import type {
  ActionItemRecord,
  SyncActionItem,
  TaskCreateFields,
  TaskDashboardSlices,
  TaskOpFailure,
  TaskUpdateFields
} from '../../shared/types'
// Event-driven promotion (Mac's TasksStore complete/delete triggers). Import is
// cycle-safe: create.ts imports only ipc/db, taskEmbeddingService, core/session,
// electron, and shared types — none of which import this engine.
import { promoteIfNeeded } from '../assistants/tasks/create'

// --- Tunables ---------------------------------------------------------------
const REQUEST_TIMEOUT_MS = 15_000
// Reconcile (hard-delete tasks absent from the backend) at most once per 5 min —
// Mac's `lastReconcileAt` throttle. Prevents an every-keystroke reconcile sweep.
const RECONCILE_THROTTLE_MS = 5 * 60_000
// Page size for full listings (the backend caps `limit` at 500).
const PAGE_LIMIT = 500
// Hard ceiling on paging so a runaway `has_more` can never loop forever.
const MAX_PAGES = 200

// --- FIX (ii): the embedding-eviction DI seam --------------------------------

/** One locally hard-deleted task, handed to the deletion listener so the caller
 *  can evict it from the in-memory embedding index. Mirrors the storage source. */
export type TaskDeletion = { source: 'action_item'; id: number }
export type TaskDeletionListener = (deleted: TaskDeletion[]) => void

// Default no-op: the engine works standalone; app startup injects the real evictor.
let deletionListener: TaskDeletionListener = () => {}

/** Wire the embedding index's evictor (or any observer) to every hard-delete. The
 *  engine hard-imports nothing from the embedding service — this is the only seam.
 *  Default is a no-op, so the engine is fully functional before it is wired. */
export function setTaskDeletionListener(fn: TaskDeletionListener): void {
  deletionListener = fn
}

function emitDeletions(ids: number[]): void {
  if (ids.length === 0) return
  try {
    deletionListener(ids.map((id) => ({ source: 'action_item' as const, id })))
  } catch (e) {
    console.warn('[tasks] deletion listener threw:', errName(e))
  }
}

// --- Module state ------------------------------------------------------------
let lastReconcileAt = 0
let retrying = false
let hydrateIncompleteInFlight: Promise<void> | null = null
let hydrateCompletedInFlight: Promise<void> | null = null

// --- Pending-delete tombstones ----------------------------------------------
// A user delete is a HARD local delete + a fire-and-forget backend DELETE. Without
// this guard, a hydrate GET that raced the delete (or ran while the DELETE was
// dropped by a 429 storm) re-inserts the row from a list that still contains it —
// the "delete then the row comes back" divergence. We tombstone the deleted
// backend_id so syncTaskActionItems skips re-inserting it until the DELETE settles.
// TTL-bounded so a lost confirmation can't wedge a row as permanently invisible.
const TOMBSTONE_TTL_MS = 10 * 60_000
const pendingDeletes = new Map<string, number>() // backendId -> expiresAt (epoch ms)

function tombstoneDelete(backendId: string): void {
  pendingDeletes.set(backendId, Date.now() + TOMBSTONE_TTL_MS)
}
function clearTombstone(backendId: string): void {
  pendingDeletes.delete(backendId)
}
/** True while a delete for this backend_id is unresolved. Lazily evicts on expiry. */
function isTombstoned(backendId: string): boolean {
  const expiresAt = pendingDeletes.get(backendId)
  if (expiresAt === undefined) return false
  if (expiresAt <= Date.now()) {
    pendingDeletes.delete(backendId)
    return false
  }
  return true
}

/** Test-only: reset tombstone state between cases. */
export function __resetTombstonesForTest(): void {
  pendingDeletes.clear()
}
/** Test-only: inspect whether a backend_id is currently tombstoned. */
export function __isTombstonedForTest(backendId: string): boolean {
  return isTombstoned(backendId)
}

// --- Backend item shape + mapping -------------------------------------------
// Authoritative shape from backend/routers/action_items.py `ActionItemResponse`
// (verified against source, not guessed): the LIST envelope is
// `{ action_items: [...], has_more }` (NOT `{ items }`), and the item has NO
// priority/category/tags/source/deleted fields — those stay Windows-local-only.
type BackendActionItem = {
  id: string
  description: string
  completed: boolean
  created_at?: string | null
  updated_at?: string | null
  due_at?: string | null
  conversation_id?: string | null
  sort_order?: number | null
  indent_level?: number | null
}

function toEpochMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : t
}

/** Map a backend action item → the storage `SyncActionItem` for syncTaskActionItems.
 *  `now` fills a missing created_at so the required `createdAt` is always present. */
function mapBackendItem(item: BackendActionItem, now: number): SyncActionItem {
  const createdAt = toEpochMs(item.created_at) ?? now
  const updatedAt = toEpochMs(item.updated_at) ?? createdAt
  return {
    backendId: item.id,
    description: item.description,
    completed: item.completed,
    conversationId: item.conversation_id ?? null,
    dueAt: toEpochMs(item.due_at),
    sortOrder: item.sort_order ?? null,
    indentLevel: item.indent_level ?? null,
    createdAt,
    updatedAt
  }
}

// --- HTTP helpers ------------------------------------------------------------

class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`)
    this.name = 'HttpError'
  }
}

/** name/status only — never a raw body (repo logging-security rule): a JSON parse
 *  error can echo a fragment of a user-data response. An HttpError surfaces its
 *  STATUS (e.g. "HTTP 401"): logging only `e.name` collapsed every backend failure
 *  to a bare "HttpError" and hid the stale-token 401s this file now refreshes. */
function errName(e: unknown): string {
  if (e instanceof HttpError) return `HTTP ${e.status}`
  return e instanceof Error ? e.name : 'Error'
}

// Shared AbortController + timer dance: caps a hung request, and composes the
// session's abort signal so a sign-out kills every in-flight request at once.
async function withTimeout<T>(
  ms: number,
  fn: (signal: AbortSignal) => Promise<T>,
  external?: AbortSignal
): Promise<T> {
  const ctrl = new AbortController()
  const onExternalAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), ms)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onExternalAbort, { once: true })
  try {
    return await fn(ctrl.signal)
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onExternalAbort)
  }
}

// electron net.fetch uses Chromium's network stack (proxy/TLS aware) — same path
// as aiUserProfile/service.ts. `body` is JSON-encoded when present.
//
// fetchWithFreshToken (core/session) wraps every call with pull-based token
// freshness: it hands the fetch closure the CURRENT session (so the retry uses a
// freshly pulled token, not the one captured at operation start), pre-empts a
// doomed 401 when the cached token is already expired, and on a 401 pulls a fresh
// token and retries once. The per-attempt timeout + session abort still compose
// via withTimeout, once per attempt.
async function apiFetch(
  method: string,
  path: string,
  body: unknown,
  external?: AbortSignal
): Promise<Response> {
  return fetchWithFreshToken((session) =>
    withTimeout(
      REQUEST_TIMEOUT_MS,
      (signal) =>
        net.fetch(`${session.apiBase}${path}`, {
          method,
          headers: {
            Authorization: `Bearer ${session.token}`,
            'Content-Type': 'application/json'
          },
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal
        }),
      external
    )
  )
}

/** Page one listing. `completed` undefined = all; the envelope is
 *  `{ action_items, has_more }`. */
async function fetchPage(
  completed: boolean | undefined,
  offset: number,
  external?: AbortSignal
): Promise<{ items: BackendActionItem[]; hasMore: boolean }> {
  const q = new URLSearchParams({ limit: String(PAGE_LIMIT), offset: String(offset) })
  if (completed !== undefined) q.set('completed', String(completed))
  const res = await apiFetch('GET', `/v1/action-items?${q.toString()}`, undefined, external)
  if (!res.ok) throw new HttpError(res.status)
  const json = (await res.json()) as { action_items?: BackendActionItem[]; has_more?: boolean }
  return {
    items: Array.isArray(json.action_items) ? json.action_items : [],
    hasMore: json.has_more === true
  }
}

/** Page an entire listing (until has_more is false). Bails if the session epoch
 *  moved mid-paging. */
async function fetchAll(
  completed: boolean | undefined,
  epoch: number,
  external?: AbortSignal
): Promise<BackendActionItem[]> {
  const out: BackendActionItem[] = []
  let offset = 0
  for (let page = 0; page < MAX_PAGES; page++) {
    if (getSessionEpoch() !== epoch) break
    const { items, hasMore } = await fetchPage(completed, offset, external)
    out.push(...items)
    if (!hasMore || items.length === 0) break
    offset += PAGE_LIMIT
  }
  return out
}

// --- Renderer notification ---------------------------------------------------

/** Tell every window the local task store changed, so the renderer re-fetches.
 *  Mirrors the `conversations:changed` broadcast. */
function broadcastTasksChanged(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('tasks:changed')
  }
}

/** Tell the renderer a task mutation the user saw did NOT stick, so it can surface a
 *  toast instead of failing silently. Payload carries the op + a display message.
 *  (The delete path's renderer catch was dead code — the IPC resolves before the
 *  background DELETE runs — so this is the only honest failure signal for it.) */
function emitTaskOpFailed(failure: TaskOpFailure): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('tasks:opFailed', failure)
  }
}

// --- Backend body builders ---------------------------------------------------

/** POST body for a create (backend `CreateActionItemRequest`). due_at is ISO or
 *  omitted; priority/category/tags/source have no backend field. */
function createBody(fields: {
  description: string
  completed?: boolean
  dueAt?: number | null
  conversationId?: string | null
}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    description: fields.description,
    completed: fields.completed ?? false,
    conversation_id: fields.conversationId ?? null
  }
  if (fields.dueAt != null) body.due_at = new Date(fields.dueAt).toISOString()
  return body
}

/** PATCH body for an update (backend `UpdateActionItemRequest`). Only the mappable
 *  fields are sent; `clearDueAt` sends an explicit null (backend clears on it).
 *  Returns `{}` when only Windows-local-only fields changed → skip the request. */
function updateBody(fields: TaskUpdateFields): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  if (fields.description !== undefined) body.description = fields.description
  if (fields.completed !== undefined) body.completed = fields.completed
  if (fields.clearDueAt) body.due_at = null
  else if (fields.dueAt !== undefined)
    body.due_at = fields.dueAt != null ? new Date(fields.dueAt).toISOString() : null
  return body
}

// --- Reconcile ---------------------------------------------------------------

/** Hard-delete synced active tasks absent from `apiIds` (throttled to once / 5 min
 *  unless `force`). The storage guard makes an empty `apiIds` a no-op, so an empty
 *  or failed listing never wipes local data. FIX (ii): evict the deleted ids. */
function maybeReconcile(apiIds: string[], now: number, force = false): void {
  if (!force && now - lastReconcileAt < RECONCILE_THROTTLE_MS) return
  lastReconcileAt = now
  const deleted = hardDeleteAbsentTasks(apiIds)
  if (deleted.length > 0) {
    emitDeletions(deleted)
    broadcastTasksChanged()
  }
}

// --- One-time versioned full sync -------------------------------------------

/** Derive the uid from the Firebase token's `user_id`/`sub` claim (decode, not
 *  verify — the value only keys a local flag). Same idiom as ipc/omiListen.ts. */
function uidFromToken(token: string): string | null {
  try {
    const payload = JSON.parse(
      Buffer.from(token.split('.')[1] ?? '', 'base64').toString('utf8')
    ) as Record<string, unknown>
    const uid = payload.user_id ?? payload.sub
    return typeof uid === 'string' && uid.length > 0 ? uid : null
  } catch {
    return null
  }
}

/** Once per (user, schema version): page EVERYTHING (incomplete + completed) so the
 *  local store starts fully populated, then reconcile once. The flag lives in
 *  app_meta (survives sign-out, keyed per uid) so it runs exactly once per install
 *  per account. */
async function maybeFullSync(
  session: BackendSession,
  epoch: number,
  external?: AbortSignal
): Promise<void> {
  const uid = uidFromToken(session.token)
  if (!uid) return
  const key = `tasksFullSyncCompleted_v1_${uid}`
  if (getAppMeta(key)) return
  const incomplete = await fetchAll(false, epoch, external)
  const completed = await fetchAll(true, epoch, external)
  if (getSessionEpoch() !== epoch) return
  const now = Date.now()
  syncTaskActionItems(
    [...incomplete, ...completed].map((i) => mapBackendItem(i, now)),
    {
      now,
      isTombstoned
    }
  )
  // The one-time full sync forces a reconcile regardless of the 5-min throttle.
  maybeReconcile(
    incomplete.map((i) => i.id),
    now,
    true
  )
  setAppMeta(key, '1')
  broadcastTasksChanged()
}

// --- Hydration (local-first) -------------------------------------------------

/** Sync the incomplete list from the backend, then reconcile. Deduped: concurrent
 *  callers share the one in-flight run. On the first run per account it also drains
 *  unsynced creates and does the one-time full sync. Errors are swallowed (logged
 *  name-only) — hydration is best-effort over the always-available local read. */
export function hydrateIncomplete(): Promise<void> {
  if (hydrateIncompleteInFlight) return hydrateIncompleteInFlight
  hydrateIncompleteInFlight = doHydrateIncomplete().finally(() => {
    hydrateIncompleteInFlight = null
  })
  return hydrateIncompleteInFlight
}

async function doHydrateIncomplete(): Promise<void> {
  const session = getBackendSession()
  if (!session) return // local-only until a session is relayed
  const epoch = getSessionEpoch()
  const external = getAbortSignal()
  try {
    await retryUnsynced()
    await maybeFullSync(session, epoch, external)
    if (getSessionEpoch() !== epoch) return
    const items = await fetchAll(false, epoch, external)
    if (getSessionEpoch() !== epoch) return
    const now = Date.now()
    const res = syncTaskActionItems(
      items.map((i) => mapBackendItem(i, now)),
      { now, isTombstoned }
    )
    // maybeReconcile broadcasts on its own iff it hard-deletes something. Here we
    // broadcast only when the sync actually changed a row — a no-op hydrate MUST
    // stay silent, else the renderer (which re-reads on `tasks:changed`, and every
    // read kicks another hydrate) spins in an unbounded backend-polling loop.
    maybeReconcile(
      items.map((i) => i.id),
      now
    )
    if (res.inserted + res.updated + res.adopted > 0) broadcastTasksChanged()
  } catch (e) {
    console.warn('[tasks] hydrateIncomplete failed:', errName(e))
  }
}

/** Sync the completed list (no reconcile — hardDeleteAbsentTasks only ever touches
 *  active rows, so a completed listing must never drive it). Deduped. */
export function hydrateCompleted(): Promise<void> {
  if (hydrateCompletedInFlight) return hydrateCompletedInFlight
  hydrateCompletedInFlight = doHydrateCompleted().finally(() => {
    hydrateCompletedInFlight = null
  })
  return hydrateCompletedInFlight
}

async function doHydrateCompleted(): Promise<void> {
  const session = getBackendSession()
  if (!session) return
  const epoch = getSessionEpoch()
  const external = getAbortSignal()
  try {
    const items = await fetchAll(true, epoch, external)
    if (getSessionEpoch() !== epoch) return
    const now = Date.now()
    const res = syncTaskActionItems(
      items.map((i) => mapBackendItem(i, now)),
      { now, isTombstoned }
    )
    // Broadcast only on an actual change — see doHydrateIncomplete for why a silent
    // no-op hydrate is mandatory (renderer re-read → hydrate → broadcast loop).
    if (res.inserted + res.updated + res.adopted > 0) broadcastTasksChanged()
  } catch (e) {
    console.warn('[tasks] hydrateCompleted failed:', errName(e))
  }
}

// --- Reads (local-first: return local instantly, kick background hydration) ---

/** Incomplete tasks — returns the LOCAL rows instantly and kicks a background sync
 *  (subscribe to `tasks:changed` to re-fetch). */
export function listIncomplete(opts?: { limit?: number; offset?: number }): ActionItemRecord[] {
  void hydrateIncomplete()
  return getLocalActionItems({ completed: false, limit: opts?.limit, offset: opts?.offset })
}

/** Completed tasks — local-first, kicks a background completed sync. */
export function listCompleted(opts?: { limit?: number; offset?: number }): ActionItemRecord[] {
  void hydrateCompleted()
  return getLocalActionItems({ completed: true, limit: opts?.limit, offset: opts?.offset })
}

/** Deleted tasks. NOTE: the Windows storage layer HARD-deletes user deletions and
 *  exposes no reader for `deleted = 1` rows (getLocalActionItems/getFilteredActionItems
 *  all filter `deleted = 0`), and the backend GET has no "deleted" concept. So this
 *  currently returns []. Surfacing a real "recently deleted" list needs a
 *  `getDeletedActionItems` storage wrapper (owned by the storage wave — out of this
 *  PR's scope). The channel is defined now so the renderer wave has the full contract. */
export function listDeleted(_opts?: { limit?: number; offset?: number }): ActionItemRecord[] {
  return []
}

/** Dashboard slices for the Tasks home: overdue / due-today / no-due — all active
 *  tasks, read from local (getFilteredActionItems), with a background sync kicked. */
export function dashboardSlices(): TaskDashboardSlices {
  void hydrateIncomplete()
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const startToday = start.getTime()
  const tomorrow = new Date(startToday)
  tomorrow.setDate(tomorrow.getDate() + 1)
  const startTomorrow = tomorrow.getTime()
  return {
    overdue: getFilteredActionItems({ dueBefore: startToday }),
    today: getFilteredActionItems({ dueAfter: startToday, dueBefore: startTomorrow }),
    noDue: getFilteredActionItems({ dueIsNull: true })
  }
}

// --- Optimistic write-through ------------------------------------------------

/** Create a task: insert locally (unsynced) and return the row immediately; POST in
 *  the background. On success stamp it synced with the backend id. On FAILURE it
 *  stays unsynced (retried at the next hydrate) — never reverted. */
export function createTask(fields: TaskCreateFields): ActionItemRecord {
  const now = Date.now()
  const rec = insertLocalActionItem({
    description: fields.description,
    completed: fields.completed ?? false,
    source: fields.source ?? 'manual',
    conversationId: fields.conversationId ?? null,
    priority: fields.priority ?? null,
    category: fields.category ?? null,
    tags: fields.tags,
    dueAt: fields.dueAt ?? null,
    createdAt: now,
    updatedAt: now
  })
  void pushCreate(rec.id, fields, getSessionEpoch())
  broadcastTasksChanged()
  return rec
}

async function pushCreate(localId: number, fields: TaskCreateFields, epoch: number): Promise<void> {
  const session = getBackendSession()
  if (!session) return // stays unsynced — retryUnsynced picks it up later
  const external = getAbortSignal()
  try {
    const res = await apiFetch('POST', '/v1/action-items', createBody(fields), external)
    if (!res.ok) throw new HttpError(res.status)
    const created = (await res.json()) as BackendActionItem
    if (getSessionEpoch() !== epoch) return
    if (created?.id) {
      markSyncedActionItem(localId, created.id, Date.now())
      broadcastTasksChanged()
    }
  } catch (e) {
    console.warn('[tasks] create sync failed (kept local, will retry):', errName(e))
  }
}

/** Toggle completion: flip locally, PATCH in the background. On success absorb the
 *  server echo; on FAILURE REVERT the local completion (Mac behavior). */
export function toggleTask(backendId: string, completed: boolean): void {
  updateCompletionStatus(backendId, completed, Date.now())
  broadcastTasksChanged()
  void pushToggle(backendId, completed, getSessionEpoch())
  // Event-driven promote (Mac TasksStore.swift:1225): completing a task vacates a
  // slot, so pull the top staged task up. ONLY on complete (not un-complete), like
  // Mac. Deviation: UNGATED — Mac gates on `source contains "screenshot"`, but the
  // Windows call site has only `backendId` (`source` isn't hydrated from the backend
  // LIST), and the gate only skips one debounced POST that returns {promoted:false}
  // when nothing is staged. Fire-and-forget (`void`): cannot slow or fail the
  // toggle, cannot regress the revert-on-failure path (promoteIfNeeded is internally
  // error-guarded and never rejects).
  if (completed) void promoteIfNeeded()
}

async function pushToggle(backendId: string, completed: boolean, epoch: number): Promise<void> {
  const session = getBackendSession()
  if (!session) return
  const external = getAbortSignal()
  try {
    const res = await apiFetch(
      'PATCH',
      `/v1/action-items/${encodeURIComponent(backendId)}`,
      { completed },
      external
    )
    if (!res.ok) throw new HttpError(res.status)
    const item = (await res.json()) as BackendActionItem
    if (getSessionEpoch() !== epoch) return
    syncTaskActionItems([mapBackendItem(item, Date.now())], { now: Date.now(), isTombstoned })
    broadcastTasksChanged()
  } catch (e) {
    console.warn('[tasks] toggle sync failed — reverting:', errName(e))
    // Re-check the epoch: never revert into a different user's DB after sign-out.
    if (getSessionEpoch() !== epoch) return
    updateCompletionStatus(backendId, !completed, Date.now())
    broadcastTasksChanged()
  }
}

/** Edit task fields: apply locally, PATCH the mappable fields in the background. On
 *  FAILURE keep the local edit (the next sync reconciles) — no revert. */
export function updateTask(backendId: string, fields: TaskUpdateFields): void {
  updateActionItemFields(backendId, fields, Date.now())
  broadcastTasksChanged()
  void pushUpdate(backendId, fields, getSessionEpoch())
}

async function pushUpdate(
  backendId: string,
  fields: TaskUpdateFields,
  epoch: number
): Promise<void> {
  const session = getBackendSession()
  if (!session) return
  const body = updateBody(fields)
  if (Object.keys(body).length === 0) return // only Windows-local-only fields changed
  const external = getAbortSignal()
  try {
    const res = await apiFetch(
      'PATCH',
      `/v1/action-items/${encodeURIComponent(backendId)}`,
      body,
      external
    )
    if (!res.ok) throw new HttpError(res.status)
    const item = (await res.json()) as BackendActionItem
    if (getSessionEpoch() !== epoch) return
    syncTaskActionItems([mapBackendItem(item, Date.now())], { now: Date.now(), isTombstoned })
    broadcastTasksChanged()
  } catch (e) {
    console.warn('[tasks] update sync failed (kept local):', errName(e))
  }
}

/** Delete a task: HARD-delete locally and evict its embeddings (FIX ii), then DELETE
 *  in the background. On FAILURE keep the local deletion (Mac behavior) — the row is
 *  already gone locally. */
export function deleteTask(backendId: string): void {
  // Tombstone BEFORE the local delete so a hydrate that races the DELETE can't
  // resurrect the row (see pendingDeletes).
  tombstoneDelete(backendId)
  const deletedIds = deleteActionItemByBackendId(backendId, 'user')
  emitDeletions(deletedIds)
  broadcastTasksChanged()
  void pushDelete(backendId, getSessionEpoch())
  // Event-driven promote (Mac TasksStore.swift:1410): a delete frees a slot — pull
  // the top staged task up. Ungated + fire-and-forget, same rationale as toggleTask.
  void promoteIfNeeded()
}

async function pushDelete(backendId: string, epoch: number): Promise<void> {
  const session = getBackendSession()
  if (!session) return // offline: tombstone holds; a later reconcile/launch resolves it
  const external = getAbortSignal()
  try {
    const res = await apiFetch(
      'DELETE',
      `/v1/action-items/${encodeURIComponent(backendId)}`,
      undefined,
      external
    )
    // 204 on success; 404 = already gone on the server — both confirm the row is
    // gone, so retire the tombstone and keep the local deletion.
    if (res.ok || res.status === 404) {
      clearTombstone(backendId)
      return
    }
    // Ambiguous (429 storm / 5xx / other 4xx): the DELETE may or may not have
    // landed. Verify against the backend before deciding, so we never leave a zombie.
    await verifyDeleteOutcome(backendId, epoch, external)
  } catch (e) {
    // Network drop / timeout — also ambiguous. Verify if the session still stands.
    console.warn('[tasks] delete request failed, verifying:', errName(e))
    if (getSessionEpoch() !== epoch) return
    await verifyDeleteOutcome(backendId, epoch, external)
  }
}

/**
 * Resolve an ambiguous delete: GET the item by id.
 *   - 404 → the delete actually stuck → keep it deleted, retire the tombstone.
 *   - 200 → it's still on the server → the delete failed → honestly RESTORE the row
 *     (reusing the normal insert path) and tell the user, so it's never a silent
 *     zombie. This overrides the engine's usual keep-local-deleted asymmetry, which
 *     only holds when the delete definitively succeeded.
 *   - anything else (e.g. still 429) → inconclusive → keep the tombstone (no
 *     resurrection); the TTL / next reconcile resolves it later.
 */
async function verifyDeleteOutcome(
  backendId: string,
  epoch: number,
  external?: AbortSignal
): Promise<void> {
  try {
    const res = await apiFetch(
      'GET',
      `/v1/action-items/${encodeURIComponent(backendId)}`,
      undefined,
      external
    )
    if (getSessionEpoch() !== epoch) return
    if (res.status === 404) {
      clearTombstone(backendId) // delete stuck after all
      return
    }
    if (res.ok) {
      const item = (await res.json()) as BackendActionItem
      if (getSessionEpoch() !== epoch) return
      // Clear FIRST so the guard doesn't block our own restore insert.
      clearTombstone(backendId)
      const now = Date.now()
      syncTaskActionItems([mapBackendItem(item, now)], { now, isTombstoned })
      broadcastTasksChanged()
      emitTaskOpFailed({ op: 'delete', message: 'Could not delete task — it has been restored.' })
      return
    }
    console.warn('[tasks] delete verify inconclusive (kept tombstone):', res.status)
  } catch (e) {
    console.warn('[tasks] delete verify failed (kept tombstone):', errName(e))
  }
}

// --- Retry unsynced creates --------------------------------------------------

/** Re-POST every unsynced local create (a create whose background POST never
 *  landed — offline at creation, or app killed before markSynced). Guarded against
 *  re-entry. Called at the start of each incomplete hydrate. */
export async function retryUnsynced(): Promise<void> {
  if (retrying) return
  const session = getBackendSession()
  if (!session) return
  retrying = true
  try {
    const epoch = getSessionEpoch()
    const external = getAbortSignal()
    const rows = getUnsyncedActionItems()
    let changed = false
    for (const row of rows) {
      if (getSessionEpoch() !== epoch) break
      try {
        const res = await apiFetch(
          'POST',
          '/v1/action-items',
          createBody({
            description: row.description,
            completed: row.completed,
            dueAt: row.dueAt,
            conversationId: row.conversationId
          }),
          external
        )
        if (!res.ok) throw new HttpError(res.status)
        const created = (await res.json()) as BackendActionItem
        if (getSessionEpoch() !== epoch) break
        if (created?.id) {
          markSyncedActionItem(row.id, created.id, Date.now())
          changed = true
        }
      } catch (e) {
        console.warn('[tasks] retryUnsynced item failed (will retry later):', errName(e))
      }
    }
    if (changed) broadcastTasksChanged()
  } finally {
    retrying = false
  }
}

// --- Public reconcile (IPC `tasks:reconcile`) --------------------------------

/** Run a throttled reconcile: page the incomplete list, sync it, and hard-delete
 *  local tasks the backend no longer has (respecting the 5-min throttle). */
export function reconcile(): Promise<void> {
  return hydrateIncomplete()
}
