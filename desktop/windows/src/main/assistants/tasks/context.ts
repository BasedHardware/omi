// The grounding behind TaskAssistant's extraction prompt: the AI user profile (a
// local read), the active-task dedup context (top-relevance + recent-active
// action items + staged tasks, three local reads merged), recently-completed
// action items (a local read), and the user's active goals (a backend read,
// cached 300s). Assembled together and rendered into the context block that the
// loop appends to buildUserPrompt's header (tasks/prompt.ts renders only the
// header + messaging reminder and delegates the context sections here).
//
// Ports Mac's `refreshContext` (TaskAssistant.swift:1383-1447) — the same merge
// (top-relevance first, then recent+staged not already in top) and the same
// per-section prompt copy (TaskAssistant.swift:911-953). Only goals are cached
// (Mac caches goals with `goalsRefreshInterval`; every other slice is re-read
// each call); Mac's interval is 300s.
//
// DEVIATION D3: Mac feeds a fourth "USER-DELETED TASKS" slice
// (getRecentDeletedTasks, TaskAssistant.swift:1445). Windows hard-deletes and has
// no `deleted=1` reader, so that slice is dropped entirely — the search_* dedup
// tools already guard against re-extracting rejected work.
//
// Every source fails open to []/null on its own error — a context block grounded
// in four slices instead of five is still a valid block; one failing read must
// not blank the whole thing or throw out of assembly. Nothing here throws.
import { net } from 'electron'
import { getAbortSignal, getBackendSession } from '../core/session'
import { getLatestProfileText } from '../aiUserProfile/service'
import {
  getAllStagedTasks,
  getLocalActionItems,
  getRecentActiveActionItems,
  getTopRelevanceActionItems
} from '../../ipc/db'

/** Mac's per-slice caps (TaskAssistant.swift:1391-1436). */
const TOP_RELEVANCE_LIMIT = 30
const RECENT_ACTIVE_LIMIT = 30
const STAGED_LIMIT = 30
const COMPLETED_LIMIT = 10

/** Mac caches goals with `goalsRefreshInterval` (300s). */
const GOALS_CACHE_TTL_MS = 300_000
const REQUEST_TIMEOUT_MS = 15_000

/** A single active/dedup task line. `id` is the action-item id used by the model
 *  for duplicate_of / refines_task; staged tasks carry id 0 (Mac's convention,
 *  TaskAssistant.swift:1405 — staged rows aren't individually referenceable). */
type ActiveTask = { id: number; description: string; priority: string | null }
type Goal = { title: string; description: string | null }

/** The assembled slices, before rendering. */
export type TaskContextData = {
  /** AI user profile text, or null when unavailable. */
  profileText: string | null
  /** Merged dedup context: top-relevance action items first, then recent-active
   *  + staged not already present by id. */
  activeTasks: ActiveTask[]
  /** Recently completed action items (description only). */
  completedTasks: { description: string }[]
  /** The user's active goals. */
  goals: Goal[]
}

let goalsCache: { at: number; goals: Goal[] } | null = null

function asArray<T>(data: unknown, key: string): T[] {
  if (Array.isArray(data)) return data as T[]
  const nested = (data as Record<string, unknown> | null)?.[key]
  return Array.isArray(nested) ? (nested as T[]) : []
}

/** Fetch active goals. Fail-open to [] on no-session, non-OK, or any error — the
 *  block degrades gracefully rather than throwing. Same transport as
 *  focus/context.ts (net.fetch + relayed session, /v1/goals/all). */
async function fetchGoals(): Promise<Goal[]> {
  const session = getBackendSession()
  if (!session) return []
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await net.fetch(`${session.apiBase}/v1/goals/all`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.token}` },
      signal: ctrl.signal
    })
    if (!res.ok) {
      // Status only — never a body. Goal titles could ride in an error echo.
      console.warn(`[tasks] context goals HTTP ${res.status}`)
      return []
    }
    const goals = asArray<{ title?: string; description?: string; is_active?: boolean }>(
      await res.json(),
      'goals'
    )
    return goals
      .filter((g) => g.is_active !== false && g.title)
      .map((g) => ({ title: g.title as string, description: g.description ?? null }))
  } catch (e) {
    console.warn('[tasks] context goals failed:', e instanceof Error ? e.name : 'Error')
    return []
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

/** Goals cached 300s; every other call within the window reuses the cache without
 *  a refetch. Only a successful read is cached — a failure retries next call
 *  rather than caching [] for 300s. */
async function loadGoals(nowMs: number): Promise<Goal[]> {
  if (goalsCache && nowMs - goalsCache.at < GOALS_CACHE_TTL_MS) return goalsCache.goals
  const goals = await fetchGoals()
  goalsCache = { at: nowMs, goals }
  return goals
}

/** Read a local slice, failing open to [] on any throw (see the module header). */
function safeRead<T>(read: () => T[]): T[] {
  try {
    return read()
  } catch {
    return []
  }
}

/** Assemble the extraction context. `now` is injected so the goals cache is
 *  testable. */
export async function loadTaskContext(now: Date = new Date()): Promise<TaskContextData> {
  // Merge order mirrors Mac (TaskAssistant.swift:1416-1418): top-relevance first,
  // then recent-active + staged that aren't already present by id. Staged carry
  // id 0, so they're never filtered out by the top-id set.
  const toActiveTask = (t: { id: number; description: string; priority: string | null }): ActiveTask => ({
    id: t.id,
    description: t.description,
    priority: t.priority
  })
  const top = safeRead(() => getTopRelevanceActionItems(TOP_RELEVANCE_LIMIT)).map(toActiveTask)
  const recentActive = safeRead(() =>
    getRecentActiveActionItems(RECENT_ACTIVE_LIMIT)
  ).map(toActiveTask)
  const staged = safeRead(() => getAllStagedTasks(STAGED_LIMIT)).map((t) => ({
    id: 0,
    description: t.description,
    priority: t.priority
  }))
  const topIds = new Set(top.map((t) => t.id))
  const activeTasks: ActiveTask[] = [
    ...top,
    ...[...recentActive, ...staged].filter((t) => !topIds.has(t.id))
  ]

  const completedTasks = safeRead(() =>
    getLocalActionItems({ completed: true, limit: COMPLETED_LIMIT })
  ).map((t) => ({ description: t.description }))

  // Profile is a local read; fail open to null.
  let profileText: string | null = null
  try {
    profileText = getLatestProfileText()
  } catch {
    profileText = null
  }

  const goals = await loadGoals(now.getTime())

  return { profileText, activeTasks, completedTasks, goals }
}

/** Render the assembled slices into the context block appended after
 *  buildUserPrompt's header — Mac's per-section copy and formatting verbatim
 *  (TaskAssistant.swift:911-953). Empty sections are omitted entirely (Mac skips
 *  a section when its array is empty). Each present section ends with a blank
 *  line, matching Mac's `prompt += "…\n"; prompt += "\n"` concatenation, so the
 *  loop appends the static capture-policy trailer directly after. */
export function buildTaskContextBlock(data: TaskContextData): string {
  let block = ''

  const profile = data.profileText?.trim()
  if (profile) {
    block += 'USER PROFILE (who this user is — use for context, not as a task source):\n'
    block += profile + '\n\n'
  }

  if (data.activeTasks.length > 0) {
    block +=
      'ACTIVE TASKS (use only for semantic duplicate/refinement evidence; never globally rank new captures):\n'
    data.activeTasks.forEach((t, i) => {
      const pri = t.priority ? ` [${t.priority}]` : ''
      block += `${i + 1}. [id:${t.id}] ${t.description}${pri}\n`
    })
    block += '\n'
  }

  if (data.completedTasks.length > 0) {
    block +=
      'RECENTLY COMPLETED TASKS (user engaged with these — this is the kind of task the user finds valuable. Extract similar types of tasks, just not exact duplicates of these specific ones):\n'
    data.completedTasks.forEach((t, i) => {
      block += `${i + 1}. ${t.description}\n`
    })
    block += '\n'
  }

  if (data.goals.length > 0) {
    block += 'ACTIVE GOALS:\n'
    data.goals.forEach((g, i) => {
      const desc = g.description?.trim() ? ` — ${g.description.trim()}` : ''
      block += `${i + 1}. ${g.title}${desc}\n`
    })
    block += '\n'
  }

  return block
}

/** Convenience for the loop: assemble + render in one call. */
export async function assembleTaskContext(now: Date = new Date()): Promise<string> {
  return buildTaskContextBlock(await loadTaskContext(now))
}

/** Test/teardown: drop the goals cache. */
export function _resetTaskContextCache(): void {
  goalsCache = null
}
