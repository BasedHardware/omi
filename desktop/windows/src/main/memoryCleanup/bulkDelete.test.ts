import { describe, it, expect } from 'vitest'
import { classifyStatus, backoffMs } from './bulkDelete'

describe('classifyStatus', () => {
  it('treats 2xx as ok', () => {
    expect(classifyStatus(200)).toBe('ok')
    expect(classifyStatus(204)).toBe('ok')
  })
  it('treats 404 as gone (idempotent success)', () => {
    expect(classifyStatus(404)).toBe('gone')
  })
  it('treats 429 and 5xx as retry', () => {
    expect(classifyStatus(429)).toBe('retry')
    expect(classifyStatus(500)).toBe('retry')
    expect(classifyStatus(503)).toBe('retry')
  })
  it('treats auth/client errors as fail', () => {
    expect(classifyStatus(401)).toBe('fail')
    expect(classifyStatus(400)).toBe('fail')
  })
})

describe('backoffMs', () => {
  it('honors a numeric Retry-After header (seconds -> ms, capped)', () => {
    expect(backoffMs(1, '2')).toBe(2000)
    expect(backoffMs(5, '120')).toBe(60_000) // capped
  })
  it('falls back to exponential backoff with jitter when no header', () => {
    expect(backoffMs(1)).toBeGreaterThanOrEqual(1000)
    expect(backoffMs(1)).toBeLessThan(1400)
    expect(backoffMs(3)).toBeGreaterThanOrEqual(4000)
    expect(backoffMs(99)).toBeLessThan(16_400) // capped at 16s + jitter
  })
  it('ignores a non-numeric Retry-After', () => {
    expect(backoffMs(1, 'soon')).toBeGreaterThanOrEqual(1000)
  })
})
