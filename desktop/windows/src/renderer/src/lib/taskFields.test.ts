import { describe, it, expect } from 'vitest'
import {
  PRIORITY_ORDER,
  dueNextWeekMs,
  dueTodayMs,
  dueTomorrowMs,
  normalizePriority,
  quickDueChips,
  todayDueAtMs
} from './taskFields'

describe('priority model', () => {
  it('normalizes known values case-insensitively and rejects junk', () => {
    expect(normalizePriority('high')).toBe('high')
    expect(normalizePriority(' HIGH ')).toBe('high')
    expect(normalizePriority('Medium')).toBe('medium')
    expect(normalizePriority('low')).toBe('low')
    expect(normalizePriority('urgent')).toBeNull()
    expect(normalizePriority('')).toBeNull()
    expect(normalizePriority(null)).toBeNull()
    expect(normalizePriority(undefined)).toBeNull()
  })

  it('declares the detail-panel chip order low to high, matching the mac panel', () => {
    expect([...PRIORITY_ORDER]).toEqual(['low', 'medium', 'high'])
  })
})

describe('todayDueAtMs', () => {
  it('pins to 23:59:00 local of the same day, matching mac todayDueAt', () => {
    const now = new Date(2026, 7, 15, 9, 30, 42).getTime()
    const d = new Date(todayDueAtMs(now))
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 7, 15])
    expect([d.getHours(), d.getMinutes(), d.getSeconds()]).toEqual([23, 59, 0])
  })
})

describe('quick due chips', () => {
  // A fixed local-time reference: 2026-08-15 at 09:30 local.
  const now = new Date(2026, 7, 15, 9, 30).getTime()

  it('today pins to local noon of the same day', () => {
    const d = new Date(dueTodayMs(now))
    expect([d.getFullYear(), d.getMonth(), d.getDate(), d.getHours()]).toEqual([2026, 7, 15, 12])
  })

  it('tomorrow and next week advance by calendar days at local noon', () => {
    const t = new Date(dueTomorrowMs(now))
    expect([t.getMonth(), t.getDate(), t.getHours()]).toEqual([7, 16, 12])
    const w = new Date(dueNextWeekMs(now))
    expect([w.getMonth(), w.getDate(), w.getHours()]).toEqual([7, 22, 12])
  })

  it('tomorrow crosses a month boundary correctly', () => {
    const eom = new Date(2026, 7, 31, 20, 0).getTime()
    const t = new Date(dueTomorrowMs(eom))
    expect([t.getMonth(), t.getDate()]).toEqual([8, 1])
  })

  it('quickDueChips returns the three chips in order with consistent values', () => {
    const chips = quickDueChips(now)
    expect(chips.map((c) => c.key)).toEqual(['today', 'tomorrow', 'nextWeek'])
    expect(chips.map((c) => c.label)).toEqual(['Today', 'Tomorrow', 'Next week'])
    expect(chips[0].ms).toBe(dueTodayMs(now))
    expect(chips[1].ms).toBe(dueTomorrowMs(now))
    expect(chips[2].ms).toBe(dueNextWeekMs(now))
  })
})
