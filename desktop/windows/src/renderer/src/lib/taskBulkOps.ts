import type { ActionItemRecord } from '../../../shared/types'

// Bulk mutations over a selection (mac parity: TaskBulkOperationCoordinator).
// Each operation fans out the SAME thin per-task IPC the single-row actions use —
// main still owns optimism and revert-on-failure per row — with a small
// concurrency cap so a 200-task "complete all" doesn't fire 200 simultaneous
// invokes, and a per-task failure ledger so one rejected row never aborts the
// rest. Unsynced rows (backendId null) are skipped and reported, mirroring the
// single-row gate.

export type BulkTaskOps = {
  toggle: (args: { backendId: string; completed: boolean }) => Promise<void>
  update: (args: {
    backendId: string
    fields: { dueAt?: number | null; clearDueAt?: boolean; priority?: string }
  }) => Promise<void>
  del: (args: { backendId: string }) => Promise<void>
}

export type BulkFailure = { task: ActionItemRecord; error: unknown }

export type BulkResult = {
  done: number
  skippedUnsynced: number
  failures: BulkFailure[]
}

const BULK_CONCURRENCY = 4

async function runBulk(
  tasks: readonly ActionItemRecord[],
  op: (task: ActionItemRecord, backendId: string) => Promise<void>
): Promise<BulkResult> {
  const result: BulkResult = { done: 0, skippedUnsynced: 0, failures: [] }
  const queue = [...tasks]

  const worker = async (): Promise<void> => {
    for (;;) {
      const task = queue.shift()
      if (!task) return
      if (!task.backendId) {
        result.skippedUnsynced += 1
        continue
      }
      try {
        await op(task, task.backendId)
        result.done += 1
      } catch (error) {
        result.failures.push({ task, error })
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(BULK_CONCURRENCY, Math.max(queue.length, 1)) }, worker)
  )
  return result
}

function defaultOps(): BulkTaskOps {
  return {
    toggle: window.omi.tasksToggle,
    update: window.omi.tasksUpdate,
    del: window.omi.tasksDelete
  }
}

export async function bulkSetCompleted(
  tasks: readonly ActionItemRecord[],
  completed: boolean,
  ops: BulkTaskOps = defaultOps()
): Promise<BulkResult> {
  // Rows already in the target state are a no-op success, not an IPC call.
  const changing = tasks.filter((t) => t.completed !== completed)
  const unchanged = tasks.length - changing.length
  const result = await runBulk(changing, (_t, backendId) => ops.toggle({ backendId, completed }))
  result.done += unchanged
  return result
}

export async function bulkDelete(
  tasks: readonly ActionItemRecord[],
  ops: BulkTaskOps = defaultOps()
): Promise<BulkResult> {
  return runBulk(tasks, (_t, backendId) => ops.del({ backendId }))
}

export async function bulkReschedule(
  tasks: readonly ActionItemRecord[],
  dueAt: number | null,
  ops: BulkTaskOps = defaultOps()
): Promise<BulkResult> {
  return runBulk(tasks, (_t, backendId) =>
    ops.update({ backendId, fields: dueAt != null ? { dueAt } : { clearDueAt: true } })
  )
}

export async function bulkSetPriority(
  tasks: readonly ActionItemRecord[],
  priority: 'high' | 'medium' | 'low',
  ops: BulkTaskOps = defaultOps()
): Promise<BulkResult> {
  return runBulk(tasks, (_t, backendId) => ops.update({ backendId, fields: { priority } }))
}

/** One toast-ready sentence for a finished bulk op. */
export function describeBulkResult(verb: string, result: BulkResult): string {
  const parts: string[] = [`${verb} ${result.done} ${result.done === 1 ? 'task' : 'tasks'}`]
  if (result.failures.length > 0) parts.push(`${result.failures.length} failed`)
  if (result.skippedUnsynced > 0) parts.push(`${result.skippedUnsynced} still syncing`)
  return parts.join(' · ')
}
