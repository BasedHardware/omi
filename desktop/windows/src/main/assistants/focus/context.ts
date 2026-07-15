// The grounding data behind Focus's context block: the AI profile (a local
// read) plus goals / tasks / core-memories (backend reads), fetched together and
// cached 120s so a steady 3s analysis tick doesn't hammer the API five times a
// minute.
//
// Same transport as aiUserProfile/service.ts (net.fetch + relayed session).
// Each source degrades to [] on its own failure — a focus verdict grounded in
// four sources instead of five is still a verdict; one failing source must not
// blank the whole block. Nothing here throws.
import { net } from 'electron'
import { getAbortSignal, getBackendSession } from '../core/session'
import { getLatestProfileText } from '../aiUserProfile/service'
import { MAX_GOALS, MAX_MEMORIES, MAX_TASKS, type FocusContextData } from './prompt'

const REQUEST_TIMEOUT_MS = 15_000
const CACHE_TTL_MS = 120_000

type Goal = { title: string; description?: string | null }
type Task = { description: string; priority?: string | null }

let cache: { at: number; goals: Goal[]; tasks: Task[]; memories: string[] } | null = null

async function authedGet<T>(path: string, pick: (data: unknown) => T, fallback: T): Promise<T> {
  const session = getBackendSession()
  if (!session) return fallback
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await net.fetch(`${session.apiBase}${path}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.token}` },
      signal: ctrl.signal
    })
    if (!res.ok) {
      // Status only — never a body. Titles/PII could ride in an error echo.
      console.warn(`[focus] context source ${path} HTTP ${res.status}`)
      return fallback
    }
    return pick(await res.json())
  } catch (e) {
    console.warn(`[focus] context source ${path} failed:`, e instanceof Error ? e.name : 'Error')
    return fallback
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

function asArray<T>(data: unknown, key: string): T[] {
  if (Array.isArray(data)) return data as T[]
  const nested = (data as Record<string, unknown> | null)?.[key]
  return Array.isArray(nested) ? (nested as T[]) : []
}

async function fetchGoals(): Promise<Goal[]> {
  return authedGet(
    '/v1/goals/all',
    (data) => {
      const goals = asArray<{ title?: string; description?: string; is_active?: boolean }>(
        data,
        'goals'
      )
      return goals
        .filter((g) => g.is_active !== false && g.title)
        .slice(0, MAX_GOALS)
        .map((g) => ({ title: g.title as string, description: g.description ?? null }))
    },
    []
  )
}

async function fetchTasks(): Promise<Task[]> {
  return authedGet(
    '/v1/action-items?limit=50&offset=0',
    (data) => {
      // Windows ActionItemResponse has no `priority` field (Mac does); it comes
      // back undefined and the prompt falls back to "medium".
      const items = asArray<{ description?: string; completed?: boolean; priority?: string }>(
        data,
        'action_items'
      )
      return items
        .filter((t) => t.completed !== true && t.description)
        .slice(0, MAX_TASKS)
        .map((t) => ({ description: t.description as string, priority: t.priority ?? null }))
    },
    []
  )
}

async function fetchCoreMemories(): Promise<string[]> {
  return authedGet(
    '/v3/memories?limit=100&offset=0',
    (data) => {
      const items = asArray<{ content?: string; category?: string }>(data, 'memories')
      return items
        .filter((m) => m.category === 'core' && m.content)
        .slice(0, MAX_MEMORIES)
        .map((m) => (m.content as string).trim())
        .filter((s) => s.length > 0)
    },
    []
  )
}

/** Assemble the context data. Cached 120s; the clock is `now`'s Date. */
export async function loadFocusContext(now: Date = new Date()): Promise<FocusContextData> {
  const nowMs = now.getTime()
  if (!cache || nowMs - cache.at >= CACHE_TTL_MS) {
    const [goals, tasks, memories] = await Promise.all([
      fetchGoals(),
      fetchTasks(),
      fetchCoreMemories()
    ])
    cache = { at: nowMs, goals, tasks, memories }
  }
  return {
    // Read fresh every time — it's a local read, and the profile can change
    // under us (a background regeneration) between the 120s source refreshes.
    profileText: getLatestProfileText(),
    goals: cache.goals,
    tasks: cache.tasks,
    memories: cache.memories,
    now
  }
}

/** Test/teardown: drop the cache. */
export function _resetFocusContextCache(): void {
  cache = null
}
