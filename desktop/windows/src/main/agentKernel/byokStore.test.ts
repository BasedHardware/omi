import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const dir = mkdtempSync(join(tmpdir(), 'byok-store-test-'))

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

import { safeStorage } from 'electron'
import { ByokKeyStore } from './byokStore'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

let store: ByokKeyStore

beforeEach(() => {
  store = new ByokKeyStore(join(dir, `byok-${Math.random().toString(36).slice(2)}.json`))
})

describe('ByokKeyStore', () => {
  it('set → get round-trips a single provider', () => {
    store.setKey('openai', 'sk-openai')
    expect(store.getKey('openai')).toBe('sk-openai')
    expect(store.getKey('anthropic')).toBeNull()
  })

  it('getAllKeys returns every stored provider', () => {
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    expect(store.getAllKeys()).toEqual({
      openai: 'sk-openai',
      anthropic: 'sk-ant',
      gemini: 'gm-key',
      deepgram: 'dg-key'
    })
  })

  it('trims on set and clears a provider when set to blank', () => {
    store.setKey('openai', '  sk-openai  ')
    expect(store.getKey('openai')).toBe('sk-openai')
    store.setKey('openai', '   ')
    expect(store.getKey('openai')).toBeNull()
  })

  it('clearKey removes one provider and leaves the rest', () => {
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.clearKey('openai')
    expect(store.getKey('openai')).toBeNull()
    expect(store.getKey('anthropic')).toBe('sk-ant')
  })

  it('clearAll removes everything', () => {
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.clearAll()
    expect(store.getAllKeys()).toEqual({})
  })

  it('after sign-out (clearAll on a full set) getAllKeys is empty AND isActive is false', () => {
    // Cross-account leak guard: a second account on this install must not inherit
    // the prior user's keys (which the REST/chat/WS lanes would otherwise send).
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    store.setKey('deepgram', 'dg-key')
    expect(store.isActive()).toBe(true)
    store.clearAll()
    expect(store.getAllKeys()).toEqual({})
    expect(store.isActive()).toBe(false)
  })

  it('isActive is true only at 4/4 providers', () => {
    expect(store.isActive()).toBe(false)
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    expect(store.isActive()).toBe(false)
    store.setKey('deepgram', 'dg-key')
    expect(store.isActive()).toBe(true)
  })

  it('setKey throws and getKey returns null when encryption is unavailable', () => {
    store.setKey('openai', 'sk-openai')
    const spy = vi.spyOn(safeStorage, 'isEncryptionAvailable').mockReturnValue(false)
    try {
      expect(() => store.setKey('anthropic', 'sk-ant')).toThrow('Secure storage is unavailable')
      expect(store.getKey('openai')).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })

  it('defaults the file path to userData when constructed with no args', () => {
    const dflt = new ByokKeyStore()
    dflt.setKey('openai', 'sk-openai')
    expect(dflt.getKey('openai')).toBe('sk-openai')
    dflt.clearAll()
  })
})
