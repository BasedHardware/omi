// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-006)
import { createHash, timingSafeEqual } from "node:crypto";

import type {
  PersistedApplicationMemoryGrant,
  ResolvedApplicationCredential,
} from "../../core/retrieve/authorization-boundary";
import type { McpCredential } from "../mcp/protocol";

export interface QaPrincipal {
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
  readonly scopes: readonly string[];
}

export interface QaDevAuthRegistry {
  /** Registers a dev API token -> principal. Returns the opaque token. */
  readonly register: (principal: QaPrincipal, token: string) => void;
  /** Header value is the raw `Authorization` header, e.g. "Bearer qa_...". */
  readonly authenticate: (authorizationHeader: string | undefined) => McpCredential | null;
  /** Current credential activity + persisted grant, as the read path needs them. */
  readonly resolveCredential: (principal: QaPrincipal) => ResolvedApplicationCredential;
  readonly resolveGrant: (principal: QaPrincipal) => PersistedApplicationMemoryGrant | null;
  /** Revocation controls used to prove the final authorization fence. */
  readonly revokeCredential: (principal: QaPrincipal) => void;
  readonly revokeGrant: (principal: QaPrincipal) => void;
  readonly restore: (principal: QaPrincipal) => void;
  /** Counts calls so a test can prove the fence was consulted after page build. */
  readonly authorizationChecks: () => number;
}

interface RegistryRecord {
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
  readonly scopes: readonly string[];
  readonly tokenBytes: Buffer;
  /** Opaque non-reversible authentication handle — never the bearer token. */
  readonly authenticationHandle: Readonly<{ readonly digest: string }>;
  credentialActive: boolean;
  grantPresent: boolean;
}

const principalKey = (principal: Pick<QaPrincipal, "owner_account_id" | "app_id" | "key_id">): string =>
  `${principal.owner_account_id}\0${principal.app_id}\0${principal.key_id}`;

/**
 * Constant-time string equality over UTF-8 bytes. Unequal lengths still execute
 * a timingSafeEqual on equal-length buffers so the length check is not a naked
 * early return oracle.
 */
const tokenBytesEqual = (left: Buffer, right: Buffer): boolean => {
  if (left.byteLength !== right.byteLength) {
    timingSafeEqual(left, left);
    return false;
  }
  return timingSafeEqual(left, right);
};

/** Exactly `Bearer <token>` — one space, no leading/trailing header whitespace, no second token. */
const parseBearerToken = (authorizationHeader: string | undefined): string | null => {
  if (typeof authorizationHeader !== "string") return null;
  if (!authorizationHeader.startsWith("Bearer ")) return null;
  const token = authorizationHeader.slice("Bearer ".length);
  if (token.length === 0) return null;
  if (/[\t\n\r ]/.test(token)) return null;
  return token;
};

const freezeScopes = (scopes: readonly string[]): readonly string[] => Object.freeze([...scopes]);

const detachedCredential = (record: RegistryRecord): McpCredential => ({
  kind: "mcp_api_key",
  scopes: freezeScopes(record.scopes),
  rateLimitKey: {
    prefix: "mcp",
    uid: record.owner_account_id,
    // domain-pending(DIV-DOMAPPS-001)
    app_id: record.app_id,
    // domain-pending(DIV-DOMAPPS-006)
    key_id: record.key_id,
  },
  authentication: { digest: record.authenticationHandle.digest },
});

const detachedResolvedCredential = (record: RegistryRecord): ResolvedApplicationCredential => ({
  owner_account_id: record.owner_account_id,
  // domain-pending(DIV-DOMAPPS-006)
  credential_kind: "mcp_api_key",
  // domain-pending(DIV-DOMAPPS-001)
  app_id: record.app_id,
  // domain-pending(DIV-DOMAPPS-006)
  key_id: record.key_id,
  scopes: freezeScopes(record.scopes),
  active: record.credentialActive,
});

// domain-pending(DIV-DOMX-006)
const detachedGrant = (record: RegistryRecord): PersistedApplicationMemoryGrant => ({
  owner_account_id: record.owner_account_id,
  // domain-pending(DIV-DOMAPPS-006)
  consumer: "mcp",
  // domain-pending(DIV-DOMAPPS-001)
  app_id: record.app_id,
  // domain-pending(DIV-DOMAPPS-006)
  key_id: record.key_id,
  enabled: true,
  default_read: true,
  scopes: freezeScopes(record.scopes),
});

/**
 * Handle material derived only from principal identity fields — never from the
 * bearer token — so authentication cannot reverse to the secret.
 *
 * This is an actual SHA-256, not a formatted identity string. A field called
 * `digest` that holds `owner:app:key` in clear text is the kind of thing that
 * reads as safe in review and then gets logged.
 */
const authenticationHandleFor = (principal: QaPrincipal): Readonly<{ readonly digest: string }> =>
  Object.freeze({
    digest: createHash("sha256")
      .update(JSON.stringify([
        "qa-dev-auth-principal-v1",
        principal.owner_account_id,
        principal.app_id,
        principal.key_id,
      ]))
      .digest("hex"),
  });

export const createQaDevAuthRegistry = (): QaDevAuthRegistry => {
  const byPrincipal = new Map<string, RegistryRecord>();
  const records: RegistryRecord[] = [];
  let authorizationCheckCount = 0;

  const requireRecord = (principal: QaPrincipal): RegistryRecord => {
    const record = byPrincipal.get(principalKey(principal));
    if (record === undefined) {
      throw new TypeError("QA dev-auth principal is not registered");
    }
    return record;
  };

  return {
    register(principal, token) {
      if (typeof token !== "string" || token.length === 0 || /[\t\n\r ]/.test(token)) {
        throw new TypeError("QA dev-auth token must be a non-empty string without whitespace");
      }
      const key = principalKey(principal);
      const existing = byPrincipal.get(key);
      const record: RegistryRecord = {
        owner_account_id: principal.owner_account_id,
        app_id: principal.app_id,
        key_id: principal.key_id,
        scopes: freezeScopes(principal.scopes),
        tokenBytes: Buffer.from(token, "utf8"),
        authenticationHandle: authenticationHandleFor(principal),
        credentialActive: true,
        grantPresent: true,
      };
      if (existing !== undefined) {
        const index = records.indexOf(existing);
        if (index >= 0) records[index] = record;
      } else {
        records.push(record);
      }
      byPrincipal.set(key, record);
    },

    authenticate(authorizationHeader) {
      const parsed = parseBearerToken(authorizationHeader);
      // Always walk every registered token so missing/malformed/unknown/revoked
      // share the same comparison work rather than a Map.get timing oracle.
      const candidate = Buffer.from(parsed ?? "", "utf8");
      let matched: RegistryRecord | null = null;
      for (const record of records) {
        if (tokenBytesEqual(candidate, record.tokenBytes)) {
          matched = record;
        }
      }
      if (parsed === null || matched === null || !matched.credentialActive) {
        return null;
      }
      return detachedCredential(matched);
    },

    resolveCredential(principal) {
      const record = requireRecord(principal);
      return detachedResolvedCredential(record);
    },

    resolveGrant(principal) {
      authorizationCheckCount += 1;
      const record = requireRecord(principal);
      if (!record.grantPresent) return null;
      return detachedGrant(record);
    },

    revokeCredential(principal) {
      requireRecord(principal).credentialActive = false;
    },

    revokeGrant(principal) {
      requireRecord(principal).grantPresent = false;
    },

    restore(principal) {
      const record = requireRecord(principal);
      record.credentialActive = true;
      record.grantPresent = true;
    },

    authorizationChecks() {
      return authorizationCheckCount;
    },
  };
};
