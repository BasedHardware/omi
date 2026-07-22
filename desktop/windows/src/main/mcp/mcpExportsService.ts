// Hosted MCP key lifecycle orchestrator (main process, Electron-free so it
// unit-tests without safeStorage). Sits between the encrypted store
// (mcpKeyStore) and the REST client (mcpMintClient):
//
//   • ensureKey — lazy: reuse the stored key for THIS account, else mint one and
//     persist it. Minting happens on first connect, never at startup.
//   • rotateKey — mint a fresh key, persist it, then best-effort revoke the old
//     one on the backend. Mint-first so a failed mint never leaves us keyless.
//
// The owner-uid guard lives in the store (read(uid) rejects a foreign record), so
// a key minted under account A is never reused for account B here.

import { mintMcpKey, deleteMcpKey, type FetchLike } from './mcpMintClient'
import { MCP_KEY_NAME } from '../../shared/mcpExports'
import type { McpKeyRecord } from './mcpKeyStore'

/** The store surface the service needs — the real McpKeyStore satisfies it. */
export interface McpKeyStoreLike {
  read(ownerUserId: string): McpKeyRecord | null
  write(ownerUserId: string, record: McpKeyRecord): void
  storedId(): string | null
  clearAll(): void
}

export class McpExportsService {
  // In-flight mint per owner, so a rapid double-connect mints ONCE and both
  // callers share the result (no duplicate backend keys).
  private minting = new Map<string, Promise<McpKeyRecord>>()

  constructor(
    private readonly store: McpKeyStoreLike,
    private readonly fetchImpl: FetchLike = fetch
  ) {}

  /** Reuse this account's stored key, or mint + persist one on first use. */
  async ensureKey(ownerUserId: string, token: string, apiBase: string): Promise<McpKeyRecord> {
    const existing = this.store.read(ownerUserId)
    if (existing) return existing
    const inflight = this.minting.get(ownerUserId)
    if (inflight) return inflight
    const promise = (async (): Promise<McpKeyRecord> => {
      const minted = await mintMcpKey(apiBase, token, MCP_KEY_NAME, this.fetchImpl)
      const record: McpKeyRecord = { id: minted.id, name: minted.name, key: minted.key }
      this.store.write(ownerUserId, record)
      return record
    })().finally(() => this.minting.delete(ownerUserId))
    this.minting.set(ownerUserId, promise)
    return promise
  }

  /** True when this account already has a stored key (no network). */
  hasKey(ownerUserId: string): boolean {
    return this.store.read(ownerUserId) !== null
  }

  /** The stored key record for this account (owner-guarded), or null. No network. */
  storedKey(ownerUserId: string): McpKeyRecord | null {
    return this.store.read(ownerUserId)
  }

  /**
   * Mint a fresh key for this account and revoke the prior one. Mint-first: the
   * new key is persisted before the old is revoked, so a mint failure leaves the
   * existing key intact rather than stranding the user with no key.
   */
  async rotateKey(ownerUserId: string, token: string, apiBase: string): Promise<McpKeyRecord> {
    const oldId = this.store.storedId()
    const minted = await mintMcpKey(apiBase, token, MCP_KEY_NAME, this.fetchImpl)
    const record: McpKeyRecord = { id: minted.id, name: minted.name, key: minted.key }
    this.store.write(ownerUserId, record)
    if (oldId && oldId !== record.id) {
      try {
        await deleteMcpKey(apiBase, token, oldId, this.fetchImpl)
      } catch {
        /* best-effort revoke — the new key is already active */
      }
    }
    return record
  }
}
