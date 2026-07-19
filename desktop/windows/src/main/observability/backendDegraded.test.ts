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

    noteBackendStatus(429)
    noteBackendStatus(429)
    expect(isBackendDegraded()).toBe(false)
    noteBackendStatus(429) // 3rd within window → degraded
    expect(isBackendDegraded()).toBe(true)

    noteBackendStatus(429) // still degraded, no re-broadcast
    noteBackendStatus(200) // success during active storm: no clear (anti-flicker)
    expect(isBackendDegraded()).toBe(true)

    clock += 21_000 // storm ages out
    noteBackendStatus(200) // now a success clears it
    expect(isBackendDegraded()).toBe(false)

    expect(broadcasts).toEqual([true, false])
  })

  it('a non-429 error status never trips the signal', () => {
    __setDegradedInternalsForTest({ broadcaster: null, now: () => 0 })
    noteBackendStatus(500)
    noteBackendStatus(500)
    noteBackendStatus(500)
    expect(isBackendDegraded()).toBe(false)
  })

  it('records a structured fallback line on each transition', () => {
    let clock = 1_000
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    __setDegradedInternalsForTest({ broadcaster: () => {}, now: () => clock })

    noteBackendStatus(429)
    noteBackendStatus(429)
    noteBackendStatus(429) // → degraded
    clock += 21_000
    noteBackendStatus(200) // → recovered

    const fallbackCalls = warn.mock.calls.filter((c) => c[0] === '[fallback]')
    expect(fallbackCalls).toHaveLength(2)
    expect(fallbackCalls[0][1]).toMatchObject({ component: 'backend_fetch', outcome: 'degraded' })
    expect(fallbackCalls[1][1]).toMatchObject({ component: 'backend_fetch', outcome: 'recovered' })
  })
})
