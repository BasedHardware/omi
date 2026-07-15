// Persist BYOK provider keys encrypted at rest via Electron safeStorage
// (DPAPI on Windows). Mirrors the pattern in `integrations/tokenStore.ts`:
// one JSON file under userData, per-provider base64 ciphertext, synchronous
// file I/O. Key material is NEVER logged.
//
// Storage shape: { openai?: <base64 ciphertext>, anthropic?: ..., ... }
// Each value is `safeStorage.encryptString(rawKey).toString('base64')`.

import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'
import { BYOK_PROVIDERS, isByokActive, type ByokKeys, type ByokProvider } from '../../shared/byok'

/** On-disk shape: provider → base64-encoded safeStorage ciphertext. */
type StoredFile = Partial<Record<ByokProvider, string>>

/**
 * Encrypted-at-rest store for the four BYOK provider keys. Reads/writes are
 * synchronous, matching `tokenStore`. Construct with no args for the real
 * userData path, or pass an explicit path in tests.
 */
export class ByokKeyStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'byok-keys.json')
  }

  private requireEncryption(): void {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('Secure storage is unavailable on this system')
    }
  }

  private readFile(): StoredFile {
    if (!existsSync(this.filePath)) return {}
    try {
      const raw = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredFile
      return raw && typeof raw === 'object' ? raw : {}
    } catch {
      return {}
    }
  }

  private writeFile(data: StoredFile): void {
    writeFileSync(this.filePath, JSON.stringify(data), 'utf8')
  }

  /** Decrypt and return one provider's key, or null if unset/undecryptable. */
  getKey(provider: ByokProvider): string | null {
    const enc = this.readFile()[provider]
    if (!enc) return null
    try {
      this.requireEncryption()
      return safeStorage.decryptString(Buffer.from(enc, 'base64'))
    } catch {
      return null
    }
  }

  /** Decrypt and return every stored provider key. */
  getAllKeys(): ByokKeys {
    const stored = this.readFile()
    const out: ByokKeys = {}
    for (const provider of BYOK_PROVIDERS) {
      const enc = stored[provider]
      if (!enc) continue
      try {
        this.requireEncryption()
        out[provider] = safeStorage.decryptString(Buffer.from(enc, 'base64'))
      } catch {
        /* skip undecryptable entries */
      }
    }
    return out
  }

  /**
   * Encrypt and persist one provider's key. A blank (whitespace-only) key
   * clears that provider instead of storing an empty value.
   */
  setKey(provider: ByokProvider, key: string): void {
    const trimmed = key.trim()
    if (!trimmed) {
      this.clearKey(provider)
      return
    }
    this.requireEncryption()
    const data = this.readFile()
    data[provider] = safeStorage.encryptString(trimmed).toString('base64')
    this.writeFile(data)
  }

  /** Remove one provider's key. */
  clearKey(provider: ByokProvider): void {
    const data = this.readFile()
    if (!(provider in data)) return
    delete data[provider]
    this.writeFile(data)
  }

  /** Remove all stored keys (deletes the backing file). */
  clearAll(): void {
    try {
      rmSync(this.filePath, { force: true })
    } catch {
      /* best-effort */
    }
  }

  /** True when all four providers have a stored key (backend all-or-nothing). */
  isActive(): boolean {
    return isByokActive(this.getAllKeys())
  }
}
