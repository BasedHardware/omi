import type { ActionItemRecord } from '../../../shared/types'

// Local-first read of "all the user's tasks": the main-process task store owns a
// local SQLite mirror with optimistic write-through + background sync, so this
// returns the LOCAL rows instantly (no network round-trip) and main kicks a
// background hydrate. Concatenates the incomplete + completed slices into one
// list — the same shape the Tasks page buckets over and the Hub ribbon counts.
//
// Lives here rather than in pages/Tasks.tsx because two callers share it: the
// Tasks page and the Hub's stat ribbon — one definition of "all the user's tasks".
//
// The list IPC defaults to a 50-row page; pass a high ceiling so a user with many
// tasks isn't silently truncated (mirrors the old paginating fetch's 100×100 cap).
const TASKS_LIST_LIMIT = 10_000

export async function fetchAllActionItems(): Promise<ActionItemRecord[]> {
  const [incomplete, completed] = await Promise.all([
    window.omi.tasksListIncomplete({ limit: TASKS_LIST_LIMIT }),
    window.omi.tasksListCompleted({ limit: TASKS_LIST_LIMIT })
  ])
  return [...incomplete, ...completed]
}
