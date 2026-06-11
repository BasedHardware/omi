import { describe, it, expect } from 'vitest'
import { retentionCutoff } from './retentionSelection'

describe('retentionCutoff', () => {
  const now = 10_000_000_000 // fixed epoch ms
  it('returns now minus N days in ms', () => {
    expect(retentionCutoff(now, 7)).toBe(now - 7 * 24 * 60 * 60 * 1000)
  })
  it('treats 0 or negative retention as "keep nothing in the past" (cutoff = now)', () => {
    expect(retentionCutoff(now, 0)).toBe(now)
    expect(retentionCutoff(now, -5)).toBe(now)
  })
})
