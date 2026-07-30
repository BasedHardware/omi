import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  classifyForRateLimit,
  noteBackendStatus,
  isBackendDegraded,
  __setDegradedInternalsForTest
} from './backendDegraded'

afterEach(() => {
  __setDegradedInternalsForTest({ broadcaster: null, now: null })
  vi.restoreAllMocks()
})

describe('classifyForRateLimit', () => {
  it('maps 429 to a rate-limit hit', () => {
    expect(classifyForRateLimit(429)).toBe('hit')
  })
  it('maps any 2xx/3xx to a recovery signal', () => {
    expect(classifyForRateLimit(200)).toBe('ok')
    expect(classifyForRateLimit(204)).toBe('ok')
    expect(classifyForRateLimit(304)).toBe('ok')
  })
  it('ignores other 4xx/5xx and thrown errors (undefined)', () => {
    expect(classifyForRateLimit(400)).toBe('ignore')
    expect(classifyForRateLimit(404)).toBe('ignore')
    expect(classifyForRateLimit(500)).toBe('ignore')
    expect(classifyForRateLimit(undefined)).toBe('ignore')
  })
})

describe('noteBackendStatus → degraded signal', () => {
  it('broadcasts degraded=true exactly once after a storm, and clears on recovery', () => {
    let clock = 1_000
    const broadcasts: boolean[] = []
    __setDegradedInternalsForTest({ broadcaster: (d) => broadcasts.push(d), now: () => clock })
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    // Production rule: 5 429s across ≥2 distinct paths within 60s.
    noteBackendStatus(429, 'GET /v1/action-items')
    noteBackendStatus(429, 'GET /v1/action-items')
    noteBackendStatus(429, 'GET /v1/action-items')
    noteBackendStatus(429, 'GET /v1/action-items')
    expect(isBackendDegraded()).toBe(false) // count met but only ONE distinct path
    noteBackendStatus(429, 'DELETE /v1/action-items/:id') // 5th + 2nd path → degraded
    expect(isBackendDegraded()).toBe(true)

    noteBackendStatus(429, 'POST /v1/action-items') // still degraded, no re-broadcast
    noteBackendStatus(200, 'GET /v1/action-items') // success mid-storm: no clear (anti-flicker)
    expect(isBackendDegraded()).toBe(true)

    clock += 61_000 // storm ages out
    noteBackendStatus(200, 'GET /v1/action-items') // now a success clears it
    expect(isBackendDegraded()).toBe(false)

    expect(broadcasts).toEqual([true, false])
  })

  it('a non-429 error status never trips the signal', () => {
    __setDegradedInternalsForTest({ broadcaster: null, now: () => 0 })
    noteBackendStatus(500, 'a')
    noteBackendStatus(500, 'b')
    noteBackendStatus(500, 'c')
    expect(isBackendDegraded()).toBe(false)
  })

  it('a single endpoint 429-looping does not trip (one distinct path)', () => {
    __setDegradedInternalsForTest({ broadcaster: null, now: () => 0 })
    for (let i = 0; i < 8; i++) noteBackendStatus(429, 'GET /v1/action-items')
    expect(isBackendDegraded()).toBe(false)
  })

  it('records a structured fallback line on each transition', () => {
    let clock = 1_000
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    __setDegradedInternalsForTest({ broadcaster: () => {}, now: () => clock })

    noteBackendStatus(429, 'p1')
    noteBackendStatus(429, 'p1')
    noteBackendStatus(429, 'p2')
    noteBackendStatus(429, 'p2')
    noteBackendStatus(429, 'p3') // 5 across 3 paths → degraded
    clock += 61_000
    noteBackendStatus(200, 'p1') // → recovered

    const fallbackCalls = warn.mock.calls.filter((c) => c[0] === '[fallback]')
    expect(fallbackCalls).toHaveLength(2)
    expect(fallbackCalls[0][1]).toMatchObject({ component: 'backend_fetch', outcome: 'degraded' })
    expect(fallbackCalls[1][1]).toMatchObject({ component: 'backend_fetch', outcome: 'recovered' })
  })
})
