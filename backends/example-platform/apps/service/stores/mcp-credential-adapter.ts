import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

export const MCP_CREDENTIAL_ADAPTER_VERSION = "mcp-credential-adapter-v1" as const;
export const MCP_LIVE_KEY_SCOPE = "memories.read" as const;

export interface McpKeyRecord {
  readonly version: typeof MCP_CREDENTIAL_ADAPTER_VERSION;
  readonly key_id: string;
  readonly owner_account_id: string;
  readonly application_id: string;
  readonly name: string;
  readonly key_prefix: string;
  readonly secret_hash: string;
  readonly scopes: readonly string[];
  readonly created_at: string;
  readonly last_used_at: string | null;
  readonly revoked: boolean;
  readonly credential_generation: number;
}

export interface McpGrantRecord {
  readonly grant_id: string;
  readonly key_id: string;
  readonly owner_account_id: string;
  readonly capability: string;
  readonly grant_version: number;
  readonly revoked: boolean;
}

export type McpCredentialAdapterOutcome =
  | Readonly<{ kind: "ok"; record: McpKeyRecord }>
  | Readonly<{ kind: "listed"; records: readonly McpKeyRecord[] }>
  | Readonly<{ kind: "granted"; grant: McpGrantRecord }>
  | Readonly<{ kind: "revoked" }>
  | Readonly<{ kind: "wiped"; key_count: number }>
  | Readonly<{ kind: "not_found" }>
  | Readonly<{ kind: "denied" }>;

export interface McpCredentialStore {
  readonly load: (keyId: string) => Promise<McpKeyRecord | null>;
  readonly list: (ownerAccountId: string) => Promise<readonly McpKeyRecord[]>;
  readonly save: (record: McpKeyRecord) => Promise<void>;
  readonly saveGrant: (grant: McpGrantRecord) => Promise<void>;
  readonly loadGrant: (grantId: string) => Promise<McpGrantRecord | null>;
}

export interface McpSecretMint {
  readonly prefix: string;
  readonly secret_hash: string;
}

const fail = (code: string): never => { throw new TypeError(`mcp credential adapter ${code}`); };
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) return fail(code);
  return value;
};

const publicRecord = (record: McpKeyRecord): Omit<McpKeyRecord, "secret_hash"> => {
  const { secret_hash: _secret, ...rest } = record;
  return rest;
};

/**
 * Inert adapter mapping live MCP key/scope/grant/revoke/deletion-wipe policy
 * onto PostgreSQL credential coordinates. It does not mint a new token grammar
 * and does not migrate live Firestore keys.
 */
export const defineMcpCredentialAdapter = (
  store: McpCredentialStore,
  mintSecret: () => McpSecretMint,
): {
  list(context: AuthorizedLedgerWriteContext): Promise<McpCredentialAdapterOutcome>;
  create(
    context: AuthorizedLedgerWriteContext,
    name: string,
    createdAt: string,
  ): Promise<McpCredentialAdapterOutcome>;
  revoke(
    context: AuthorizedLedgerWriteContext,
    keyId: string,
  ): Promise<McpCredentialAdapterOutcome>;
  grant(
    context: AuthorizedLedgerWriteContext,
    keyId: string,
  ): Promise<McpCredentialAdapterOutcome>;
  revokeGrant(
    context: AuthorizedLedgerWriteContext,
    grantId: string,
  ): Promise<McpCredentialAdapterOutcome>;
  wipeForAccountDeletion(
    context: AuthorizedLedgerWriteContext,
  ): Promise<McpCredentialAdapterOutcome>;
} => {
  if (store === null || typeof store !== "object" || Array.isArray(store) || isProxy(store)
    || typeof mintSecret !== "function" || isProxy(mintSecret)) fail("invalid_dependencies");
  const requireOwner = (contextValue: AuthorizedLedgerWriteContext): AuthorizedLedgerWriteContext => {
    const context = assertAuthorizedLedgerWriteContext(contextValue);
    if (context.lifecycle_state !== "active") fail("lifecycle_inactive");
    return context;
  };
  return Object.freeze({
    async list(contextValue) {
      const context = requireOwner(contextValue);
      const records = await store.list(context.account_id);
      return Object.freeze({
        kind: "listed" as const,
        records: Object.freeze(records.filter((record) => !record.revoked).map((record) => {
          const visible = publicRecord(record);
          return Object.freeze({ ...visible, secret_hash: "" });
        })),
      });
    },
    async create(contextValue, name, createdAt) {
      const context = requireOwner(contextValue);
      const minted = mintSecret();
      if (!TOKEN.test(minted.prefix) || !DIGEST.test(minted.secret_hash)) fail("invalid_mint");
      const keyId = `mcpkey:${sha256CanonicalContent({
        contract_version: MCP_CREDENTIAL_ADAPTER_VERSION,
        owner_account_id: context.account_id,
        application_id: context.application_id,
        prefix: minted.prefix,
        created_at: createdAt,
      })}`;
      const record: McpKeyRecord = Object.freeze({
        version: MCP_CREDENTIAL_ADAPTER_VERSION,
        key_id: keyId,
        owner_account_id: context.account_id,
        application_id: context.application_id,
        name: token(name, "invalid_name"),
        key_prefix: minted.prefix,
        secret_hash: minted.secret_hash,
        scopes: Object.freeze([MCP_LIVE_KEY_SCOPE]),
        created_at: token(createdAt, "invalid_created_at"),
        last_used_at: null,
        revoked: false,
        credential_generation: context.credential_generation,
      });
      await store.save(record);
      const grant: McpGrantRecord = Object.freeze({
        grant_id: `mcpgrant:${sha256CanonicalContent({
          contract_version: MCP_CREDENTIAL_ADAPTER_VERSION,
          key_id: keyId,
        })}`,
        key_id: keyId,
        owner_account_id: context.account_id,
        capability: MCP_LIVE_KEY_SCOPE,
        grant_version: 1,
        revoked: false,
      });
      await store.saveGrant(grant);
      return Object.freeze({ kind: "ok" as const, record });
    },
    async revoke(contextValue, keyId) {
      const context = requireOwner(contextValue);
      const existing = await store.load(token(keyId, "invalid_key"));
      if (existing === null || existing.owner_account_id !== context.account_id) {
        return Object.freeze({ kind: "not_found" as const });
      }
      await store.save(Object.freeze({ ...existing, revoked: true }));
      return Object.freeze({ kind: "revoked" as const });
    },
    async grant(contextValue, keyId) {
      const context = requireOwner(contextValue);
      const existing = await store.load(token(keyId, "invalid_key"));
      if (existing === null || existing.owner_account_id !== context.account_id || existing.revoked) {
        return Object.freeze({ kind: "not_found" as const });
      }
      const grant: McpGrantRecord = Object.freeze({
        grant_id: `mcpgrant:${sha256CanonicalContent({
          contract_version: MCP_CREDENTIAL_ADAPTER_VERSION,
          key_id: existing.key_id,
          generation: existing.credential_generation,
        })}`,
        key_id: existing.key_id,
        owner_account_id: context.account_id,
        capability: MCP_LIVE_KEY_SCOPE,
        grant_version: existing.credential_generation,
        revoked: false,
      });
      await store.saveGrant(grant);
      return Object.freeze({ kind: "granted" as const, grant });
    },
    async revokeGrant(contextValue, grantId) {
      const context = requireOwner(contextValue);
      const existing = await store.loadGrant(token(grantId, "invalid_grant"));
      if (existing === null || existing.owner_account_id !== context.account_id) {
        return Object.freeze({ kind: "not_found" as const });
      }
      await store.saveGrant(Object.freeze({ ...existing, revoked: true }));
      return Object.freeze({ kind: "revoked" as const });
    },
    async wipeForAccountDeletion(contextValue) {
      const context = requireOwner(contextValue);
      const records = await store.list(context.account_id);
      for (const record of records) {
        await store.save(Object.freeze({ ...record, revoked: true }));
      }
      return Object.freeze({ kind: "wiped" as const, key_count: records.length });
    },
  });
};
