// Persist the single hosted MCP API key encrypted at rest via Electron
// safeStorage (DPAPI on Windows). Mirrors `agentKernel/byokStore.ts` and
// `integrations/tokenStore.ts`: one JSON file under userData, base64 ciphertext,
// synchronous file I/O. The key is a CREDENTIAL — it is NEVER logged.
//
// OWNER-UID GUARD (the security-critical part): the hosted MCP key is minted for
// a specific Omi account. If account A signs out and account B signs in on the
// same install without a full wipe, B must NEVER be served A's key. So the record
// stores the owner uid alongside the ciphertext, and `read(uid)` returns the key
// ONLY when the stored owner matches the caller's uid — otherwise it clears the
// stale record and returns null (mirrors macOS's memoryExportMCPApiKeyOwnerUserId).
//
// Storage shape (plaintext JSON, encrypted key field):
//   { ownerUserId: "<uid>", id: "<backend key id>", name: "Omi Desktop",
//     key: "<base64 safeStorage ciphertext>" }

import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'

/** A decrypted hosted MCP key plus the metadata needed to rotate/revoke it. */
export interface McpKeyRecord {
  /** Backend key id — used for DELETE /v1/mcp/keys/{id} on rotate/sign-out. */
  id: string
  /** Display name the key was minted under ("Omi Desktop"). */
  name: string
  /** The raw hosted MCP key (secret). */
  key: string
}

/** On-disk shape: owner uid + metadata + base64 safeStorage ciphertext of the key. */
interface StoredFile {
  ownerUserId: string
  id: string
  name: string
  key: string
}

/**
 * Encrypted-at-rest store for the one hosted MCP key. Reads/writes are
 * synchronous, matching `byokStore`/`tokenStore`. Construct with no args for the
 * real userData path, or pass an explicit path in tests.
 */
export class McpKeyStore {
  private readonly filePath: string

  constructor(filePath?: string) {
    this.filePath = filePath ?? join(app.getPath('userData'), 'mcp-key.json')
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
      if (raw && typeof raw === 'object' && raw.ownerUserId && raw.id && raw.key) return raw
      return null
    } catch {
      return null
    }
  }

  /**
   * Decrypt and return the stored key ONLY if it belongs to `ownerUserId`.
   * A record owned by a different account is treated as absent AND cleared, so
   * a prior user's key can never leak to — or be transmitted on behalf of — the
   * current account.
   */
  read(ownerUserId: string): McpKeyRecord | null {
    const stored = this.readFile()
    if (!stored) return null
    if (stored.ownerUserId !== ownerUserId) {
      // Foreign key on this install — drop it rather than serve it.
      this.clearAll()
      return null
    }
    try {
      this.requireEncryption()
      const key = safeStorage.decryptString(Buffer.from(stored.key, 'base64'))
      return { id: stored.id, name: stored.name, key }
    } catch {
      return null
    }
  }

  /** Encrypt and persist the hosted key for `ownerUserId`, replacing any prior record. */
  write(ownerUserId: string, record: McpKeyRecord): void {
    if (!ownerUserId) throw new Error('ownerUserId is required')
    this.requireEncryption()
    const data: StoredFile = {
      ownerUserId,
      id: record.id,
      name: record.name,
      key: safeStorage.encryptString(record.key).toString('base64')
    }
    writeFileSync(this.filePath, JSON.stringify(data), 'utf8')
  }

  /** The backend key id of the stored record (any owner), for revoke-on-rotate. */
  storedId(): string | null {
    return this.readFile()?.id ?? null
  }

  /** True when a key record is present for this exact owner. */
  has(ownerUserId: string): boolean {
    const stored = this.readFile()
    return !!stored && stored.ownerUserId === ownerUserId
  }

  /** Remove the stored key (deletes the backing file). Called on sign-out. */
  clearAll(): void {
    try {
      rmSync(this.filePath, { force: true })
    } catch {
      /* best-effort */
    }
  }
}
