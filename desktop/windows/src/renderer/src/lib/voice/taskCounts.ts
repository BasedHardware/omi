// Overdue / due-today counts for the voice session's <about_user> card — the
// Windows equivalent of macOS TasksStore.overdueTasks.count / todaysTasks.count
// (AboutUserCard.build). Reads the local-first task store (incomplete rows) the
// Tasks page uses, then mirrors that page's due-date classification (Tasks.tsx
// `bucketOf`) rather than importing from a page.
//
// Best-effort by contract: a failed read degrades to zero counts, never throws.

import type { ActionItemRecord } from '../../../../shared/types'

export type TaskCounts = { overdue: number; dueToday: number }

export const ZERO_TASK_COUNTS: TaskCounts = { overdue: 0, dueToday: 0 }

// High ceiling so a user with many tasks isn't truncated (the list IPC defaults to
// a 50-row page); mirrors the old paginating fetch's 100×100 cap.
const TASKS_LIST_LIMIT = 10_000

function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** Pure classifier over the local rows — same due-date rule the Tasks page uses
 *  (local start-of-day comparison). Completed items are not "on the user's plate
 *  right now" and are excluded, matching the Tasks dashboard buckets. */
export function countDueBuckets(items: ActionItemRecord[], now = Date.now()): TaskCounts {
  const today = startOfDay(now)
  let overdue = 0
  let dueToday = 0
  for (const item of items) {
    if (item.completed || item.dueAt == null) continue
    const day = startOfDay(item.dueAt)
    if (day < today) overdue++
    else if (day === today) dueToday++
  }
  return { overdue, dueToday }
}

/** Overdue + due-today counts. Any failure degrades to zeros — the card must
 *  still render (macOS AboutUserCard: "never throws"). The store returns only
 *  incomplete rows, so no extra completed filter is needed. */
export async function fetchTaskCounts(): Promise<TaskCounts> {
  try {
    return countDueBuckets(await window.omi.tasksListIncomplete({ limit: TASKS_LIST_LIMIT }))
  } catch {
    return ZERO_TASK_COUNTS
  }
}
