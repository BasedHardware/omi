import { describe, it, expect, vi } from 'vitest'

vi.mock('../apiClient', () => ({
  desktopApi: { post: vi.fn() }
}))

import { classifyMintFailure, mintRealtimeToken } from './tokenMint'
import { desktopApi } from '../apiClient'

describe('mintRealtimeToken — request shape', () => {
  it('mints with __sessionPreserving so an eager-warm 401 never forces reauth', async () => {
    vi.mocked(desktopApi.post).mockResolvedValue({ data: { provider: 'openai', token: 'ek_x' } })
    await mintRealtimeToken('openai')
    expect(desktopApi.post).toHaveBeenCalledWith(
      '/v2/realtime/session',
      { provider: 'openai' },
      expect.objectContaining({ __sessionPreserving: true })
    )
  })
})

describe('classifyMintFailure', () => {
  it('401 → sign-in required, no retry, no fallback', () => {
    const f = classifyMintFailure(401, { error: 'missing_token' })
    expect(f.retryable).toBe(false)
    expect(f.tryOtherProvider).toBe(false)
    expect(f.message).toMatch(/sign in/i)
  })

  it('402 trial_expired → paywall message, no fallback', () => {
    const f = classifyMintFailure(402, { error: 'trial_expired' })
    expect(f.retryable).toBe(false)
    expect(f.tryOtherProvider).toBe(false)
    expect(f.message).toMatch(/trial/i)
  })

  it('provider_not_configured (503) → try the other provider', () => {
    const f = classifyMintFailure(503, {
      error: 'Gemini realtime is not configured',
      reason: 'provider_not_configured',
      retryable: true
    })
    expect(f.tryOtherProvider).toBe(true)
    expect(f.retryable).toBe(true)
  })

  it('provider quota (429) → fall back to the other lane', () => {
    const f = classifyMintFailure(429, {
      error: 'quota exhausted',
      reason: 'provider_quota_exceeded',
      retryable: true
    })
    expect(f.tryOtherProvider).toBe(true)
  })

  it('network failure (no response) → retryable, no provider fallback', () => {
    const f = classifyMintFailure(undefined, undefined)
    expect(f.retryable).toBe(true)
    expect(f.tryOtherProvider).toBe(false)
  })

  it('bad_provider (400) → not retryable, no fallback', () => {
    const f = classifyMintFailure(400, {
      error: 'provider must be "openai" or "gemini"',
      reason: 'bad_provider',
      retryable: false
    })
    expect(f.retryable).toBe(false)
    expect(f.tryOtherProvider).toBe(false)
  })
})
