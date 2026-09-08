import { describe, it, expect } from 'vitest'
import { isNewLocalDay } from './usageDay'

describe('isNewLocalDay', () => {
  const d = (s: string) => new Date(s).getTime()
  it('is true when there is no previous timestamp', () => {
    expect(isNewLocalDay(null, d('2026-06-05T10:00:00'))).toBe(true)
  })
  it('is false within the same local day', () => {
    expect(isNewLocalDay(d('2026-06-05T01:00:00'), d('2026-06-05T23:00:00'))).toBe(false)
  })
  it('is true across local-day boundaries', () => {
    expect(isNewLocalDay(d('2026-06-05T23:59:00'), d('2026-06-06T00:01:00'))).toBe(true)
  })
})
