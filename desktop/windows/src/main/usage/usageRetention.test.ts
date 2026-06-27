import { describe, it, expect } from 'vitest'
import {
  usageCutoff,
  normalizeRetentionDays,
  DEFAULT_RETENTION_DAYS,
  MIN_RETENTION_DAYS,
  MAX_RETENTION_DAYS,
  RETENTION_PRESETS
} from './usageRetention'

const DAY_MS = 86_400_000

describe('usageCutoff', () => {
  it('returns the timestamp DEFAULT_RETENTION_DAYS before now by default', () => {
    const now = 1_000_000_000_000
    expect(usageCutoff(now)).toBe(now - DEFAULT_RETENTION_DAYS * DAY_MS)
  })

  it('respects a custom retention window', () => {
    const now = 1_000_000_000_000
    expect(usageCutoff(now, 7)).toBe(now - 7 * DAY_MS)
  })
})

describe('normalizeRetentionDays', () => {
  it('keeps a valid in-range integer', () => {
    expect(normalizeRetentionDays(30)).toBe(30)
    expect(normalizeRetentionDays(90)).toBe(90)
  })

  it('rounds fractional values', () => {
    expect(normalizeRetentionDays(45.4)).toBe(45)
  })

  it('clamps below the minimum', () => {
    expect(normalizeRetentionDays(1)).toBe(MIN_RETENTION_DAYS)
  })

  it('clamps above the maximum', () => {
    expect(normalizeRetentionDays(100_000)).toBe(MAX_RETENTION_DAYS)
  })

  it('falls back to the default for non-finite / non-numeric input', () => {
    expect(normalizeRetentionDays(NaN)).toBe(DEFAULT_RETENTION_DAYS)
    expect(normalizeRetentionDays(undefined)).toBe(DEFAULT_RETENTION_DAYS)
    expect(normalizeRetentionDays('45')).toBe(DEFAULT_RETENTION_DAYS)
  })

  it('exposes sane bounds and presets', () => {
    expect(DEFAULT_RETENTION_DAYS).toBeGreaterThanOrEqual(30)
    expect(MIN_RETENTION_DAYS).toBeLessThan(DEFAULT_RETENTION_DAYS)
    expect(MAX_RETENTION_DAYS).toBeGreaterThan(DEFAULT_RETENTION_DAYS)
    expect(RETENTION_PRESETS).toContain(DEFAULT_RETENTION_DAYS)
    // Every preset must survive normalization unchanged.
    for (const p of RETENTION_PRESETS) expect(normalizeRetentionDays(p)).toBe(p)
  })
})
