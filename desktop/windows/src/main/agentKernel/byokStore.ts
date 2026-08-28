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
import {
  BYOK_PROVIDERS,
  isByokActive,
  type ByokEnrolledFingerprints,
  type ByokKeys,
  type ByokProvider
} from '../../shared/byok'
import { byokFingerprint } from '../../shared/byokFingerprint'

/** On-disk shape: provider → base64-encoded safeStorage ciphertext. */
type StoredFile = Partial<Record<ByokProvider | 'codex', string>> & {
  codexMigrationComplete?: boolean
  /**
   * Fingerprints of the keys the backend currently enforces (the last successful
   * enrollment), mirroring macOS `persistEnrolledFingerprints`. Hashes only —
   * never raw key material. Capability claims (e.g. transcription BYOK) must
   * match these, not mere key presence.
   */
  enrolledFingerprints?: ByokEnrolledFingerprints
}

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

  private migrateLegacyCodexKey(): void {
    const stored = this.readFile()
    if (stored.codexMigrationComplete) return
    if (stored.openai && !stored.codex) {
      stored.codex = stored.openai
    }
    stored.codexMigrationComplete = true
    this.writeFile(stored)
  }

  getCodexKey(): string | null {
    this.migrateLegacyCodexKey()
    const enc = this.readFile().codex
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

  setCodexKey(key: string): void {
    const trimmed = key.trim()
    if (!trimmed) {
      this.clearCodexKey()
      return
    }
    this.requireEncryption()
    const data = this.readFile()
    data.codex = safeStorage.encryptString(trimmed).toString('base64')
    this.writeFile(data)
  }

  /** Remove one provider's key. */
  clearKey(provider: ByokProvider): void {
    const data = this.readFile()
    if (!(provider in data) && !(provider in (data.enrolledFingerprints ?? {}))) return
    delete data[provider]
    if (data.enrolledFingerprints) {
      delete data.enrolledFingerprints[provider]
      if (Object.keys(data.enrolledFingerprints).length === 0) delete data.enrolledFingerprints
    }
    this.writeFile(data)
  }

  clearCodexKey(): void {
    const data = this.readFile()
    if (!('codex' in data) && data.codexMigrationComplete) return
    delete data.codex
    data.codexMigrationComplete = true
    this.writeFile(data)
  }

  /** Remove all stored keys (deletes the backing file). */
  clearAll(): void {
    try {
      this.migrateLegacyCodexKey()
      const data = this.readFile()
      for (const provider of BYOK_PROVIDERS) delete data[provider]
      delete data.enrolledFingerprints
      if (Object.keys(data).length === 0) rmSync(this.filePath, { force: true })
      else this.writeFile(data)
    } catch {
      /* best-effort */
    }
  }

  /**
   * Persist the fingerprint set the backend currently enforces. An empty map
   * removes the stored evidence entirely (deactivated).
   */
  setEnrolledFingerprints(fingerprints: ByokEnrolledFingerprints): void {
    const data = this.readFile()
    if (Object.keys(fingerprints).length === 0) delete data.enrolledFingerprints
    else data.enrolledFingerprints = { ...fingerprints }
    this.writeFile(data)
  }

  getEnrolledFingerprints(): ByokEnrolledFingerprints {
    return { ...(this.readFile().enrolledFingerprints ?? {}) }
  }

  clearEnrolledFingerprints(): void {
    const data = this.readFile()
    if (!data.enrolledFingerprints) return
    delete data.enrolledFingerprints
    if (Object.keys(data).length === 0) rmSync(this.filePath, { force: true })
    else this.writeFile(data)
  }

  /**
   * Providers whose CURRENT stored key hash matches the enrolled fingerprint —
   * i.e. capabilities validated by the backend and not rotated since. A key
   * edited after the last enrollment drops out until it re-enrolls.
   */
  validatedProviders(): ByokProvider[] {
    const enrolled = this.readFile().enrolledFingerprints ?? {}
    const out: ByokProvider[] = []
    for (const provider of BYOK_PROVIDERS) {
      const fp = enrolled[provider]
      const key = this.getKey(provider)
      if (fp && key && byokFingerprint(key) === fp) out.push(provider)
    }
    return out
  }

  /** True when a configured LLM provider has a stored key. */
  isActive(): boolean {
    return isByokActive(this.getAllKeys())
  }
}
