import { describe, it, expect } from 'vitest'
import { friendlyChatError } from './chatErrorCopy'
import {
  CHAT_RATE_LIMIT_RETRIES,
  CHAT_BUSY_RETRY_INTERIM,
  chatRateLimitBackoffMs,
  chatRateLimitFallbackProps,
  isRetryableChatRateLimit
} from './chatRetry'

// The bounded 429 auto-retry policy the chat send paths apply. A rate limit is
// transient, so a typed send that 429s must back off + retry (not force the user
// to manually re-send), and ONLY a 429 qualifies — never auth/5xx/offline/model
// errors, which surface immediately as before.
describe('chatRetry — rate-limit policy', () => {
  it('retries ONLY a 429, in both wire formats — never any other failure', () => {
    // legacy_sse throws `HTTP <n>`; pi_mono/managed-cloud reads `status code <n>`.
    expect(isRetryableChatRateLimit('HTTP 429')).toBe(true)
    expect(isRetryableChatRateLimit('Request failed with status code 429')).toBe(true)

    expect(isRetryableChatRateLimit('HTTP 401')).toBe(false)
    expect(isRetryableChatRateLimit('HTTP 403')).toBe(false)
    expect(isRetryableChatRateLimit('HTTP 500')).toBe(false)
    expect(isRetryableChatRateLimit('Failed to fetch')).toBe(false)
    expect(isRetryableChatRateLimit('the model exploded')).toBe(false)
    expect(isRetryableChatRateLimit('')).toBe(false)
    expect(isRetryableChatRateLimit(null)).toBe(false)
    expect(isRetryableChatRateLimit(undefined)).toBe(false)
  })

  it('agrees with friendlyChatError: exactly the strings it retries map to the busy copy', () => {
    // Zero-drift contract — the retry predicate and the shown copy share one parse.
    const BUSY = 'Omi’s servers are busy. Try again in a moment.'
    for (const raw of ['HTTP 429', 'Request failed with status code 429']) {
      expect(isRetryableChatRateLimit(raw)).toBe(true)
      expect(friendlyChatError(raw)).toBe(BUSY)
    }
    // A retried-then-exhausted send lands on the same non-blaming copy.
    expect(friendlyChatError('HTTP 429')).not.toMatch(/too quickly/i)
  })

  it('backoff is bounded, monotonic-ish, and capped (never approaches the chat watchdog)', () => {
    // Each retry waits at least the exponential base and never exceeds cap + jitter.
    for (let attempt = 1; attempt <= 6; attempt++) {
      const ms = chatRateLimitBackoffMs(attempt)
      expect(ms).toBeGreaterThanOrEqual(Math.min(1000 * 2 ** (attempt - 1), 4000))
      expect(ms).toBeLessThanOrEqual(4000 + 300)
    }
    // Total worst-case added wait across all retries stays tiny vs the 180s watchdog.
    let worst = 0
    for (let rl = 1; rl <= CHAT_RATE_LIMIT_RETRIES; rl++) worst += 4000 + 300
    expect(worst).toBeLessThan(30_000)
  })

  it('is bounded to a small, non-zero number of retries', () => {
    expect(CHAT_RATE_LIMIT_RETRIES).toBeGreaterThanOrEqual(1)
    expect(CHAT_RATE_LIMIT_RETRIES).toBeLessThanOrEqual(3)
  })

  it('the interim line is non-blaming and consistent with the degraded notice', () => {
    expect(CHAT_BUSY_RETRY_INTERIM).toMatch(/busy/i)
    expect(CHAT_BUSY_RETRY_INTERIM).not.toMatch(/too quickly/i)
  })

  it('fallback props carry the fixed shared fields (component/from/to/reason/outcome)', () => {
    const recovered = chatRateLimitFallbackProps('recovered', 'pi_mono', 1)
    expect(recovered).toMatchObject({
      component: 'chat_send',
      from: 'none',
      to: 'none',
      reason: 'rate_limited',
      outcome: 'recovered',
      engine: 'pi_mono',
      attempts: 1
    })
    const exhausted = chatRateLimitFallbackProps('exhausted', 'legacy_sse', 2)
    expect(exhausted).toMatchObject({ outcome: 'exhausted', engine: 'legacy_sse', attempts: 2 })
  })
})
