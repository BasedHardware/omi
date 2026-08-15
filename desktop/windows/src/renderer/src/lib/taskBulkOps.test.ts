import { describe, it, expect, vi } from 'vitest'
import type { ActionItemRecord } from '../../../shared/types'
import {
  bulkDelete,
  bulkReschedule,
  bulkSetCompleted,
  bulkSetPriority,
  describeBulkResult,
  type BulkTaskOps
} from './taskBulkOps'

const rec = (over: Partial<ActionItemRecord>): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'b-1',
    backendSynced: true,
    description: 'task',
    completed: false,
    deleted: false,
    deletedBy: null,
    source: null,
    conversationId: null,
    priority: null,
    category: null,
    tags: [],
    dueAt: null,
    screenshotId: null,
    confidence: null,
    sourceApp: null,
    windowTitle: null,
    contextSummary: null,
    currentActivity: null,
    metadataJson: null,
    createdAt: 1,
    updatedAt: 1,
    ...over
  }) as ActionItemRecord

const opsMock = (): BulkTaskOps & {
  toggle: ReturnType<typeof vi.fn>
  update: ReturnType<typeof vi.fn>
  del: ReturnType<typeof vi.fn>
} => ({
  toggle: vi.fn().mockResolvedValue(undefined),
  update: vi.fn().mockResolvedValue(undefined),
  del: vi.fn().mockResolvedValue(undefined)
})

describe('bulkSetCompleted', () => {
  it('toggles only rows not already in the target state and counts the rest as done', async () => {
    const ops = opsMock()
    const tasks = [
      rec({ id: 1, backendId: 'a', completed: false }),
      rec({ id: 2, backendId: 'b', completed: true }),
      rec({ id: 3, backendId: 'c', completed: false })
    ]
    const result = await bulkSetCompleted(tasks, true, ops)
    expect(ops.toggle).toHaveBeenCalledTimes(2)
    expect(ops.toggle).toHaveBeenCalledWith({ backendId: 'a', completed: true })
    expect(ops.toggle).toHaveBeenCalledWith({ backendId: 'c', completed: true })
    expect(result.done).toBe(3)
    expect(result.failures).toEqual([])
  })

  it('skips unsynced rows and reports them', async () => {
    const ops = opsMock()
    const result = await bulkSetCompleted(
      [rec({ id: 1, backendId: null }), rec({ id: 2, backendId: 'b' })],
      true,
      ops
    )
    expect(ops.toggle).toHaveBeenCalledTimes(1)
    expect(result.done).toBe(1)
    expect(result.skippedUnsynced).toBe(1)
  })

  it('collects per-task failures without aborting the rest', async () => {
    const ops = opsMock()
    ops.toggle.mockImplementation(({ backendId }: { backendId: string }) =>
      backendId === 'bad' ? Promise.reject(new Error('nope')) : Promise.resolve()
    )
    const tasks = [
      rec({ id: 1, backendId: 'a' }),
      rec({ id: 2, backendId: 'bad' }),
      rec({ id: 3, backendId: 'c' })
    ]
    const result = await bulkSetCompleted(tasks, true, ops)
    expect(result.done).toBe(2)
    expect(result.failures).toHaveLength(1)
    expect(result.failures[0].task.id).toBe(2)
  })
})

describe('bulkDelete / bulkReschedule / bulkSetPriority', () => {
  it('deletes every synced row', async () => {
    const ops = opsMock()
    const result = await bulkDelete(
      [rec({ id: 1, backendId: 'a' }), rec({ id: 2, backendId: 'b' })],
      ops
    )
    expect(ops.del).toHaveBeenCalledTimes(2)
    expect(result.done).toBe(2)
  })

  it('reschedules with dueAt, and clears when null', async () => {
    const ops = opsMock()
    await bulkReschedule([rec({ id: 1, backendId: 'a' })], 1_755_000_000_000, ops)
    expect(ops.update).toHaveBeenCalledWith({
      backendId: 'a',
      fields: { dueAt: 1_755_000_000_000 }
    })
    await bulkReschedule([rec({ id: 1, backendId: 'a' })], null, ops)
    expect(ops.update).toHaveBeenCalledWith({ backendId: 'a', fields: { clearDueAt: true } })
  })

  it('sets priority on every synced row', async () => {
    const ops = opsMock()
    await bulkSetPriority(
      [rec({ id: 1, backendId: 'a' }), rec({ id: 2, backendId: 'b' })],
      'high',
      ops
    )
    expect(ops.update).toHaveBeenCalledTimes(2)
    expect(ops.update).toHaveBeenCalledWith({ backendId: 'a', fields: { priority: 'high' } })
  })

  it('handles an empty selection without touching the ops', async () => {
    const ops = opsMock()
    const result = await bulkDelete([], ops)
    expect(result).toEqual({ done: 0, skippedUnsynced: 0, failures: [] })
    expect(ops.del).not.toHaveBeenCalled()
  })
})

describe('describeBulkResult', () => {
  it('summarizes the outcome for a toast', () => {
    expect(describeBulkResult('Completed', { done: 3, skippedUnsynced: 0, failures: [] })).toBe(
      'Completed 3 tasks'
    )
    expect(describeBulkResult('Deleted', { done: 1, skippedUnsynced: 0, failures: [] })).toBe(
      'Deleted 1 task'
    )
    expect(
      describeBulkResult('Completed', {
        done: 2,
        skippedUnsynced: 1,
        failures: [{ task: rec({}), error: new Error('x') }]
      })
    ).toBe('Completed 2 tasks · 1 failed · 1 still syncing')
  })
})
