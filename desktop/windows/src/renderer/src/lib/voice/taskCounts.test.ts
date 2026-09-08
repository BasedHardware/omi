// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { countDueBuckets, fetchTaskCounts } from './taskCounts'
import type { ActionItemRecord } from '../../../../shared/types'

// Minimal ActionItemRecord factory — only the fields the classifier reads
// (completed, dueAt) matter; the rest are filled with inert defaults.
const item = (over: Partial<ActionItemRecord>): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'x',
    backendSynced: true,
    description: 'd',
    completed: false,
    deleted: false,
    dueAt: null,
    tags: [],
    createdAt: 0,
    updatedAt: 0,
    ...over
  }) as ActionItemRecord

const tasksListIncomplete = vi.fn()

beforeEach(() => {
  tasksListIncomplete.mockReset()
  ;(window as unknown as { omi: unknown }).omi = { tasksListIncomplete }
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('countDueBuckets', () => {
  const now = new Date('2026-07-14T15:00:00Z').getTime()
  const day = 86_400_000

  it('counts overdue and due-today, ignoring completed, undated, and future items', () => {
    expect(
      countDueBuckets(
        [
          item({ dueAt: now - 3 * day }),
          item({ dueAt: now - day }),
          item({ dueAt: now }),
          item({ dueAt: now + day }),
          item({ dueAt: null }),
          item({ dueAt: now - day, completed: true })
        ],
        now
      )
    ).toEqual({ overdue: 2, dueToday: 1 })
  })
})

describe('fetchTaskCounts', () => {
  it('degrades to zeros when the read fails (never throws)', async () => {
    tasksListIncomplete.mockRejectedValue(new Error('boom'))
    expect(await fetchTaskCounts()).toEqual({ overdue: 0, dueToday: 0 })
  })

  it('classifies the incomplete rows the store returns', async () => {
    const past = new Date('2000-01-01T00:00:00Z').getTime()
    tasksListIncomplete.mockResolvedValue(
      Array.from({ length: 105 }, (_, i) => item({ id: i, dueAt: past }))
    )
    await expect(fetchTaskCounts()).resolves.toEqual({ overdue: 105, dueToday: 0 })
    expect(tasksListIncomplete).toHaveBeenCalledTimes(1)
  })
})
