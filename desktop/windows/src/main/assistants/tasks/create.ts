// The TaskAssistant's staged-task WRITE path: the save → sync → embed → promote
// lifecycle for one extracted task (spec §5 / §5b), plus the two staged-task REST
// calls that `taskSyncEngine.ts` lacks. A faithful port of Mac's
// `TaskAssistant.saveTaskToSQLite` + `syncTaskToBackend` (TaskAssistant.swift:420–546)
// and `TaskPromotionService.promoteIfNeeded` (TaskPromotionService.swift:59–137).
//
// Two writes per extracted task, exactly like Mac:
//   1. a local `staged_tasks` row (source of truth; born unsynced), then
//   2. `POST /v1/staged-tasks` → markSynced on success. A sync failure is
//      fail-open: the row stays unsynced (a later hydrate/retry re-POSTs) and is
//      never reverted. Then the title is embedded, and `promoteIfNeeded` may
//      promote the top staged task into `action_items`.
//
// SAFETY — the epoch guard (core/session.ts), mirrored from `taskSyncEngine`'s
// `pushCreate`: a task extracted under session A must never be written after A
// signs out and B signs in. The caller pins `getSessionEpoch()` BEFORE the (long)
// Gemini extraction; here it is re-checked before every local write, with NO
// await between the check and the write, so a mid-flight sign-out drops the result
// rather than writing a departed user's task into the next user's DB.
//
// Two staged-task REST calls live here because `taskSyncEngine.ts` only speaks the
// `/v1/action-items` surface — it has no `/v1/staged-tasks` create nor
// `/v1/staged-tasks/promote`. The `net.fetch` + Bearer + epoch-guard shape is
// copied verbatim from that engine's `pushCreate` (contained blast radius; the
// engine is intentionally untouched).
import { BrowserWindow, net } from 'electron'
import { insertLocalStagedTask, markSyncedStagedTask, syncTaskActionItems } from '../../ipc/db'
import { generateEmbeddingForTask } from '../../tasks/taskEmbeddingService'
import {
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  type BackendSession
} from '../core/session'
import type { RewindFrame, SyncActionItem } from '../../../shared/types'
import type { ExtractedTask } from './models'

// --- Tunables ---------------------------------------------------------------
const REQUEST_TIMEOUT_MS = 15_000
// Mac `TaskAssistantSettings.defaultMinConfidence` (TaskAssistantSettings.swift:113).
const DEFAULT_MIN_CONFIDENCE = 0.75
// Mac `TaskPromotionService.promotionDebounceInterval` (TaskPromotionService.swift:10).
const PROMOTION_DEBOUNCE_MS = 30_000

/** The per-result extraction context the loop reads separately from the task
 *  (`context_summary` / `current_activity` route to the extraction RESULT, not the
 *  `ExtractedTask` — see models.ts). Both ride into the local row + backend
 *  metadata. Empty strings when the caller has no context (Mac sends ""). */
export type TaskExtractionContext = {
  contextSummary: string
  currentActivity: string
}

const EMPTY_CONTEXT: TaskExtractionContext = { contextSummary: '', currentActivity: '' }

// --- HTTP helpers (mirrored from taskSyncEngine.ts) --------------------------

class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`)
    this.name = 'HttpError'
  }
}

/** name/status only — never a raw body (repo logging-security rule): a JSON parse
 *  error can echo a fragment of a user-data response. */
function errName(e: unknown): string {
  return e instanceof Error ? e.name : 'Error'
}

function toEpochMs(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  return Number.isNaN(t) ? null : t
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
// as taskSyncEngine.apiFetch. `body` is JSON-encoded when present.
async function apiFetch(
  session: BackendSession,
  method: string,
  path: string,
  body: unknown,
  external?: AbortSignal
): Promise<Response> {
  return withTimeout(
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
}

/** Tell every window the local task store changed, so the renderer re-fetches.
 *  Same event the sync engine emits (`tasks:changed`). */
function broadcastTasksChanged(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('tasks:changed')
  }
}

// --- Due-date + metadata builders (Mac parity) -------------------------------

/** Mac `parseDueDate(from:)` (TaskAssistant.swift:74–): "" / null → null; parse an
 *  ISO8601 or `yyyy-MM-dd` deadline to epoch-ms; REJECT a date before the start of
 *  today (a past due date is dropped, not stored). */
function parseDueDate(inferredDeadline: string | null): number | null {
  if (!inferredDeadline || inferredDeadline.trim().length === 0) return null
  const t = Date.parse(inferredDeadline)
  if (Number.isNaN(t)) return null
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  if (t < startOfToday.getTime()) return null
  return t
}

function firstTag(tags: string[]): string | null {
  return tags.length > 0 ? tags[0] : null
}

/** Local `staged_tasks.metadata_json` dict — Mac `saveTaskToSQLite` (TA:427–441).
 *  The bracketed keys are conditional (present only when non-empty), exactly as
 *  Mac appends them. */
function buildLocalMetadata(
  task: ExtractedTask,
  context: TaskExtractionContext,
  frame: RewindFrame,
  primaryTag: string | null
): Record<string, unknown> {
  const md: Record<string, unknown> = {
    tags: task.tags,
    context_summary: context.contextSummary,
    source_category: task.sourceCategory,
    source_subcategory: task.sourceSubcategory
  }
  if (primaryTag) md.category = primaryTag
  if (task.inferredDeadline) md.inferred_deadline = task.inferredDeadline
  if (frame.windowTitle) md.window_title = frame.windowTitle
  return md
}

/** Backend POST `metadata` dict — Mac `syncTaskToBackend` (TA:497–517). Carries
 *  the fields that are NOT top-level backend columns (source_app, confidence, tags,
 *  window_title, …), so they survive inside the opaque `metadata` string. */
function buildBackendMetadata(
  task: ExtractedTask,
  context: TaskExtractionContext,
  frame: RewindFrame,
  primaryTag: string | null
): Record<string, unknown> {
  const md: Record<string, unknown> = {
    source_app: task.sourceApp,
    confidence: task.confidence,
    context_summary: context.contextSummary,
    current_activity: context.currentActivity,
    tags: task.tags,
    source_category: task.sourceCategory,
    source_subcategory: task.sourceSubcategory
  }
  if (primaryTag) md.category = primaryTag
  if (task.description) md.reasoning = task.description
  if (task.inferredDeadline) md.inferred_deadline = task.inferredDeadline
  if (frame.windowTitle) md.window_title = frame.windowTitle
  return md
}

/** The exact `POST /v1/staged-tasks` body (backend `CreateStagedTaskRequest`,
 *  routers/staged_tasks.py:25–33). `due_at` is ISO or null; `metadata` is the
 *  JSON-stringified dict; `relevance_score` is null (unscored — screenshot path). */
function buildStagedTaskBody(
  task: ExtractedTask,
  context: TaskExtractionContext,
  frame: RewindFrame,
  dueAtMs: number | null,
  primaryTag: string | null
): Record<string, unknown> {
  return {
    description: task.title,
    due_at: dueAtMs != null ? new Date(dueAtMs).toISOString() : null,
    source: 'screenshot',
    priority: task.priority,
    category: primaryTag,
    metadata: JSON.stringify(buildBackendMetadata(task, context, frame, primaryTag)),
    relevance_score: null
  }
}

// --- The staged-task lifecycle (spec §5) -------------------------------------

/**
 * Save one extracted task through the full lifecycle: confidence gate → local
 * staged row → `POST /v1/staged-tasks` → markSynced → embed title →
 * `promoteIfNeeded`. Resolves after the (best-effort) promote; a backend failure
 * anywhere past the local insert leaves the row unsynced for a later retry and
 * never throws out.
 *
 * `epoch` is `getSessionEpoch()` pinned by the caller BEFORE the Gemini extraction
 * (Memory/sync-engine discipline). `context` carries the extraction result's
 * `context_summary` / `current_activity` (they live on the RESULT, not the task).
 * `minConfidence` defaults to Mac's 0.75 — the caller may pass the user setting.
 */
export async function createStagedTaskFromExtraction(
  task: ExtractedTask,
  frame: RewindFrame,
  epoch: number,
  context: TaskExtractionContext = EMPTY_CONTEXT,
  minConfidence: number = DEFAULT_MIN_CONFIDENCE
): Promise<void> {
  // §5 step 1 — confidence gate (Mac gates in processFrame before save). Below the
  // threshold is filtered with no write of any kind.
  if (task.confidence < minConfidence) return

  // Epoch guard before the local write: drop a task whose session already departed.
  if (getSessionEpoch() !== epoch) return

  const now = Date.now()
  const primaryTag = firstTag(task.tags)
  const dueAtMs = parseDueDate(task.inferredDeadline)

  // §5 step 2 — the local unsynced staged row (backend_synced forced 0 by the
  // storage fn). `source` is 'screenshot' for the local row AND the POST (D6:
  // Windows drops Mac's `candidate_outbox`). `relevance_score` null → unscored, so
  // the plain insert, not the score-shifting one.
  const rec = insertLocalStagedTask({
    description: task.title,
    source: 'screenshot',
    priority: task.priority,
    category: primaryTag,
    tags: task.tags,
    dueAt: dueAtMs,
    screenshotId: frame.id ?? null,
    confidence: task.confidence,
    sourceApp: task.sourceApp,
    windowTitle: frame.windowTitle || null,
    contextSummary: context.contextSummary,
    currentActivity: context.currentActivity,
    metadataJson: JSON.stringify(buildLocalMetadata(task, context, frame, primaryTag)),
    relevanceScore: null,
    backendSynced: false,
    createdAt: now,
    updatedAt: now
  })

  // §5 steps 3–6 — POST → markSynced → embed → promote.
  await syncStagedTask(rec.id, task, frame, context, dueAtMs, primaryTag, epoch)
}

/** §5 steps 3–6. POST the staged task; on success stamp the local row synced, embed
 *  the title, and run `promoteIfNeeded`. A failure keeps the local row unsynced
 *  (fail-open) — never reverted, never thrown. */
async function syncStagedTask(
  localId: number,
  task: ExtractedTask,
  frame: RewindFrame,
  context: TaskExtractionContext,
  dueAtMs: number | null,
  primaryTag: string | null,
  epoch: number
): Promise<void> {
  const session = getBackendSession()
  if (!session) return // stays unsynced — a later hydrate/retry re-POSTs it
  const external = getAbortSignal()
  try {
    const res = await apiFetch(
      session,
      'POST',
      '/v1/staged-tasks',
      buildStagedTaskBody(task, context, frame, dueAtMs, primaryTag),
      external
    )
    if (!res.ok) throw new HttpError(res.status)
    const created = (await res.json()) as { id?: string }
    // Epoch guard #2: the POST ran across an await; a sign-out mid-request means
    // this row belongs to a departed session — drop the markSynced. No await
    // between this check and the write.
    if (getSessionEpoch() !== epoch) return
    if (!created?.id) return
    markSyncedStagedTask(localId, created.id, Date.now())
  } catch (e) {
    console.warn('[tasks] staged create sync failed (kept local, will retry):', errName(e))
    return
  }

  // §5 step 5 — embed the TITLE (best-effort; the embed service is epoch-guarded
  // internally and never throws). Keyed by the LOCAL row id.
  if (getSessionEpoch() !== epoch) return
  await generateEmbeddingForTask('staged_task', localId, task.title)

  // §5 step 6 / §5b — try to promote the top staged task now, so the user sees it
  // in action_items within seconds instead of waiting for a safety-net tick.
  if (getSessionEpoch() !== epoch) return
  await promoteIfNeeded()
}

// --- Promotion (spec §5b — TaskPromotionService.swift:59–137) ----------------

// Programmatic promotion, no AI: the promote/skip decision is entirely server-side
// (`POST /v1/staged-tasks/promote`); the client only reflects the returned
// `promoted_task` into the local `action_items` store.
let promotionInFlight = false
// Mac `lastPromotedAt` (distantPast). Updated ONLY on a successful promote, so the
// 30s debounce is measured from the last real promotion (a promoted:false trigger
// does not arm the debounce).
let lastPromotedAt = 0

/** The backend `promoted_task` (an action_item document = `ActionItemResponse`).
 *  Opaque dict on the wire; we map the fields the local store needs. */
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

/** Map a promoted backend action_item → the storage `SyncActionItem`. `fromStaged`
 *  marks its origin; `now` fills a missing created_at so `createdAt` is always set. */
function mapPromotedTask(item: BackendActionItem, now: number): SyncActionItem {
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
    fromStaged: true,
    createdAt,
    updatedAt
  }
}

/**
 * Promote the top staged task into `action_items` (spec §5b). 30s debounce (unless
 * `bypassDebounce`, for the safety-net timer), at most one promotion per trigger,
 * a single re-entrancy guard. On `promoted:true` the returned action_item is
 * reflected locally via `syncTaskActionItems` (insert-or-adopt by backend_id +
 * marks synced, matching Mac's local insert of `ActionItemRecord.from(promotedTask)`)
 * and the renderer is told. On `promoted:false` it stops (cap reached / none left).
 *
 * NOTE (spec §5b / Mac): promotion does NOT delete the local staged row here — Mac
 * inserts the action_item only; the staged row is reconciled away on the next
 * staged hydrate. The backend `promote` response carries no consumed-staged id to
 * delete by, so a local staged delete is not attempted.
 */
export async function promoteIfNeeded(opts?: { bypassDebounce?: boolean }): Promise<void> {
  if (promotionInFlight) return
  const bypass = opts?.bypassDebounce === true
  if (!bypass && Date.now() - lastPromotedAt < PROMOTION_DEBOUNCE_MS) return

  promotionInFlight = true
  try {
    const session = getBackendSession()
    if (!session) return
    const epoch = getSessionEpoch()
    const external = getAbortSignal()
    try {
      const res = await apiFetch(session, 'POST', '/v1/staged-tasks/promote', undefined, external)
      if (!res.ok) throw new HttpError(res.status)
      const body = (await res.json()) as {
        promoted?: boolean
        reason?: string | null
        promoted_task?: BackendActionItem | null
      }
      // Epoch guard: the promote ran across an await — never write into a departed
      // session's DB.
      if (getSessionEpoch() !== epoch) return
      if (body.promoted === true && body.promoted_task) {
        lastPromotedAt = Date.now()
        const at = Date.now()
        syncTaskActionItems([mapPromotedTask(body.promoted_task, at)], { now: at })
        broadcastTasksChanged()
      }
    } catch (e) {
      console.warn('[tasks] promote failed:', errName(e))
    }
  } finally {
    promotionInFlight = false
  }
}

/** Reset the module-level promotion debounce/lock. Test-only seam so a suite can
 *  exercise the debounce deterministically without a shared-state carryover. */
export function __resetPromotionStateForTests(): void {
  promotionInFlight = false
  lastPromotedAt = 0
}
