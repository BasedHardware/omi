// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  conversationsCache,
  hydrateConversationsFromDisk,
  invalidateConversationsCache,
  publishConversationsCache,
  type ConversationRow
} from './pageCache'

const LAST_UID_KEY = 'omi.lastSignedInUid'
const KEY_A = 'omi.cache.conversations.userA'

const row = (id: string, extra: Partial<ConversationRow> = {}): ConversationRow => ({
  id,
  title: id,
  subtitle: '',
  preview: '',
  source: 'cloud',
  sortAt: 1,
  ...extra
})

beforeEach(() => {
  localStorage.clear()
  // Resets the in-memory cache AND the one-shot hydration flag.
  invalidateConversationsCache()
})
afterEach(() => localStorage.clear())

describe('pageCache — cold-start cache-first', () => {
  it('publishConversationsCache mirrors the rows to the per-uid snapshot', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    publishConversationsCache([row('c1'), row('c2')])
    const persisted = JSON.parse(localStorage.getItem(KEY_A) as string) as ConversationRow[]
    expect(persisted.map((r) => r.id)).toEqual(['c1', 'c2'])
  })

  it('excludes transient pending placeholders from the snapshot', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    publishConversationsCache([row('c1'), row('p1', { pending: true })])
    const persisted = JSON.parse(localStorage.getItem(KEY_A) as string) as ConversationRow[]
    expect(persisted.map((r) => r.id)).toEqual(['c1'])
  })

  it('hydrateConversationsFromDisk seeds rows from the snapshot but leaves loaded=false', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([row('c1'), row('c2')]))
    hydrateConversationsFromDisk()
    expect(conversationsCache.rows?.map((r) => r.id)).toEqual(['c1', 'c2'])
    // loaded stays false so the revalidating fetch still runs on mount.
    expect(conversationsCache.loaded).toBe(false)
  })

  it('does not leak the snapshot across accounts (per-uid scoping)', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem(KEY_A, JSON.stringify([row('a-secret')]))
    // Account switch: teardown resets the in-memory cache + hydration flag.
    invalidateConversationsCache()
    localStorage.setItem(LAST_UID_KEY, 'userB')
    hydrateConversationsFromDisk()
    expect(conversationsCache.rows).toBeNull()
  })
})
