// The stats formula. The subtle part — session i's duration comes from the row
// AFTER it (the next MORE RECENT one) because rows are newest-first and carry no
// duration — is what these pin down.
import { describe, expect, it } from 'vitest'
import { computeStats, todayStats } from './stats'
import type { FocusSessionRecord } from '../../../shared/types'

let idSeq = 0
function row(
  status: 'focused' | 'distracted',
  createdAt: number,
  appOrSite = 'App'
): FocusSessionRecord {
  return {
    id: ++idSeq,
    screenshotId: null,
    status,
    appOrSite,
    description: '',
    message: null,
    durationSeconds: 0,
    backendId: null,
    backendSynced: false,
    createdAt,
    windowTitle: null
  }
}

const MIN = 60_000

describe('computeStats', () => {
  it('is empty when there are no sessions', () => {
    expect(computeStats([], 1_000_000)).toEqual({
      focusedMinutes: 0,
      distractedMinutes: 0,
      sessionCount: 0,
      focusedCount: 0,
      distractedCount: 0,
      topDistractions: [],
      focusRate: 0
    })
  })

  it('derives each duration from the NEXT more recent row; the latest runs to now', () => {
    const now = 100 * MIN
    // Newest-first. focused@90m, distracted@70m, focused@40m.
    const sessions = [
      row('focused', 90 * MIN), //  90→now(100) = 10 min focused
      row('distracted', 70 * MIN, 'YouTube'), // 70→90     = 20 min distracted
      row('focused', 40 * MIN) //  40→70     = 30 min focused
    ]
    const s = computeStats(sessions, now)
    expect(s.focusedMinutes).toBe(40) // 10 + 30
    expect(s.distractedMinutes).toBe(20)
    expect(s.sessionCount).toBe(3)
    expect(s.focusedCount).toBe(2)
    expect(s.distractedCount).toBe(1)
    // focusRate = 40 / (40 + 20) * 100
    expect(s.focusRate).toBeCloseTo(66.666, 2)
  })

  it('tallies topDistractions by app, top 5 by seconds', () => {
    const now = 100 * MIN
    const sessions = [
      row('distracted', 95 * MIN, 'YouTube'), // 5 min
      row('distracted', 80 * MIN, 'Reddit'), // 15 min
      row('distracted', 70 * MIN, 'YouTube') // 10 min
    ]
    const s = computeStats(sessions, now)
    // YouTube: 5m (95→100) + 10m (70→80) = 15m over 2 rows. Reddit: 15m (80→95)
    // over 1 row. Equal seconds → stable order keeps first-seen (YouTube) first.
    expect(s.topDistractions).toEqual([
      { appOrSite: 'YouTube', totalSeconds: 15 * 60, count: 2 },
      { appOrSite: 'Reddit', totalSeconds: 15 * 60, count: 1 }
    ])
  })

  it('focusRate is 0 (not NaN) when total elapsed time is zero', () => {
    // Every row at the same instant as `now` → zero duration everywhere.
    const t = 5 * MIN
    const s = computeStats([row('focused', t), row('distracted', t)], t)
    expect(s.focusRate).toBe(0)
    expect(s.focusedMinutes).toBe(0)
    expect(s.distractedMinutes).toBe(0)
  })

  it('clamps a negative duration (a row newer than `now`) to zero', () => {
    const now = 50 * MIN
    // The newest row is in the future relative to now → max(0, …).
    const s = computeStats([row('focused', 60 * MIN)], now)
    expect(s.focusedMinutes).toBe(0)
  })
})

describe('todayStats', () => {
  it('only counts rows from the current calendar day', () => {
    const now = new Date('2026-07-14T15:00:00').getTime()
    const todayMorning = new Date('2026-07-14T09:00:00').getTime()
    const yesterday = new Date('2026-07-13T20:00:00').getTime()
    const s = todayStats([row('focused', todayMorning), row('focused', yesterday)], now)
    // Only today's row is in scope; yesterday's is filtered out.
    expect(s.sessionCount).toBe(1)
  })
})
