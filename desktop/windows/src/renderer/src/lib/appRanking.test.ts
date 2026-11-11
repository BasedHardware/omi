import { describe, it, expect } from 'vitest'
import { rankSearchResults } from './appRanking'
import type { App as AppEntry } from './omiApi.generated'

function app(partial: Partial<AppEntry> & { id: string; name: string }): AppEntry {
  return {
    id: partial.id,
    name: partial.name,
    author: partial.author ?? '',
    description: partial.description ?? '',
    category: partial.category ?? '',
    installs: partial.installs ?? 0,
    rating_avg: partial.rating_avg ?? 0
  } as AppEntry
}

describe('rankSearchResults', () => {
  it('returns [] for an empty or whitespace query', () => {
    const apps = [app({ id: '1', name: 'Alpha' })]
    expect(rankSearchResults(apps, '')).toEqual([])
    expect(rankSearchResults(apps, '   ')).toEqual([])
  })

  it('matches name, description, category, and author (case-insensitive)', () => {
    const apps = [
      app({ id: 'n', name: 'Zebra' }),
      app({ id: 'd', name: 'X', description: 'a zebra tool' }),
      app({ id: 'c', name: 'Y', category: 'zebra-stuff' }),
      app({ id: 'a', name: 'W', author: 'Zebra Labs' }),
      app({ id: 'no', name: 'Nothing', description: 'unrelated' })
    ]
    const ids = rankSearchResults(apps, 'ZEBRA').map((a) => a.id)
    expect(ids).toContain('n')
    expect(ids).toContain('d')
    expect(ids).toContain('c')
    expect(ids).toContain('a')
    expect(ids).not.toContain('no')
  })

  it('ranks exact name match, then name-prefix match, then popularity', () => {
    const apps = [
      // substring matches (tier 2): "note" appears mid-name, not as a prefix.
      app({ id: 'popular', name: 'My Notebook', installs: 1_000_000, rating_avg: 5 }),
      app({ id: 'substr', name: 'Keep Notes', installs: 500, rating_avg: 5 }),
      app({ id: 'prefix', name: 'Notes Plus', installs: 10, rating_avg: 4 }),
      app({ id: 'exact', name: 'Note', installs: 1, rating_avg: 1 })
    ]
    const ids = rankSearchResults(apps, 'note').map((a) => a.id)
    // exact name, then prefix, then substring matches ordered by popularity.
    expect(ids[0]).toBe('exact')
    expect(ids[1]).toBe('prefix')
    expect(ids[2]).toBe('popular')
    expect(ids[3]).toBe('substr')
  })

  // Regression guard for the MAJOR: a user's installed low-popularity app, searched
  // by its exact name, must surface at the very top so it stays within the render
  // cap (SEARCH_LIMIT) and remains reachable to toggle off — even when the catalog
  // holds many more-popular apps that also match the query as a substring.
  it('keeps a low-popularity exact-name match reachable ahead of popular substring matches', () => {
    const noise = Array.from({ length: 200 }, (_, i) =>
      app({
        id: `noise-${i}`,
        name: `Widget notes ${i}`,
        installs: 100_000 + i,
        rating_avg: 5
      })
    )
    const mine = app({ id: 'mine', name: 'Notes', installs: 1, rating_avg: 0 })
    const ranked = rankSearchResults([...noise, mine], 'notes')
    expect(ranked[0].id).toBe('mine')
    expect(ranked.findIndex((a) => a.id === 'mine')).toBeLessThan(60)
  })
})
