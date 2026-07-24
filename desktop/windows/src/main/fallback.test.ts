import { describe, it, expect, vi, afterEach } from 'vitest'
import { recordFallback, bucketComponent, bucketReason } from './fallback'

/**
 * The Windows main process had no shared fallback emitter, so fail-open branches each
 * logged their own ad-hoc string and ops could not aggregate them (#10240). These pin
 * the field contract from docs/agents/fallback-telemetry.md: one fixed-field record,
 * closed vocabularies, and telemetry that can never break the path it reports on.
 */

afterEach(() => vi.restoreAllMocks())

function emitted(): Record<string, unknown> {
  const warn = console.warn as unknown as { mock: { calls: unknown[][] } }
  const call = warn.mock.calls.at(-1)
  expect(call?.[0]).toBe('omi_fallback_event')
  return call?.[1] as Record<string, unknown>
}

describe('recordFallback', () => {
  it('emits one fixed-field record under a stable event name', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    recordFallback({
      component: 'rewind_embedding',
      from: 'semantic_search',
      to: 'keyword_search',
      reason: 'timeout',
      outcome: 'degraded'
    })

    expect(emitted()).toMatchObject({
      event: 'fallback',
      component: 'rewind_embedding',
      from: 'semantic_search',
      to: 'keyword_search',
      reason: 'timeout',
      outcome: 'degraded'
    })
  })

  it('buckets unknown components and reasons instead of opening new labels', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    recordFallback({ component: 'not_a_component', reason: 'not_a_reason', outcome: 'exhausted' })

    expect(emitted()).toMatchObject({ component: 'other', reason: 'other', outcome: 'exhausted' })
  })

  it('defaults absent from/to to none rather than undefined', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    recordFallback({ component: 'ai_profile', reason: 'policy', outcome: 'degraded' })

    expect(emitted()).toMatchObject({ from: 'none', to: 'none' })
  })

  it('omits detail when empty and includes it when present', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    recordFallback({ component: 'ai_profile', reason: 'policy', outcome: 'degraded' })
    expect(emitted()).not.toHaveProperty('detail')

    recordFallback({
      component: 'ai_profile',
      reason: 'policy',
      outcome: 'degraded',
      detail: { batchSize: 3 }
    })
    expect(emitted()).toMatchObject({ detail: { batchSize: 3 } })
  })

  it('never throws, so telemetry cannot break the fallback path it reports on', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {
      throw new Error('logging exploded')
    })

    expect(() =>
      recordFallback({
        component: 'ptt_audio_mute',
        reason: 'config_incomplete',
        outcome: 'degraded'
      })
    ).not.toThrow()
  })
})

describe('bucketing', () => {
  it('normalises case and whitespace before matching the closed set', () => {
    expect(bucketComponent('  AI_Profile ')).toBe('ai_profile')
    expect(bucketReason('  TIMEOUT ')).toBe('timeout')
  })

  it('falls back to other for empty or unknown values', () => {
    expect(bucketComponent('')).toBe('other')
    expect(bucketComponent(undefined)).toBe('other')
    expect(bucketReason('')).toBe('other')
  })
})
