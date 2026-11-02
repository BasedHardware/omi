// Pure view-model helpers: client-side search filter + date-bucket grouping.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatSession } from '../../../shared/chatSessions'
import { filterSessions, groupSessionsByDate, toEpochMs } from './chatSessionsView'

function session(over: Partial<ChatSession> & { id: string }): ChatSession {
  return {
    id: over.id,
    title: over.title ?? 'Untitled',
    preview: over.preview,
    createdAt: over.createdAt ?? '2026-07-14T00:00:00Z',
    updatedAt: over.updatedAt ?? '2026-07-14T00:00:00Z',
    appId: over.appId,
    messageCount: over.messageCount ?? 0,
    starred: over.starred ?? false
  }
}

describe('toEpochMs', () => {
  it('passes finite numbers through and parses ISO strings', () => {
    expect(toEpochMs(1_700_000_000_000)).toBe(1_700_000_000_000)
    expect(toEpochMs('2026-07-14T00:00:00Z')).toBe(Date.parse('2026-07-14T00:00:00Z'))
  })
  it('returns 0 for junk (never NaN)', () => {
    expect(toEpochMs('not-a-date')).toBe(0)
    expect(toEpochMs(undefined)).toBe(0)
    expect(toEpochMs(NaN)).toBe(0)
  })
})

describe('filterSessions', () => {
  const list = [
    session({ id: '1', title: 'Trip to Berlin', preview: 'flights' }),
    session({ id: '2', title: 'Grocery list', preview: 'milk and eggs' }),
    session({ id: '3', title: 'Work notes', preview: 'Berlin office' })
  ]

  it('returns the input unchanged for an empty/whitespace query', () => {
    expect(filterSessions(list, '')).toHaveLength(3)
    expect(filterSessions(list, '   ')).toHaveLength(3)
  })

  it('matches title case-insensitively', () => {
    expect(filterSessions(list, 'GROCERY').map((s) => s.id)).toEqual(['2'])
  })

  it('also matches the preview text', () => {
    // "Berlin" is in #1's title and #3's preview.
    expect(filterSessions(list, 'berlin').map((s) => s.id)).toEqual(['1', '3'])
  })

  it('returns nothing when no session matches', () => {
    expect(filterSessions(list, 'zzz')).toHaveLength(0)
  })
})

describe('groupSessionsByDate', () => {
  // Fixed "now": Tue 2026-07-14 12:00 local.
  const now = new Date(2026, 6, 14, 12, 0, 0).getTime()
  const at = (y: number, m: number, d: number, h = 9): string => new Date(y, m, d, h).toISOString()

  it('buckets into the four macOS groups: Today / Yesterday / This Week / Older', () => {
    const groups = groupSessionsByDate(
      [
        session({ id: 'today', updatedAt: at(2026, 6, 14) }),
        session({ id: 'yst', updatedAt: at(2026, 6, 13) }),
        session({ id: 'wk', updatedAt: at(2026, 6, 10) }), // 4 days ago → This Week
        session({ id: 'old', updatedAt: at(2026, 6, 1) }) // 13 days ago → Older
      ],
      now
    )
    expect(groups.map((g) => g.label)).toEqual(['Today', 'Yesterday', 'This Week', 'Older'])
    expect(groups[0].sessions.map((s) => s.id)).toEqual(['today'])
    expect(groups[3].sessions.map((s) => s.id)).toEqual(['old'])
  })

  it('puts everything older than 7 days into "Older" (no month/year buckets)', () => {
    const groups = groupSessionsByDate(
      [
        session({ id: 'may', updatedAt: at(2026, 4, 3) }), // May 2026
        session({ id: 'lastyear', updatedAt: at(2025, 10, 20) }) // Nov 2025
      ],
      now
    )
    expect(groups.map((g) => g.label)).toEqual(['Older'])
    expect(groups[0].sessions.map((s) => s.id)).toEqual(['may', 'lastyear'])
  })

  it('treats the 7-day boundary as a rolling window (just inside → This Week)', () => {
    const groups = groupSessionsByDate(
      [session({ id: 'edge', updatedAt: new Date(now - 6.5 * 86_400_000).toISOString() })],
      now
    )
    expect(groups.map((g) => g.label)).toEqual(['This Week'])
  })

  it('preserves input order within a bucket (server sends updated_at DESC)', () => {
    const groups = groupSessionsByDate(
      [
        session({ id: 'a', updatedAt: at(2026, 6, 14, 11) }),
        session({ id: 'b', updatedAt: at(2026, 6, 14, 8) })
      ],
      now
    )
    expect(groups).toHaveLength(1)
    expect(groups[0].sessions.map((s) => s.id)).toEqual(['a', 'b'])
  })

  describe('across a daylight-saving change', () => {
    // CI runs in UTC, which never changes its clocks, so pin a zone that does: in
    // New York, Sun 2026-03-08 lasts 23 h and Sun 2026-11-01 lasts 25 h. On the
    // Monday after each, today's midnight minus 24 h is not Sunday's midnight.
    beforeEach(() => {
      vi.stubEnv('TZ', 'America/New_York')
    })

    afterEach(() => {
      vi.unstubAllEnvs()
    })

    // Length of a local calendar day in hours; proves the pinned zone took effect.
    const dayHours = (y: number, m: number, d: number): number =>
      (new Date(y, m, d + 1).getTime() - new Date(y, m, d).getTime()) / 3_600_000

    it('files Sunday under "Yesterday" on the Monday after clocks spring forward', () => {
      expect(dayHours(2026, 2, 8)).toBe(23)
      const groups = groupSessionsByDate(
        [
          session({ id: 'today', updatedAt: at(2026, 2, 9) }),
          session({ id: 'yst', updatedAt: at(2026, 2, 8) }),
          session({ id: 'wk', updatedAt: at(2026, 2, 6) })
        ],
        new Date(2026, 2, 9, 12).getTime()
      )
      expect(groups.map((g) => g.label)).toEqual(['Today', 'Yesterday', 'This Week'])
      expect(groups[1].sessions.map((s) => s.id)).toEqual(['yst'])
    })

    it('files Sunday under "Yesterday" on the Monday after clocks fall back', () => {
      expect(dayHours(2026, 10, 1)).toBe(25)
      const groups = groupSessionsByDate(
        [session({ id: 'yst', updatedAt: at(2026, 10, 1) })],
        new Date(2026, 10, 2, 12).getTime()
      )
      expect(groups.map((g) => g.label)).toEqual(['Yesterday'])
    })
  })
})
