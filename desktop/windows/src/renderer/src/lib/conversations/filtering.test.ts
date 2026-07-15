import { describe, expect, it } from 'vitest'
import type { ConversationRow } from '../pageCache'
import {
  applyFilters,
  buildConversationQuery,
  canMerge,
  endOfLocalDay,
  groupConversationsByDate,
  hasActiveFilters,
  isCloudBacked,
  matchesType,
  mergeableRows,
  startOfLocalDay,
  type ConversationFilters,
  NO_DATE_RANGE
} from './filtering'

function row(over: Partial<ConversationRow> = {}): ConversationRow {
  return {
    id: 'c1',
    title: 'Untitled',
    subtitle: '',
    preview: '',
    source: 'cloud',
    sortAt: 0,
    ...over
  }
}

const ALL: ConversationFilters = {
  folder: { kind: 'all' },
  type: 'all',
  query: '',
  dateRange: NO_DATE_RANGE
}

// A fixed reference "now": 2026-01-15 12:00 local.
const NOW = new Date(2026, 0, 15, 12, 0, 0).getTime()
const DAY = 86_400_000

describe('isCloudBacked', () => {
  it('is true only for non-pending cloud rows', () => {
    expect(isCloudBacked(row({ source: 'cloud' }))).toBe(true)
    expect(isCloudBacked(row({ source: 'cloud', pending: true }))).toBe(false)
    expect(isCloudBacked(row({ source: 'local' }))).toBe(false)
  })
})

describe('matchesType', () => {
  it('recording includes cloud conversations and local recordings, excludes chats', () => {
    expect(matchesType(row({ source: 'cloud' }), 'recording')).toBe(true)
    expect(matchesType(row({ source: 'local', localKind: 'recording' }), 'recording')).toBe(true)
    expect(matchesType(row({ source: 'local', localKind: 'chat' }), 'recording')).toBe(false)
  })
  it('chat matches only chat rows', () => {
    expect(matchesType(row({ localKind: 'chat' }), 'chat')).toBe(true)
    expect(matchesType(row({ source: 'cloud' }), 'chat')).toBe(false)
  })
})

describe('filter composition', () => {
  const rows = [
    row({ id: 'cloud-starred', source: 'cloud', starred: true, folderId: 'f1', preview: 'alpha' }),
    row({ id: 'cloud-plain', source: 'cloud', starred: false, folderId: null, preview: 'beta' }),
    row({ id: 'local-rec', source: 'local', localKind: 'recording', preview: 'alpha' }),
    row({ id: 'chat', source: 'local', localKind: 'chat', preview: 'gamma' })
  ]

  it('all + all shows everything', () => {
    expect(applyFilters(rows, ALL).map((r) => r.id)).toEqual([
      'cloud-starred',
      'cloud-plain',
      'local-rec',
      'chat'
    ])
  })

  it('starred filter shows only starred cloud rows (hides locals/chats)', () => {
    const out = applyFilters(rows, { ...ALL, folder: { kind: 'starred' } })
    expect(out.map((r) => r.id)).toEqual(['cloud-starred'])
  })

  it('folder filter shows only cloud rows in that folder', () => {
    const out = applyFilters(rows, { ...ALL, folder: { kind: 'folder', id: 'f1' } })
    expect(out.map((r) => r.id)).toEqual(['cloud-starred'])
  })

  it('type + folder + query all compose (AND)', () => {
    // starred folder AND recording type AND query 'alpha' → only cloud-starred.
    const out = applyFilters(rows, {
      folder: { kind: 'starred' },
      type: 'recording',
      query: 'alpha',
      dateRange: NO_DATE_RANGE
    })
    expect(out.map((r) => r.id)).toEqual(['cloud-starred'])
  })

  it('query matches title or preview, case-insensitively', () => {
    const out = applyFilters(rows, { ...ALL, query: 'ALPHA' })
    expect(out.map((r) => r.id)).toEqual(['cloud-starred', 'local-rec'])
  })

  it('date range filters by sortAt (both bounds inclusive)', () => {
    const dated = [
      row({ id: 'old', sortAt: NOW - 3 * DAY }),
      row({ id: 'mid', sortAt: NOW - 1 * DAY }),
      row({ id: 'new', sortAt: NOW })
    ]
    const out = applyFilters(dated, {
      ...ALL,
      dateRange: { start: startOfLocalDay(NOW - 1 * DAY), end: endOfLocalDay(NOW) }
    })
    expect(out.map((r) => r.id)).toEqual(['mid', 'new'])
  })
})

describe('hasActiveFilters', () => {
  it('is false for the default filters', () => {
    expect(hasActiveFilters(ALL)).toBe(false)
  })
  it.each([
    ['folder', { ...ALL, folder: { kind: 'starred' as const } }],
    ['type', { ...ALL, type: 'chat' as const }],
    ['query', { ...ALL, query: 'x' }],
    ['date', { ...ALL, dateRange: { start: 1, end: null } }]
  ])('is true when %s is set', (_name, f) => {
    expect(hasActiveFilters(f as ConversationFilters)).toBe(true)
  })
})

describe('merge eligibility', () => {
  it('needs at least two cloud conversations', () => {
    const two = [row({ id: 'a', source: 'cloud' }), row({ id: 'b', source: 'cloud' })]
    expect(canMerge(two)).toBe(true)
    expect(canMerge([row({ id: 'a', source: 'cloud' })])).toBe(false)
  })
  it('ignores local / pending rows', () => {
    const sel = [
      row({ id: 'a', source: 'cloud' }),
      row({ id: 'b', source: 'local', localKind: 'recording' }),
      row({ id: 'c', source: 'cloud', pending: true })
    ]
    expect(mergeableRows(sel).map((r) => r.id)).toEqual(['a'])
    expect(canMerge(sel)).toBe(false)
  })
})

describe('buildConversationQuery', () => {
  it('defaults to limit/offset only', () => {
    expect(buildConversationQuery({ kind: 'all' }, NO_DATE_RANGE)).toEqual({
      limit: 100,
      offset: 0
    })
  })
  it('adds starred=true for the starred chip', () => {
    expect(buildConversationQuery({ kind: 'starred' }, NO_DATE_RANGE)).toMatchObject({
      starred: true
    })
  })
  it('adds folder_id for a folder chip', () => {
    expect(buildConversationQuery({ kind: 'folder', id: 'f9' }, NO_DATE_RANGE)).toMatchObject({
      folder_id: 'f9'
    })
  })
  it('serializes date bounds to ISO strings', () => {
    const q = buildConversationQuery({ kind: 'all' }, { start: NOW, end: NOW + DAY })
    expect(q.start_date).toBe(new Date(NOW).toISOString())
    expect(q.end_date).toBe(new Date(NOW + DAY).toISOString())
  })
})

describe('groupConversationsByDate', () => {
  it('buckets into Today / Yesterday / dated, newest section first', () => {
    const rows = [
      row({ id: 'today-am', sortAt: new Date(2026, 0, 15, 9).getTime() }),
      row({ id: 'today-pm', sortAt: new Date(2026, 0, 15, 18).getTime() }),
      row({ id: 'yday', sortAt: new Date(2026, 0, 14, 10).getTime() }),
      row({ id: 'older', sortAt: new Date(2026, 0, 5, 10).getTime() })
    ]
    const sections = groupConversationsByDate(rows, NOW)
    expect(sections.map((s) => s.label)).toEqual(['Today', 'Yesterday', 'Jan 5, 2026'])
    // Within Today, newest first.
    expect(sections[0].rows.map((r) => r.id)).toEqual(['today-pm', 'today-am'])
  })

  it('returns an empty array for no rows', () => {
    expect(groupConversationsByDate([], NOW)).toEqual([])
  })

  it('keys are stable local-midnight epochs', () => {
    const sections = groupConversationsByDate([row({ sortAt: NOW })], NOW)
    expect(sections[0].key).toBe(String(startOfLocalDay(NOW)))
  })
})
