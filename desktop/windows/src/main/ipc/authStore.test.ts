import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'auth-store-test-'))

// Mock Electron: a temp userData dir plus an identity-ish safeStorage so the
// encrypt→base64→decrypt round-trip is exercised without real DPAPI. ipcMain and
// webContents are stubbed so the module imports (registerAuthStoreHandlers pulls
// them in), even though these tests only exercise the store class directly.
vi.mock('electron', () => ({
  app: { getPath: (): string => dir },
  ipcMain: { handle: (): void => {} },
  webContents: { getAllWebContents: (): unknown[] => [] },
  safeStorage: {
    isEncryptionAvailable: (): boolean => true,
    encryptString: (s: string): Buffer => Buffer.from(s, 'utf8'),
    decryptString: (b: Buffer): string => b.toString('utf8')
  }
}))

import { safeStorage } from 'electron'
import { AuthTokenStore } from './authStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

let store: AuthTokenStore
let filePath: string

beforeEach(() => {
  filePath = join(dir, `auth-${Math.random().toString(36).slice(2)}.json`)
  store = new AuthTokenStore(filePath)
})

const KEY = 'firebase:authUser:AIzaTest:[DEFAULT]'
const VALUE = JSON.stringify({ uid: 'u1', stsTokenManager: { accessToken: 'id-tok' } })

describe('AuthTokenStore', () => {
  it('set → get round-trips a value under a namespaced firebase key', () => {
    store.set(KEY, VALUE)
    expect(store.get(KEY)).toBe(VALUE)
    expect(store.get('firebase:authUser:other')).toBeNull()
  })

  it('get returns null when the file is missing', () => {
    expect(store.get(KEY)).toBeNull()
    expect(existsSync(filePath)).toBe(false)
  })

  it('set persists ciphertext, not plaintext, on disk', () => {
    store.set(KEY, VALUE)
    const raw = readFileSync(filePath, 'utf8')
    // The base64-of-"utf8-bytes" fake still must not contain the raw token text.
    expect(raw).not.toContain('id-tok')
    expect(raw).not.toContain('accessToken')
  })

  it('remove clears one entry and deletes the file when it empties', () => {
    store.set(KEY, VALUE)
    expect(existsSync(filePath)).toBe(true)
    store.remove(KEY)
    expect(store.get(KEY)).toBeNull()
    expect(existsSync(filePath)).toBe(false)
  })

  it('remove leaves other entries intact', () => {
    store.set(KEY, VALUE)
    store.set('firebase:authUser:second', 'v2')
    store.remove(KEY)
    expect(store.get(KEY)).toBeNull()
    expect(store.get('firebase:authUser:second')).toBe('v2')
    expect(existsSync(filePath)).toBe(true)
  })

  it('set throws and get returns null when encryption is unavailable', () => {
    store.set(KEY, VALUE)
    const spy = vi.spyOn(safeStorage, 'isEncryptionAvailable').mockReturnValue(false)
    try {
      expect(() => store.set('firebase:authUser:x', 'v')).toThrow('Secure storage is unavailable')
      expect(store.get(KEY)).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })

  it('isAvailable reflects safeStorage', () => {
    expect(store.isAvailable()).toBe(true)
    const spy = vi.spyOn(safeStorage, 'isEncryptionAvailable').mockReturnValue(false)
    try {
      expect(store.isAvailable()).toBe(false)
    } finally {
      spy.mockRestore()
    }
  })

  it('defaults the file path to userData when constructed with no args', () => {
    const dflt = new AuthTokenStore()
    dflt.set(KEY, VALUE)
    expect(dflt.get(KEY)).toBe(VALUE)
    dflt.remove(KEY)
  })
})
