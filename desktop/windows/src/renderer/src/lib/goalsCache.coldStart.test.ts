// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cache, hydrateGoalsFromDisk, resetGoalsCache, writeCache } from './goalsCache'
import type { GoalResponse as Goal } from './omiApi.generated'

const LAST_UID_KEY = 'omi.lastSignedInUid'
const KEY_A = 'omi.cache.goals.userA'
const goal = (id: string): Goal => ({ id, title: id }) as Goal

beforeEach(() => {
  localStorage.clear()
  // Reset the in-memory singleton + hydration flag between tests.
  resetGoalsCache()
})
afterEach(() => localStorage.clear())

describe('goalsCache — cold-start cache-first', () => {
  it('writeCache mirrors the goals to the per-uid snapshot', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    writeCache([goal('g1'), goal('g2')])
    const persisted = JSON.parse(localStorage.getItem(KEY_A) as string) as Goal[]
    expect(persisted.map((g) => g.id)).toEqual(['g1', 'g2'])
  })

  it('hydrateGoalsFromDisk seeds the cache but leaves loaded=false', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([goal('g1')]))
    hydrateGoalsFromDisk()
    expect(cache.goals?.map((g) => g.id)).toEqual(['g1'])
    // loaded stays false so the revalidating fetch still runs on mount.
    expect(cache.loaded).toBe(false)
  })

  it('does not leak the snapshot across accounts (per-uid scoping)', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([goal('a-secret')]))
    // Account switch: teardown resets the in-memory cache + hydration flag.
    resetGoalsCache()
    localStorage.setItem(LAST_UID_KEY, 'userB')
    hydrateGoalsFromDisk()
    expect(cache.goals).toBeNull()
  })

  it('resetGoalsCache clears the in-memory cache', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    writeCache([goal('g1')])
    cache.loaded = true
    resetGoalsCache()
    expect(cache.goals).toBeNull()
    expect(cache.loaded).toBe(false)
  })
})
