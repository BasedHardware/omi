// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { clearAllPersistedCaches, readPersistedCache, writePersistedCache } from './persistentCache'

const LAST_UID_KEY = 'omi.lastSignedInUid'

describe('persistentCache (per-uid cold-start cache)', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('round-trips rows scoped to the current uid', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    writePersistedCache('memories', [{ id: '1' }, { id: '2' }])
    expect(readPersistedCache('memories')).toEqual([{ id: '1' }, { id: '2' }])
  })

  it("never leaks another account's cache (per-uid key isolation)", () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    writePersistedCache('memories', [{ id: 'a-only' }])
    // A different account signs in on the same machine.
    localStorage.setItem(LAST_UID_KEY, 'userB')
    expect(readPersistedCache('memories')).toBeNull()
  })

  it('returns null when signed out (no uid)', () => {
    writePersistedCache('memories', [{ id: '1' }])
    expect(readPersistedCache('memories')).toBeNull()
  })

  it('does not persist when signed out (no uid)', () => {
    writePersistedCache('memories', [{ id: '1' }])
    localStorage.setItem(LAST_UID_KEY, 'userA')
    expect(readPersistedCache('memories')).toBeNull()
  })

  it('returns null on a non-array payload (shape-drift tolerance)', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem('omi.cache.memories.userA', JSON.stringify({ not: 'an array' }))
    expect(readPersistedCache('memories')).toBeNull()
  })

  it('returns null on a corrupt (unparseable) payload', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    localStorage.setItem('omi.cache.memories.userA', '{not json')
    expect(readPersistedCache('memories')).toBeNull()
  })

  it('clearAllPersistedCaches purges every surface and uid but keeps other keys', () => {
    localStorage.setItem(LAST_UID_KEY, 'userA')
    writePersistedCache('memories', [{ id: '1' }])
    writePersistedCache('conversations', [{ id: '2' }])
    localStorage.setItem(LAST_UID_KEY, 'userB')
    writePersistedCache('memories', [{ id: '3' }])
    localStorage.setItem('omi.some-device-setting', 'keep-me')
    localStorage.setItem(LAST_UID_KEY, 'userB')

    clearAllPersistedCaches()

    localStorage.setItem(LAST_UID_KEY, 'userA')
    expect(readPersistedCache('memories')).toBeNull()
    expect(readPersistedCache('conversations')).toBeNull()
    localStorage.setItem(LAST_UID_KEY, 'userB')
    expect(readPersistedCache('memories')).toBeNull()
    // A non-cache key (device setting) survives the purge.
    expect(localStorage.getItem('omi.some-device-setting')).toBe('keep-me')
    // The uid pointer itself is not a cache key and survives.
    expect(localStorage.getItem(LAST_UID_KEY)).toBe('userB')
  })
})
