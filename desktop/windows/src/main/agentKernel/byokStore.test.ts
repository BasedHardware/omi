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
import { byokFingerprint } from '../../shared/byokFingerprint'

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

  it('stores the Codex key separately from BYOK providers', () => {
    store.setCodexKey('sk-codex')
    expect(store.getCodexKey()).toBe('sk-codex')
    expect(store.getAllKeys()).toEqual({})
    store.clearCodexKey()
    expect(store.getCodexKey()).toBeNull()
  })

  it('records Codex migration complete when no legacy OpenAI key exists', () => {
    expect(store.getCodexKey()).toBeNull()
    store.setKey('openai', 'sk-later')
    expect(store.getCodexKey()).toBeNull()
    expect(store.getKey('openai')).toBe('sk-later')
  })

  it('migrates a legacy OpenAI Codex key without removing the BYOK slot', () => {
    store.setKey('openai', 'sk-legacy-codex')
    expect(store.getCodexKey()).toBe('sk-legacy-codex')
    store.clearKey('openai')
    expect(store.getCodexKey()).toBe('sk-legacy-codex')
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

  it('clearAll removes BYOK keys while preserving the Codex key', () => {
    store.setKey('openai', 'sk-openai')
    store.setKey('anthropic', 'sk-ant')
    store.setCodexKey('sk-codex')
    store.clearAll()
    expect(store.getAllKeys()).toEqual({})
    expect(store.getCodexKey()).toBe('sk-codex')
  })

  it('migrates a legacy OpenAI Codex key before clearAll deletes the openai slot', () => {
    store.setKey('openai', 'sk-legacy-codex')
    store.clearAll()
    expect(store.getAllKeys()).toEqual({})
    expect(store.getCodexKey()).toBe('sk-legacy-codex')
  })

  it('does not restore an OpenAI BYOK key after Codex is explicitly cleared', () => {
    store.setKey('openai', 'sk-openai')
    store.setCodexKey('sk-codex')
    store.clearCodexKey()
    expect(store.getCodexKey()).toBeNull()
    expect(store.getKey('openai')).toBe('sk-openai')
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

  it('isActive is true with a configured LLM provider', () => {
    expect(store.isActive()).toBe(false)
    store.setKey('openai', 'sk-openai')
    expect(store.isActive()).toBe(true)
    store.setKey('anthropic', 'sk-ant')
    store.setKey('gemini', 'gm-key')
    expect(store.isActive()).toBe(true)
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

  describe('enrolled fingerprints + validatedProviders', () => {
    it('persists enrollment evidence and reports only matching providers as validated', () => {
      store.setKey('deepgram', 'dg-key')
      store.setKey('openai', 'sk-openai')
      // No evidence yet — presence alone is not a validated capability.
      expect(store.validatedProviders()).toEqual([])

      store.setEnrolledFingerprints({
        deepgram: byokFingerprint('dg-key'),
        openai: byokFingerprint('sk-openai')
      })
      expect(store.getEnrolledFingerprints()).toEqual({
        deepgram: byokFingerprint('dg-key'),
        openai: byokFingerprint('sk-openai')
      })
      expect(store.validatedProviders().sort()).toEqual(['deepgram', 'openai'])
    })

    it('drops a provider from validated once its key is rotated (until re-enrollment)', () => {
      store.setKey('deepgram', 'dg-key')
      store.setEnrolledFingerprints({ deepgram: byokFingerprint('dg-key') })
      expect(store.validatedProviders()).toEqual(['deepgram'])

      // Rejected-key scenario: the stored key never matched an accepted fingerprint.
      store.setKey('openai', 'sk-bad')
      expect(store.validatedProviders()).toEqual(['deepgram'])

      store.setKey('deepgram', 'dg-rotated')
      expect(store.validatedProviders()).toEqual([])
    })

    it('clearing one provider key drops its enrollment evidence too', () => {
      store.setKey('deepgram', 'dg-key')
      store.setKey('openai', 'sk-openai')
      store.setEnrolledFingerprints({
        deepgram: byokFingerprint('dg-key'),
        openai: byokFingerprint('sk-openai')
      })
      store.clearKey('deepgram')
      expect(store.getEnrolledFingerprints()).toEqual({ openai: byokFingerprint('sk-openai') })
      expect(store.validatedProviders()).toEqual(['openai'])

      store.setKey('deepgram', 'dg-key') // same key re-added: evidence is gone → must re-enroll
      expect(store.validatedProviders()).toEqual(['openai'])
    })

    it('clearEnrolledFingerprints and clearAll wipe the evidence (Codex still preserved by clearAll)', () => {
      store.setCodexKey('sk-codex')
      store.setKey('deepgram', 'dg-key')
      store.setEnrolledFingerprints({ deepgram: byokFingerprint('dg-key') })

      const other = new ByokKeyStore(
        join(dir, `byok-other-${Math.random().toString(36).slice(2)}.json`)
      )
      other.setKey('openai', 'sk-openai')
      other.setEnrolledFingerprints({ openai: byokFingerprint('sk-openai') })
      other.clearEnrolledFingerprints()
      expect(other.getEnrolledFingerprints()).toEqual({})
      expect(other.validatedProviders()).toEqual([])

      store.clearAll()
      expect(store.getEnrolledFingerprints()).toEqual({})
      expect(store.validatedProviders()).toEqual([])
      expect(store.getKey('deepgram')).toBeNull()
      expect(store.getCodexKey()).toBe('sk-codex')
    })
  })

  it('defaults the file path to userData when constructed with no args', () => {
    const dflt = new ByokKeyStore()
    dflt.setKey('openai', 'sk-openai')
    expect(dflt.getKey('openai')).toBe('sk-openai')
    dflt.clearAll()
  })
})
