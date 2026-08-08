/**
 * Composition root: binds the MCP protocol seam to the deterministic QA store.
 *
 * `apps/mcp/protocol.ts` is a ports-and-adapters seam and `apps/service/app.ts`
 * is a runtime-neutral Hono shell. Neither binds a port; the only `Bun.serve`
 * in the tree before this file lived inside a test. This module supplies the
 * seven ports the protocol requires so a real socket can be opened.
 *
 * Every page emitted here is validated by the **vendored ratified contract**
 * (`@omi-core/ratified-contracts` 0.1.1, content-pinned by contracts.lock.json)
 * before it reaches the wire — the same validator the corpora classify against.
 * So a page this server emits is, by construction, a page the ratified
 * validator accepts; and the conformance runner separately proves the corpus's
 * *negative* cases can never be produced.
 */

import {
  parseSynthesizedPageJson,
  SYNTHESIZED_READ_CONTRACT_VERSION,
} from "@omi-core/ratified-contracts/projections/synthesized";

import {
  asOpaqueVisibleKeyset,
  InvalidMcpCursorError,
  issueMcpCursor,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "../../apps/mcp/cursor";
import type {
  AuthorizationDecision,
  McpCredential,
  McpProtocolPorts,
} from "../../apps/mcp/protocol";
import { SYNTHESIZED_MEMORY_READ_SCOPE } from "../../apps/mcp/protocol";

import { FIXTURE_ANCHOR_EPOCH_SECONDS } from "./fixture-clock";
import { fixtureDigest, QaStore, UnknownVisibleKeyError } from "./qa-store";

/**
 * QA-only dev credentials. Local loopback runtime only (board ruling PR-4):
 * no cloud, no real issuer, no production credential ever reaches this file.
 */
export interface QaCredentialTable {
  readonly [apiKey: string]: {
    readonly ownerId: string;
    readonly scopes: readonly string[];
  };
}

export const DEFAULT_QA_CREDENTIALS: QaCredentialTable = Object.freeze({
  "omi-integration-qa-key-v1": Object.freeze({
    ownerId: "qa-owner-1",
    scopes: Object.freeze([SYNTHESIZED_MEMORY_READ_SCOPE]),
  }),
  // A second identity with the same scope, so the harness can prove a cursor
  // minted for one owner is rejected for another.
  "omi-integration-qa-key-v2": Object.freeze({
    ownerId: "qa-owner-2",
    scopes: Object.freeze([SYNTHESIZED_MEMORY_READ_SCOPE]),
  }),
  // Authenticates successfully but holds no read scope: proves the "hidden
  // tool" path is byte-identical to the "unknown tool" path.
  "omi-integration-qa-key-noscope": Object.freeze({
    ownerId: "qa-owner-3",
    scopes: Object.freeze([]),
  }),
});

const SIGNING_KEYSET: McpCursorSigningKeyset = Object.freeze({
  active_key_id: "qa-cursor-key-1",
  // Deterministic QA secret. 32 bytes, fixed — never a production secret.
  keys: Object.freeze([
    Object.freeze({
      key_id: "qa-cursor-key-1",
      secret: new Uint8Array(Buffer.from(fixtureDigest("cursor-secret"), "hex")).slice(0, 32),
    }),
  ]),
});

const CURSOR_TTL_SECONDS = 3_600;

/** The 15-field cursor binding. `owner_digest` is what fences cursors per identity. */
function bindingsFor(ownerId: string): McpCursorBindings {
  return Object.freeze({
    owner_digest: fixtureDigest(`owner:${ownerId}`),
    app_digest: fixtureDigest("app"),
    credential_key_digest: fixtureDigest("credential"),
    authorization_generation_digest: fixtureDigest("authorization-generation"),
    grant_generation_digest: fixtureDigest("grant-generation"),
    account_generation_digest: fixtureDigest("account-generation"),
    graph_generation_digest: fixtureDigest("graph-generation"),
    projection_generation_digest: fixtureDigest("projection-generation"),
    projection_commit_digest: fixtureDigest("projection-commit"),
    visibility_digest: fixtureDigest("visibility"),
    filter_digest: fixtureDigest("filter"),
    query_digest: fixtureDigest("query"),
    cursor_policy_digest: fixtureDigest("cursor-policy"),
    source_digest: fixtureDigest("source"),
    read_mode_digest: fixtureDigest("read-mode"),
  });
}

export interface QaPortsOptions {
  readonly store: QaStore;
  readonly credentials?: QaCredentialTable;
  readonly allowedOrigins?: readonly string[];
}

interface ReadAuthorization {
  readonly ownerId: string;
}

export function createQaPorts(options: QaPortsOptions): McpProtocolPorts {
  const store = options.store;
  const credentials = options.credentials ?? DEFAULT_QA_CREDENTIALS;
  const allowedOrigins = new Set(
    options.allowedOrigins ?? [
      "http://127.0.0.1:4852",
      "http://localhost:4852",
      "http://127.0.0.1:4851",
    ],
  );

  return {
    validateOrigin(input) {
      return allowedOrigins.has(input.origin);
    },

    authenticate(input) {
      const raw = input.apiKeyHeader;
      if (raw === undefined) {
        return null;
      }
      const token = raw.startsWith("Bearer ") ? raw.slice("Bearer ".length) : raw;
      const record = Object.prototype.hasOwnProperty.call(credentials, token)
        ? credentials[token]
        : undefined;
      if (record === undefined) {
        return null;
      }
      const credential: McpCredential = {
        kind: "mcp_api_key",
        scopes: record.scopes,
        rateLimitKey: {
          prefix: "mcp",
          uid: record.ownerId,
          app_id: "omi-integration-harness",
          key_id: token,
        },
        authentication: { ownerId: record.ownerId },
      };
      return credential;
    },

    authorize(input): AuthorizationDecision {
      const authentication = input.credential.authentication as { ownerId?: unknown };
      const ownerId = typeof authentication?.ownerId === "string" ? authentication.ownerId : null;
      if (ownerId === null) {
        return { allowed: false };
      }
      const readAuthorization: ReadAuthorization = { ownerId };
      return { allowed: true, readAuthorization };
    },

    rateLimit() {
      // Deliberately permissive: this harness proves contract conformance, not
      // rate-limit tuning. A restrictive limiter here would turn conformance
      // failures into rate-limit noise and hide the thing under test.
      return Promise.resolve({ allowed: true as const });
    },

    async readPage(input) {
      const authorization = input.authorization as ReadAuthorization | undefined;
      const ownerId = authorization?.ownerId;
      if (typeof ownerId !== "string") {
        throw new Error("missing read authorization");
      }

      let lastVisibleKey: string | null = null;
      if (input.cursor !== null) {
        // Cursor verification is the server's job, and a cursor minted under a
        // different owner's bindings must not verify here.
        const claims = verifyMcpCursor(
          input.cursor,
          { bindings: bindingsFor(ownerId), now_epoch_seconds: FIXTURE_ANCHOR_EPOCH_SECONDS },
          SIGNING_KEYSET,
        );
        lastVisibleKey = claims.last_visible_key;
      }

      let result;
      try {
        result = store.read({ ownerId, lastVisibleKey, limit: input.limit });
      } catch (caught) {
        if (caught instanceof UnknownVisibleKeyError) {
          throw new InvalidMcpCursorError();
        }
        throw caught;
      }

      return buildPage(result, ownerId);
    },

    validatePage(page) {
      // Canonical JSON, then the ratified validator. Returning null (rather
      // than a page) is what the protocol translates into an error envelope.
      const json = JSON.stringify(page);
      if (typeof json !== "string") {
        return null;
      }
      return parseSynthesizedPageJson(json) === null ? null : json;
    },

    reauthorizeBeforeEmission() {
      return Promise.resolve(true);
    },
  };
}

function buildPage(
  result: { rows: readonly { id: string; text: string }[]; hasMore: boolean; nextVisibleKey: string | null },
  ownerId: string,
): unknown {
  const items = result.rows.map((row) => ({
    id: row.id,
    text: row.text,
    citations: [`citation-v1:${row.id}`],
    provenance: {
      synthesisVersion: "v1",
      inputDigest: fixtureDigest(`input:${row.id}`),
      outputDigest: fixtureDigest(`output:${row.id}`),
    },
  }));

  if (result.hasMore && result.nextVisibleKey !== null) {
    const cursor = issueMcpCursor(
      {
        last_visible_key: asOpaqueVisibleKeyset(result.nextVisibleKey),
        bindings: bindingsFor(ownerId),
        issued_at_epoch_seconds: FIXTURE_ANCHOR_EPOCH_SECONDS,
        ttl_seconds: CURSOR_TTL_SECONDS,
      },
      SIGNING_KEYSET,
    );
    return {
      contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
      items,
      window: { status: "more", complete: false, hasMore: true, nextCursor: cursor },
      completeness: completeBlock(),
      absence: null,
    };
  }

  // Terminal page. `complete: true` is only correct because the QA store reads
  // an unfiltered visible set to exhaustion — see qa-store.ts property (3).
  return {
    contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
    items,
    window: { status: "complete", complete: true, hasMore: false, nextCursor: null },
    completeness: completeBlock(),
    absence: items.length === 0 ? { kind: "query_gap" } : null,
  };
}

function completeBlock(): unknown {
  return {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "frontier-v1:declared",
      newestSearchedAcceptedFrontier: "frontier-v1:declared",
      missingAcceptedFrontierReason: null,
      newestSearchedStmFrontier: "frontier-v1:included",
      missingStmFrontierReason: null,
    },
  };
}
