import { mkdtempSync, readFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const electronState = vi.hoisted(() => ({
  userData: '',
  encryptionAvailable: true
}))

vi.mock('electron', () => ({
  app: {
    getPath: (name: string): string => {
      if (name !== 'userData') throw new Error(`unexpected app path: ${name}`)
      return electronState.userData
    }
  },
  safeStorage: {
    isEncryptionAvailable: (): boolean => electronState.encryptionAvailable,
    encryptString: (value: string): Buffer => Buffer.from(`encrypted:${value}`, 'utf8'),
    decryptString: (value: Buffer): string => value.toString('utf8').replace(/^encrypted:/, '')
  }
}))

import {
  clearByokSettings,
  deleteByokKey,
  getByokStatus,
  loadByokKey,
  recordByokValidation,
  saveByokKey,
  setActiveByokChatProvider
} from './store'

describe('BYOK secure storage', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-byok-'))
    electronState.encryptionAvailable = true
  })

  afterEach(() => {
    rmSync(electronState.userData, { recursive: true, force: true })
  })

  it('stores keys encrypted and returns only masked provider status', () => {
    const key = 'sk-openai-secret-1234567890'

    const status = saveByokKey('openai', key)

    const rawFile = readFileSync(join(electronState.userData, 'byok-keys.json'), 'utf8')
    expect(rawFile).not.toContain(key)
    expect(loadByokKey('openai')).toBe(key)
    expect(status.providers.openai).toMatchObject({
      configured: true,
      maskedKey: 'sk-o...7890'
    })
    expect(JSON.stringify(getByokStatus())).not.toContain(key)
  })

  it('persists active chat provider and clears it when that provider is deleted', () => {
    saveByokKey('openrouter', 'sk-or-secret-1234567890')

    expect(setActiveByokChatProvider('openrouter').activeChatProvider).toBe('openrouter')
    expect(deleteByokKey('openrouter').activeChatProvider).toBeNull()
  })

  it('records validation metadata without storing raw keys in status', () => {
    const key = 'AIzaSySecretGeminiKey123456789'
    saveByokKey('gemini', key)

    const status = recordByokValidation('gemini', { ok: false, error: 'Provider rejected the key' })

    expect(status.providers.gemini).toMatchObject({
      configured: true,
      lastValidationOk: false,
      lastValidationError: 'Provider rejected the key'
    })
    expect(JSON.stringify(status)).not.toContain(key)
  })

  it('deletes all BYOK settings', () => {
    saveByokKey('deepgram', 'deepgram_secret_token_1234567890')
    clearByokSettings()

    expect(loadByokKey('deepgram')).toBeNull()
    expect(getByokStatus().providers.deepgram.configured).toBe(false)
    expect(getByokStatus().providers.elevenlabs.configured).toBe(false)
  })

  it('refuses to save when secure storage is unavailable', () => {
    electronState.encryptionAvailable = false

    expect(() => saveByokKey('openai', 'sk-openai-secret-1234567890')).toThrow(
      'Secure storage is unavailable on this system'
    )
  })
})
