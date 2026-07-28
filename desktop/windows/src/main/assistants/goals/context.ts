// The on-device context bundle behind client-side goal generation — a faithful
// port of Mac's `GoalsAIService.fetchRichContext`
// (ProactiveAssistants/Assistants/Goals/GoalsAIService.swift). Fetches five
// sources in parallel through the shared relayed session (net.fetch + Bearer, the
// same transport aiUserProfile/service.ts uses), renders each into the exact
// block Mac feeds its prompt, and reports whether there is enough signal to
// generate at all.
//
// Every source fails open to []/null on its own error — a bundle grounded in four
// sources instead of five is still valid; one failing read must never blank the
// whole thing or throw out of assembly. The fetchers are injected so the assembly
// + rendering is unit-testable with zero network.
//
// Two deviations from Mac's table, both forced by the live backend contract and
// documented at their sites:
//  1. COMPLETED GOALS — Mac's getCompletedGoals() 404s (dead). /v1/goals/all
//     returns ONLY active goals (backend filters is_active==True), so "completed"
//     is derived by splitting that active list on Windows's progress-based
//     completion model (current >= target). Abandoned goals have no signal → None.
//  2. Task linking is NOT persisted (no backend goal_id field) — see generate.ts.
import { net } from 'electron'
import { noteBackendStatus } from '../../observability/backendDegraded'
import { getAbortSignal, getBackendSession, type BackendSession } from '../core/session'

/** Mac's per-source caps (GoalsAIService.swift:150-247). No truncation beyond these. */
const MEMORIES_LIMIT = 500
const CONVERSATIONS_LIMIT = 100
const TASKS_LIMIT = 100
const REQUEST_TIMEOUT_MS = 15_000

/** One incomplete task the model may reference by id in `linked_task_ids`. */
export type GoalContextTask = { id: string; description: string }

/** A raw active goal from /v1/goals/all, before the active/completed split. */
export type RawGoal = { title: string; targetValue: number; currentValue: number }

/** The assembled, rendered bundle. Each string list is already in Mac's block
 *  format; prompt.ts applies the empty-state fallbacks when a list is empty. */
export type GoalContextData = {
  /** "<name>: <description>", or null when the user has no persona. */
  persona: string | null
  /** Each memory's content, non-empty. */
  memories: string[]
  /** Each conversation's non-empty structured.overview. */
  conversations: string[]
  /** Incomplete action items (id preserved for linked_task_ids validation). */
  tasks: GoalContextTask[]
  /** Active-and-incomplete goals: "- <title> (<current>/<target>)". */
  activeGoals: string[]
  /** Progress-complete goals: "- <title> (achieved <current>/<target>)". */
  completedGoals: string[]
  /** Count of active-and-incomplete goals — the `<3 active` gate reads this. */
  activeGoalCount: number
}

/** The five source reads, injected so assembly is hermetic. Each fails open. */
export type GoalContextFetchers = {
  fetchMemories: () => Promise<string[]>
  fetchConversations: () => Promise<string[]>
  fetchTasks: () => Promise<GoalContextTask[]>
  fetchPersona: () => Promise<string | null>
  fetchGoals: () => Promise<RawGoal[]>
}

// --- HTTP transport (mirrors aiUserProfile/service.ts authedGet) -------------

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

/** GET `path` (relative to the Python backend base) with the relayed bearer.
 *  Returns the parsed JSON, or null on non-OK / any error — the caller's fail-open
 *  policy turns that into an empty section. Never logs a response body (it can
 *  echo the user's data); status/name only. */
async function authedJson(session: BackendSession, path: string): Promise<unknown | null> {
  const external = getAbortSignal()
  try {
    return await withTimeout(
      REQUEST_TIMEOUT_MS,
      async (signal) => {
        const res = await net.fetch(`${session.apiBase}${path}`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${session.token}` },
          signal
        })
        noteBackendStatus(res.status, `GET ${path.split('?')[0]}`) // 429-storm telemetry (observe only)
        if (!res.ok) {
          console.warn(`[goals] context GET ${path.split('?')[0]} HTTP ${res.status}`)
          return null
        }
        return await res.json()
      },
      external
    )
  } catch (e) {
    console.warn('[goals] context read failed:', e instanceof Error ? e.name : 'Error')
    return null
  }
}

function asArray<T>(data: unknown, key: string): T[] {
  if (Array.isArray(data)) return data as T[]
  const nested = (data as Record<string, unknown> | null)?.[key]
  return Array.isArray(nested) ? (nested as T[]) : []
}

// --- Real fetchers -----------------------------------------------------------

/** Build the production fetchers bound to a live session. Each read fails open. */
export function realFetchers(session: BackendSession): GoalContextFetchers {
  return {
    fetchMemories: async () => {
      const data = await authedJson(session, `/v3/memories?limit=${MEMORIES_LIMIT}&offset=0`)
      return asArray<{ content?: string }>(data, 'memories')
        .map((m) => (m.content ?? '').trim())
        .filter((s) => s.length > 0)
    },
    fetchConversations: async () => {
      const data = await authedJson(
        session,
        `/v1/conversations?limit=${CONVERSATIONS_LIMIT}&offset=0&statuses=completed`
      )
      return asArray<{ structured?: { overview?: string } }>(data, 'conversations')
        .map((c) => (c.structured?.overview ?? '').trim())
        .filter((s) => s.length > 0)
    },
    fetchTasks: async () => {
      const data = await authedJson(
        session,
        `/v1/action-items?limit=${TASKS_LIMIT}&offset=0&completed=false`
      )
      return asArray<{ id?: string; description?: string }>(data, 'action_items')
        .map((t) => ({ id: String(t.id ?? ''), description: (t.description ?? '').trim() }))
        .filter((t) => t.id.length > 0 && t.description.length > 0)
    },
    fetchPersona: async () => {
      // /v1/personas → the user's Omi-persona App (name + description), or a
      // non-OK when they have none → null → "No persona set".
      const data = await authedJson(session, '/v1/personas')
      const app = data as { name?: string; description?: string } | null
      const name = app?.name?.trim()
      if (!name) return null
      const desc = app?.description?.trim()
      return desc ? `${name}: ${desc}` : name
    },
    fetchGoals: async () => {
      const data = await authedJson(session, '/v1/goals/all')
      return asArray<{
        title?: string
        target_value?: number
        current_value?: number
        is_active?: boolean
      }>(data, 'goals')
        .filter((g) => g.is_active !== false && (g.title ?? '').trim().length > 0)
        .map((g) => ({
          title: (g.title as string).trim(),
          targetValue: typeof g.target_value === 'number' ? g.target_value : 0,
          currentValue: typeof g.current_value === 'number' ? g.current_value : 0
        }))
    }
  }
}

// --- Assembly + rendering ----------------------------------------------------

/** Render a numeric goal value. JS `String` already drops a trailing `.0`
 *  (`String(5.0) === '5'`); rounding to 2dp trims stored float noise. */
function fmtNum(n: number): string {
  return String(Math.round(n * 100) / 100)
}

/** A goal counts as complete under Windows's progress model when it has a real
 *  target and progress has reached it (mirrors the renderer's isCompleted). */
function isProgressComplete(g: RawGoal): boolean {
  return g.targetValue > 0 && g.currentValue >= g.targetValue
}

/** Assemble the bundle from the (injected) fetchers. Pure orchestration: it runs
 *  the five reads in parallel and renders the goal split; every fetcher already
 *  fails open, so this never throws. */
export async function assembleGoalContext(f: GoalContextFetchers): Promise<GoalContextData> {
  const [persona, memories, conversations, tasks, goals] = await Promise.all([
    f.fetchPersona(),
    f.fetchMemories(),
    f.fetchConversations(),
    f.fetchTasks(),
    f.fetchGoals()
  ])

  const active = goals.filter((g) => !isProgressComplete(g))
  const completed = goals.filter(isProgressComplete)

  return {
    persona,
    memories,
    conversations,
    tasks,
    activeGoals: active.map(
      (g) => `- ${g.title} (${fmtNum(g.currentValue)}/${fmtNum(g.targetValue)})`
    ),
    completedGoals: completed.map(
      (g) => `- ${g.title} (achieved ${fmtNum(g.currentValue)}/${fmtNum(g.targetValue)})`
    ),
    activeGoalCount: active.length
  }
}

/** Mac's insufficient-context guard (throws `insufficientContext` there): skip
 *  generation entirely unless there is at least one memory OR conversation OR
 *  task. Goal history alone is not enough to reason from. */
export function hasSufficientContext(data: GoalContextData): boolean {
  return data.memories.length > 0 || data.conversations.length > 0 || data.tasks.length > 0
}

/** Production entry: assemble the bundle for the current session, or null when
 *  there is no session (a soft no-op — nothing to fetch with). */
export async function fetchGoalContext(): Promise<GoalContextData | null> {
  const session = getBackendSession()
  if (!session) return null
  return assembleGoalContext(realFetchers(session))
}
