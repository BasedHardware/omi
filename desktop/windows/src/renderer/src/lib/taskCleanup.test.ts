import { describe, it, expect, vi, beforeEach } from 'vitest'

// Wire: taskCleanupPreview posts to /preview with the user's params and a
// 180-second timeout override (LLM strategies can take up to 2 minutes on
// large accounts). taskCleanupExecute posts the session_id to /execute —
// no timeout override since deletion is fast.

const postSpy = vi.fn()
vi.mock('./apiClient', () => ({
  omiApi: { post: (url: string, body: unknown, config?: unknown) => postSpy(url, body, config) }
}))

import { taskCleanupPreview, taskCleanupExecute } from './taskCleanup'

const PREVIEW_TIMEOUT_MS = 180_000

beforeEach(() => postSpy.mockReset())

describe('taskCleanupPreview', () => {
  it('posts to the preview endpoint and returns response data', async () => {
    const response = {
      session_id: 'sess-abc',
      total_candidates: 5,
      breakdown: { stale_age: 5 },
      sample: [],
      expires_in_seconds: 300
    }
    postSpy.mockResolvedValue({ data: response })

    const result = await taskCleanupPreview({ strategies: ['stale_age'], age_days: 90 })

    expect(result).toEqual(response)
    expect(postSpy).toHaveBeenCalledTimes(1)
    const [url, body] = postSpy.mock.calls[0] as [string, unknown, unknown]
    expect(url).toBe('/v1/action-items/cleanup/preview')
    expect(body).toEqual({ strategies: ['stale_age'], age_days: 90 })
  })

  it('passes a 180-second timeout override', async () => {
    postSpy.mockResolvedValue({ data: {} })

    await taskCleanupPreview({ strategies: [] })

    const [, , config] = postSpy.mock.calls[0] as [string, unknown, { timeout: number }]
    expect(config).toMatchObject({ timeout: PREVIEW_TIMEOUT_MS })
  })

  it('forwards all optional params to the backend', async () => {
    postSpy.mockResolvedValue({ data: {} })

    await taskCleanupPreview({
      strategies: ['semantic_dedup', 'llm_relevance'],
      age_days: 30,
      overdue_days: 14,
      similarity_threshold: 0.95,
      llm_confidence_threshold: 0.85
    })

    const [, body] = postSpy.mock.calls[0] as [string, unknown]
    expect(body).toEqual({
      strategies: ['semantic_dedup', 'llm_relevance'],
      age_days: 30,
      overdue_days: 14,
      similarity_threshold: 0.95,
      llm_confidence_threshold: 0.85
    })
  })
})

describe('taskCleanupExecute', () => {
  it('posts the session_id to the execute endpoint and returns response data', async () => {
    postSpy.mockResolvedValue({ data: { deleted_count: 42 } })

    const result = await taskCleanupExecute('my-session-id')

    expect(result).toEqual({ deleted_count: 42 })
    expect(postSpy).toHaveBeenCalledTimes(1)
    const [url, body] = postSpy.mock.calls[0] as [string, unknown]
    expect(url).toBe('/v1/action-items/cleanup/execute')
    expect(body).toEqual({ session_id: 'my-session-id' })
  })

  it('does not pass a custom timeout (fast operation)', async () => {
    postSpy.mockResolvedValue({ data: { deleted_count: 0 } })

    await taskCleanupExecute('sess-x')

    const call = postSpy.mock.calls[0] as [string, unknown, unknown?]
    // Third arg (config) should be absent or undefined — no timeout override
    expect(call[2]).toBeUndefined()
  })
})
