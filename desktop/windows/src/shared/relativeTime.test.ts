import { describe, it, expect } from 'vitest'
import { relativeTime, isSameDay } from './relativeTime'

const NOW = new Date('2026-06-05T18:00:00').getTime()

describe('relativeTime', () => {
  it('says "just now" within 5 seconds', () => {
    expect(relativeTime(NOW - 3_000, NOW)).toBe('just now')
  })

  it('reports whole seconds under a minute', () => {
    expect(relativeTime(NOW - 30_000, NOW)).toBe('30s ago')
  })

  it('rolls up to minutes at exactly 60s', () => {
    expect(relativeTime(NOW - 60_000, NOW)).toBe('1m ago')
  })

  it('reports minutes under an hour', () => {
    expect(relativeTime(NOW - 5 * 60_000, NOW)).toBe('5m ago')
  })

  it('reports hours under a day', () => {
    expect(relativeTime(NOW - 3 * 3_600_000, NOW)).toBe('3h ago')
  })

  it('reports days beyond 24h', () => {
    expect(relativeTime(NOW - 2 * 86_400_000, NOW)).toBe('2d ago')
  })
})

describe('isSameDay', () => {
  it('is true for two times on the same calendar day', () => {
    const a = new Date('2026-06-05T08:00:00').getTime()
    const b = new Date('2026-06-05T23:30:00').getTime()
    expect(isSameDay(a, b)).toBe(true)
  })

  it('is false across a day boundary', () => {
    const a = new Date('2026-06-04T23:59:00').getTime()
    const b = new Date('2026-06-05T00:01:00').getTime()
    expect(isSameDay(a, b)).toBe(false)
  })
})
