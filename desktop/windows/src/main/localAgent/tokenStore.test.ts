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
  clearLocalAgentToken,
  ensureLocalAgentToken,
  loadLocalAgentToken,
  rotateLocalAgentToken,
  saveLocalAgentToken
} from './tokenStore'

describe('local agent token store', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-local-agent-token-'))
    electronState.encryptionAvailable = true
  })

  afterEach(() => {
    rmSync(electronState.userData, { recursive: true, force: true })
  })

  it('stores and loads the bearer token without writing the raw token', () => {
    saveLocalAgentToken('local_secret_token')

    const rawFile = readFileSync(join(electronState.userData, 'local-agent-token.json'), 'utf8')
    expect(rawFile).not.toContain('local_secret_token')
    expect(loadLocalAgentToken()).toBe('local_secret_token')
  })

  it('creates one token and reuses it on later calls', () => {
    const first = ensureLocalAgentToken()
    const second = ensureLocalAgentToken()

    expect(first).toMatch(/^[A-Za-z0-9_-]+$/)
    expect(second).toBe(first)
  })

  it('rotates and persists a new bearer token', () => {
    const first = ensureLocalAgentToken()
    const second = rotateLocalAgentToken()

    expect(second).toMatch(/^[A-Za-z0-9_-]+$/)
    expect(second).not.toBe(first)
    expect(loadLocalAgentToken()).toBe(second)
  })

  it('deletes the stored token', () => {
    saveLocalAgentToken('local_secret_token')
    clearLocalAgentToken()

    expect(loadLocalAgentToken()).toBeNull()
  })

  it('refuses to save when secure storage is unavailable', () => {
    electronState.encryptionAvailable = false

    expect(() => saveLocalAgentToken('local_secret_token')).toThrow(
      'Secure storage is unavailable on this system'
    )
  })
})
