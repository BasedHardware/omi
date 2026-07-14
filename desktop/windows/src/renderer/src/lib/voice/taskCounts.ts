// Overdue / due-today counts for the voice session's <about_user> card — the
// Windows equivalent of macOS TasksStore.overdueTasks.count / todaysTasks.count
// (AboutUserCard.build). Windows has no shared tasks store: the Tasks page owns
// its own fetch + bucket logic inside the page component, so this module mirrors
// that classification (Tasks.tsx `bucketOf`) rather than importing from a page.
//
// Best-effort by contract: a failed fetch degrades to zero counts, never throws.

import { omiApi } from '../apiClient'
import type { ActionItemResponse, ActionItemsResponse } from '../omiApi.generated'

export type TaskCounts = { overdue: number; dueToday: number }

export const ZERO_TASK_COUNTS: TaskCounts = { overdue: 0, dueToday: 0 }

const PAGE_SIZE = 100

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** Pure classifier over the fetched items — same due-date rule the Tasks page
 *  uses (local start-of-day comparison). Completed items are not "on the user's
 *  plate right now" and are excluded, matching the Tasks dashboard buckets. */
export function countDueBuckets(items: ActionItemResponse[], now = Date.now()): TaskCounts {
  const today = startOfDay(now)
  let overdue = 0
  let dueToday = 0
  for (const item of items) {
    if (item.completed || !item.due_at) continue
    const due = new Date(item.due_at).getTime()
    if (Number.isNaN(due)) continue
    const day = startOfDay(due)
    if (day < today) overdue++
    else if (day === today) dueToday++
  }
  return { overdue, dueToday }
}

/** Page through /v1/action-items following `has_more` (the Tasks page's contract
 *  — a single hard `limit` silently truncates users with many items). */
async function fetchAllActionItems(pageCap = 100): Promise<ActionItemResponse[]> {
  const all: ActionItemResponse[] = []
  let offset = 0
  for (let page = 0; page < pageCap; page++) {
    const res = await omiApi.get('/v1/action-items', { params: { limit: PAGE_SIZE, offset } })
    const data = res.data as ActionItemResponse[] | ActionItemsResponse
    const batch = Array.isArray(data) ? data : (data.action_items ?? [])
    all.push(...batch)
    const hasMore = Array.isArray(data) ? batch.length === PAGE_SIZE : Boolean(data.has_more)
    if (!hasMore || batch.length === 0) break
    offset += PAGE_SIZE
  }
  return all
}

/** Overdue + due-today counts. Any failure degrades to zeros — the card must
 *  still render (macOS AboutUserCard: "never throws"). */
export async function fetchTaskCounts(): Promise<TaskCounts> {
  try {
    return countDueBuckets(await fetchAllActionItems())
  } catch {
    return ZERO_TASK_COUNTS
  }
}
