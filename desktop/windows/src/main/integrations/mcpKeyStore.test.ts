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

import { clearMcpKey, loadMcpKey, saveMcpKey } from './mcpKeyStore'

describe('mcpKeyStore', () => {
  beforeEach(() => {
    electronState.userData = mkdtempSync(join(tmpdir(), 'omi-mcp-key-'))
    electronState.encryptionAvailable = true
  })

  afterEach(() => {
    rmSync(electronState.userData, { recursive: true, force: true })
  })

  it('stores and loads the MCP key without writing the raw key', () => {
    saveMcpKey({ id: 'key_123', name: 'Omi Windows', key: 'omi_live_secret' })

    const rawFile = readFileSync(join(electronState.userData, 'mcp-key.json'), 'utf8')
    expect(rawFile).not.toContain('omi_live_secret')
    expect(loadMcpKey()).toEqual({
      id: 'key_123',
      name: 'Omi Windows',
      key: 'omi_live_secret'
    })
  })

  it('overwrites an existing stored key on regenerate', () => {
    saveMcpKey({ id: 'key_old', name: 'Omi Windows', key: 'old_secret' })
    saveMcpKey({ id: 'key_new', name: 'Omi Windows', key: 'new_secret' })

    expect(loadMcpKey()).toEqual({
      id: 'key_new',
      name: 'Omi Windows',
      key: 'new_secret'
    })
  })

  it('deletes the stored key', () => {
    saveMcpKey({ id: 'key_123', name: 'Omi Windows', key: 'omi_live_secret' })
    clearMcpKey()

    expect(loadMcpKey()).toBeNull()
  })

  it('refuses to save when secure storage is unavailable', () => {
    electronState.encryptionAvailable = false

    expect(() =>
      saveMcpKey({ id: 'key_123', name: 'Omi Windows', key: 'omi_live_secret' })
    ).toThrow('Secure storage is unavailable on this system')
  })
})
