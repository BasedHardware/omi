import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'beeper-token-store-test-'))

// Mock Electron: a temp userData dir plus an identity-ish safeStorage so the
// encrypt→base64→decrypt round-trip is exercised without real DPAPI.
vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  }
}))

import { BeeperTokenStore } from './beeperTokenStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

let store: BeeperTokenStore

beforeEach(() => {
  store = new BeeperTokenStore(join(dir, `token-${Math.random().toString(36).slice(2)}.json`))
})

describe('BeeperTokenStore', () => {
  it('has() is false and get() is null before anything is stored', () => {
    expect(store.has()).toBe(false)
    expect(store.get()).toBeNull()
  })

  it('set → get round-trips the token', () => {
    store.set('beeper_access_token_abc123')
    expect(store.get()).toBe('beeper_access_token_abc123')
    expect(store.has()).toBe(true)
  })

  it('clear() removes the token', () => {
    store.set('beeper_access_token_abc123')
    store.clear()
    expect(store.get()).toBeNull()
    expect(store.has()).toBe(false)
  })

  it('a later set() overwrites the earlier token', () => {
    store.set('first')
    store.set('second')
    expect(store.get()).toBe('second')
  })

  it('clearAll() is an alias for clear() (used by sign-out teardown)', () => {
    store.set('beeper_access_token_abc123')
    store.clearAll()
    expect(store.get()).toBeNull()
    expect(store.has()).toBe(false)
  })
})
