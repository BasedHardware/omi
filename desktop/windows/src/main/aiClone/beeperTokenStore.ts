// Track 2 (AI clone) — encrypted-at-rest store for the Beeper Desktop API
// access token. Mirrors mcp/mcpKeyStore.ts and agentKernel/byokStore.ts: one
// JSON file under userData, safeStorage (DPAPI on Windows) ciphertext,
// synchronous file I/O. This is its own file rather than reusing ByokKeyStore
// because Beeper isn't a BYOK model provider — piggybacking on that store
// would tangle an unrelated all-or-nothing BYOK-activation invariant with an
// unrelated credential.
//
// The token is a CREDENTIAL — it is NEVER logged, and never returned to a
// caller that only needs a boolean status (see beeperConnectionStatus-shaped
// callers in ipc/aiClone.ts).

import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'

interface StoredFile {
  /** base64 safeStorage ciphertext of the raw access token. */
  token: string
}

export class BeeperTokenStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'beeper-token.json')
  }

  private requireEncryption(): void {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('Secure storage is unavailable on this system')
    }
  }

  private readFile(): StoredFile | null {
    if (!existsSync(this.filePath)) return null
    try {
      const raw = JSON.parse(readFileSync(this.filePath, 'utf8')) as StoredFile
      return raw && typeof raw.token === 'string' ? raw : null
    } catch {
      return null
    }
  }

  get(): string | null {
    const stored = this.readFile()
    if (!stored) return null
    try {
      this.requireEncryption()
      return safeStorage.decryptString(Buffer.from(stored.token, 'base64'))
    } catch {
      return null
    }
  }

  set(token: string): void {
    this.requireEncryption()
    const ciphertext = safeStorage.encryptString(token).toString('base64')
    writeFileSync(this.filePath, JSON.stringify({ token: ciphertext } satisfies StoredFile), 'utf8')
  }

  clear(): void {
    if (existsSync(this.filePath)) rmSync(this.filePath, { force: true })
  }

  /** Alias for clear(), matching ByokKeyStore/McpKeyStore's clearAll() naming
   *  so main/ipc/db.ts's wipeUserData teardown can treat every user-scoped,
   *  file-backed credential store the same way on sign-out / account switch. */
  clearAll(): void {
    this.clear()
  }

  has(): boolean {
    return this.readFile() !== null
  }
}
