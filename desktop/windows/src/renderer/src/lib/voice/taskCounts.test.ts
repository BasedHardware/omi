import { describe, it, expect, vi, beforeEach } from 'vitest'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('../apiClient', () => ({ omiApi: { get } }))

import { countDueBuckets, fetchTaskCounts } from './taskCounts'
import type { ActionItemResponse } from '../omiApi.generated'

const item = (over: Partial<ActionItemResponse>): ActionItemResponse =>
  ({ id: 'x', description: 'd', completed: false, ...over }) as ActionItemResponse

// Block body, not an expression: a beforeEach that RETURNS the mock (mockReset's
// return value) makes vitest treat it as a teardown callback and call it — which
// re-invokes the mock and orphans its rejected promise.
beforeEach(() => {
  get.mockReset()
})

describe('countDueBuckets', () => {
  const now = new Date('2026-07-14T15:00:00Z').getTime()
  const day = 86_400_000

  it('counts overdue and due-today, ignoring completed, undated, and future items', () => {
    expect(
      countDueBuckets(
        [
          item({ due_at: new Date(now - 3 * day).toISOString() }),
          item({ due_at: new Date(now - day).toISOString() }),
          item({ due_at: new Date(now).toISOString() }),
          item({ due_at: new Date(now + day).toISOString() }),
          item({ due_at: null }),
          item({ due_at: new Date(now - day).toISOString(), completed: true }),
          item({ due_at: 'not-a-date' })
        ],
        now
      )
    ).toEqual({ overdue: 2, dueToday: 1 })
  })
})

describe('fetchTaskCounts', () => {
  it('degrades to zeros when the endpoint fails (never throws)', async () => {
    get.mockImplementation(() => Promise.reject(new Error('500')))
    expect(await fetchTaskCounts()).toEqual({ overdue: 0, dueToday: 0 })
  })

  it('pages through has_more', async () => {
    const page = (n: number, hasMore: boolean) => ({
      data: {
        action_items: Array.from({ length: n }, (_, i) =>
          item({ id: `p${i}`, due_at: '2000-01-01T00:00:00Z' })
        ),
        has_more: hasMore
      }
    })
    get.mockResolvedValueOnce(page(100, true)).mockResolvedValueOnce(page(5, false))
    await expect(fetchTaskCounts()).resolves.toEqual({ overdue: 105, dueToday: 0 })
    expect(get).toHaveBeenCalledTimes(2)
  })
})
