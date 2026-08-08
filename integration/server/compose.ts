/**
 * The integration harness's binding of the **registered** read composition.
 *
 * WHAT THIS FILE USED TO BE, AND WHY IT IS NOT THAT ANY MORE
 * ---------------------------------------------------------
 * Until 2026-08-08 this module built its own `McpProtocolPorts` around a
 * hand-rolled in-memory `QaStore`, and `serve.ts` built its own `/v1/memories`
 * handler on top of it. That made this the THIRD read door in the tree — and
 * the one `make stack` and `HOW-TO-RUN.md` actually boot, so every human
 * impression and every dogfooding session was formed against it.
 *
 * It had drifted, exactly the way wave 1 measured two doors drifting:
 *
 *   - it minted PUBLIC ITEM IDS FROM RAW FIXTURE ROW IDS (`id: row.id`,
 *     `citations: ["citation-v1:" + row.id]`) where the registered composition
 *     mints reader-scoped opaque refs. That is the exact defect class the
 *     wave-1 read-door collapse was built to kill;
 *   - its page builder was a 0.1.1-vintage shape on a 0.2.0+ trunk;
 *   - none of the real route's hardening applied — trailing slash, method,
 *     duplicate query parameters, the fixed `not_found`/`bad_request` bodies,
 *     or the cursor-grammar boundary that closed the 4096/4097 oracle.
 *
 * Ruled by fable 2026-08-08 (W4, `data/run-2026-08-08c/decisions/
 * COORD-fable-rulings-wave2.md`): rebuild on the registered composition with
 * only the ports faked. The hand-rolled read path is RETIRED, not pinned.
 *
 * WHAT IS HARNESS-AUTHORED NOW, PRECISELY
 * ---------------------------------------
 * The fixture (a deterministic SQLite QA snapshot from the shared seeder), the
 * credential table, the origin allow-list, the rate limiter, and the trace
 * sink. Everything from the authorization boundary to the wire bytes —
 * projection, renders, pagination, opaque refs, cursor bindings, completeness,
 * canonical JSON — is `apps/service/composition/memory-read.ts`, the ONE
 * registered composition (rule 16).
 *
 * BOTH DOORS, ONE COMPOSITION, ONE PRINCIPAL IDENTITY
 * ---------------------------------------------------
 * `/v1/memories` and `/mcp` are served from the same fixture through the same
 * composition and — critically — the same `(owner, app_id, key_id)` triple, so
 * the reader-scoped codecs derive the same subkey on both. That is what makes
 * the two doors emit the SAME public item id for the same memory, which is the
 * property wave 1 found violated and `cross-door-identity.test.ts` pins
 * in-process. `integration/adversarial/cross-door-identity.test.ts` pins it on
 * the live wire.
 *
 * SQLite here is QA fixture storage only and is never production authority.
 * Loopback only — board ruling PR-4. No production credential, secret, issuer,
 * store, or deployment topology is selected by this file.
 */

import { Database } from "bun:sqlite";

import {
  devPrincipalToAuthorizationRequest,
  type DevPrincipal,
} from "../../apps/service/auth/dev-token";
import {
  prepareMemoryRead,
  readMemoryPage,
  type CoherentQaLoad,
  type PreparedMemoryRead,
} from "../../apps/service/composition/memory-read";
import { QA_FIXTURE_TIME_ANCHOR_UTC, seedQaSnapshot } from "../../apps/service/qa/seed";
import { createSqliteQaRecallLoader } from "../../drivers/sqlite/application-recall-read";
import { DEFAULT_READ_ITEM_GRANULARITY } from "../../core/retrieve/granularity";
import { ApplicationReadDenied } from "../../core/retrieve/authorization-boundary";
import { isInvalidMcpCursorError, type McpCursorSigningKeyset } from "../../apps/mcp/cursor";
import {
  SYNTHESIZED_MEMORY_READ_SCOPE,
  type AuthorizationDecision,
  type McpCredential,
  type McpProtocolPorts,
} from "../../apps/mcp/protocol";
import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { fixtureSecret } from "./fixture-secret";

/**
 * QA-only dev credentials. Local loopback runtime only (board ruling PR-4):
 * no cloud, no real issuer, no production credential ever reaches this file.
 *
 * The spellings are unchanged from the retired door because `dev-stack.sh`,
 * `HOW-TO-RUN.md` and the cross-side wire-agreement test all hand
 * `omi-integration-qa-key-v1` to a real client as a bearer token.
 */
export interface QaCredentialRecord {
  readonly ownerId: string;
  readonly scopes: readonly string[];
}
export interface QaCredentialTable {
  readonly [apiKey: string]: QaCredentialRecord;
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

/**
 * ONE application/credential identity for both doors.
 *
 * `principal_digest` — the scope of the reader-scoped opaque codecs — covers
 * owner, app and key. If the MCP door keyed on the bearer token while the REST
 * door keyed on a dev key id, the same memory would carry different public ids
 * on the two doors *from the same process*. That is the wave-1 divergence,
 * reproduced. So the triple is a constant of the harness, derived from nothing
 * request-scoped.
 */
const HARNESS_APP_ID = "omi-integration-harness";
const HARNESS_KEY_ID = "omi-integration-harness-key";

/** Deterministic QA fixture secrets. Fixed, never production keys. */
const CODEC_ROOT_SECRET = fixtureSecret("codec-root");
const CURSOR_SIGNING_KEYSET: McpCursorSigningKeyset = Object.freeze({
  active_key_id: "qa-cursor-key-1",
  keys: Object.freeze([
    Object.freeze({ key_id: "qa-cursor-key-1", secret: fixtureSecret("cursor") }),
  ]),
});
const CURSOR_TTL_SECONDS = 3_600;

/**
 * The read timestamp AND the corpus anchor come from the shared QA seeder, not
 * from `fixture-clock.ts`'s 2026-01-15 anchor: the seeded memories step
 * backwards from `QA_FIXTURE_TIME_ANCHOR_UTC`, so a read stamped six months
 * earlier would be reading a snapshot from its own future. `fixture-clock.ts`
 * still owns the TIMEZONE invariant, which is a different question and is still
 * asserted at boot.
 */
const READ_TIMESTAMP_EPOCH_SECONDS = Math.floor(Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC) / 1000);

const RECALL_LIMITS = Object.freeze({ max_items: 512, max_bytes: 4_000_000 });

/** How many memories the fixture holds, and how many of those are hidden-but-present. */
export interface QaFixturePlan {
  /** Memories visible to the application-default projection. */
  readonly visibleCount: number;
  /**
   * Memories seeded as REAL durable rows that the authorization projection then
   * hides (non-generic policy labels). Each shares a local day with a visible
   * one, so the served day-node exists in both fixture worlds and only its
   * membership differs — which is what makes hidden-vs-absent testable on the
   * wire rather than merely asserted.
   */
  readonly hiddenCount: number;
}

export interface QaBackendOptions {
  readonly credentials?: QaCredentialTable;
  readonly accountTimezone?: string;
  readonly allowedOrigins?: readonly string[];
}

export interface QaBackend {
  /** Reseeds every QA owner's corpus. Deterministic; same plan, same bytes. */
  readonly reseed: (plan: QaFixturePlan) => void;
  /** The plan currently seeded. */
  readonly plan: () => QaFixturePlan;
  /** Owner ids the fixture is seeded for. */
  readonly ownerIds: readonly string[];
  /** Bearer token -> principal, for the REST door's `resolvePrincipal` port. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** The registered composition, prepared for one principal. Fresh per request. */
  readonly prepareRead: (principal: DevPrincipal) => Promise<PreparedMemoryRead>;
  /** MCP transport ports. Only the read is shared; the rest are harness fakes. */
  readonly mcpPorts: McpProtocolPorts;
}

const readAuthorizationOwner = (value: unknown): string | null => {
  if (typeof value !== "object" || value === null) return null;
  const owner = (value as { owner_account_id?: unknown }).owner_account_id;
  return typeof owner === "string" && owner.length > 0 ? owner : null;
};

export const createQaBackend = (options: QaBackendOptions = {}): QaBackend => {
  const credentials = options.credentials ?? DEFAULT_QA_CREDENTIALS;
  const accountTimezone = options.accountTimezone ?? "UTC";
  const allowedOrigins = new Set(
    options.allowedOrigins ?? [
      "http://127.0.0.1:4852",
      "http://localhost:4852",
      "http://127.0.0.1:4851",
    ],
  );

  /**
   * ONE DATABASE PER QA OWNER.
   *
   * `seedQaSnapshot` resets the whole snapshot and seeds a single owner, so a
   * shared database could only ever hold one identity's corpus — and the
   * cross-owner cursor proof needs a second identity that can actually read a
   * page and mint a cursor. Separate databases also make the owner fence
   * structural here rather than a filter this harness could get wrong.
   */
  const ownerIds = Object.freeze([
    ...new Set(Object.values(credentials).map((record) => record.ownerId)),
  ]);
  const databases = new Map<string, Database>(
    ownerIds.map((ownerId) => [ownerId, new Database(":memory:")]),
  );

  let currentPlan: QaFixturePlan = { visibleCount: 0, hiddenCount: 0 };

  const reseed = (plan: QaFixturePlan): void => {
    for (const [ownerId, db] of databases) {
      seedQaSnapshot(db, {
        owner_account_id: ownerId,
        memory_count: plan.visibleCount,
        account_timezone: accountTimezone,
        hidden_memory_count: plan.hiddenCount,
      });
    }
    currentPlan = { visibleCount: plan.visibleCount, hiddenCount: plan.hiddenCount };
  };

  const resolvePrincipal = (token: string): DevPrincipal | null => {
    const record = Object.prototype.hasOwnProperty.call(credentials, token)
      ? credentials[token]
      : undefined;
    if (record === undefined) return null;
    // The REST door has one scope and no tool dispatch, so a credential without
    // the read scope is simply not a principal here. The MCP door keeps its own
    // scope check, because there the refusal must be byte-identical to an
    // unknown TOOL rather than to an unknown token.
    if (!record.scopes.includes(SYNTHESIZED_MEMORY_READ_SCOPE)) return null;
    return Object.freeze({ uid: record.ownerId });
  };

  /**
   * THE ONE CALL SITE into the registered composition, for both doors.
   *
   * Prepared FRESH per request, exactly as `apps/service/app-facing.ts` does.
   * A cached prepared read would hide the very thing the concurrent-corpus-
   * change proof is looking at: whether a continuation issued against one
   * snapshot generation is honoured against a different one.
   */
  const prepareRead = async (principal: DevPrincipal): Promise<PreparedMemoryRead> => {
    const db = databases.get(principal.uid);
    if (db === undefined) {
      throw new Error("no QA fixture for this principal");
    }
    const loader = createSqliteQaRecallLoader({
      db,
      owner_account_id: principal.uid,
      account_timezone: accountTimezone,
      limits: RECALL_LIMITS,
      // The seeder owns the whole corpus and writes no accepted work, so
      // "no eligible accepted work" is declared evidence here, not a guess.
      accepted_fixture_state: {
        state: "no_eligible",
        declared_frontier: null,
        searched_frontier: null,
        candidates: [],
      },
    });
    return prepareMemoryRead({
      loadCoherent: loader as unknown as () => CoherentQaLoad,
      // A thunk, not a value: the read core crosses the authorization boundary
      // twice per page, so a grant revoked between the two loads must be seen.
      resolveAuthorization: () => devPrincipalToAuthorizationRequest(principal, {
        app_id: HARNESS_APP_ID,
        key_id: HARNESS_KEY_ID,
      }),
      codecRootSecret: CODEC_ROOT_SECRET,
      cursorSigningKeyset: CURSOR_SIGNING_KEYSET,
      cursorTtlSeconds: CURSOR_TTL_SECONDS,
      // EXPLICIT, never implied by which transport is running.
      granularity: DEFAULT_READ_ITEM_GRANULARITY,
      // DECLARED coverage, not counted at request time. This harness owns its
      // entire fixture: the seeder inserts no accepted work and no STM row, so
      // "no eligible" is true by construction rather than by a row count — and
      // a coverage state derived from a row count would vary with rows the
      // reader is not authorized to see.
      acceptedCoverageState: "no_eligible",
      stmCoverageState: "no_eligible",
      readTimestampEpochSeconds: READ_TIMESTAMP_EPOCH_SECONDS,
      // Opaque references only, and this harness has no reason to retain them.
      traceSink: () => {},
    });
  };

  const mcpPorts: McpProtocolPorts = {
    validateOrigin(input) {
      return allowedOrigins.has(input.origin);
    },

    authenticate(input) {
      const raw = input.apiKeyHeader;
      if (raw === undefined) return Promise.resolve(null);
      const token = raw.startsWith("Bearer ") ? raw.slice("Bearer ".length) : raw;
      const record = Object.prototype.hasOwnProperty.call(credentials, token)
        ? credentials[token]
        : undefined;
      if (record === undefined) return Promise.resolve(null);
      const credential: McpCredential = {
        kind: "mcp_api_key",
        scopes: record.scopes,
        rateLimitKey: {
          prefix: "mcp",
          uid: record.ownerId,
          // Constants, not the bearer token: see HARNESS_APP_ID above. A
          // per-token key here would re-scope the opaque codecs per credential
          // and split one owner's memories across two id spaces.
          app_id: HARNESS_APP_ID,
          key_id: HARNESS_KEY_ID,
        },
        authentication: { owner_account_id: record.ownerId },
      };
      return Promise.resolve(credential);
    },

    authorize(input): Promise<AuthorizationDecision> {
      const owner = readAuthorizationOwner(input.credential.authentication);
      if (owner === null || !input.credential.scopes.includes(SYNTHESIZED_MEMORY_READ_SCOPE)) {
        return Promise.resolve({ allowed: false });
      }
      return Promise.resolve({ allowed: true, readAuthorization: { owner_account_id: owner } });
    },

    rateLimit() {
      // Deliberately permissive: this harness proves contract conformance, not
      // rate-limit tuning. A restrictive limiter here would turn conformance
      // failures into rate-limit noise and hide the thing under test.
      return Promise.resolve({ allowed: true as const });
    },

    async readPage(input) {
      const owner = readAuthorizationOwner(input.authorization);
      if (owner === null) {
        throw new Error("missing read authorization");
      }
      try {
        const prepared = await prepareRead({ uid: owner });
        const result = await readMemoryPage(
          { limit: input.limit, cursor: input.cursor },
          prepared,
        );
        return { canonical_json: result.canonical_json };
      } catch (error) {
        // An invalid cursor is client input and keeps its own public shape,
        // which the transport turns into one invalid-cursor response.
        if (isInvalidMcpCursorError(error)) throw error;
        // A denial landing mid-read emits nothing, and deliberately does NOT
        // become an invalid-cursor response: that would tell an unauthorized
        // caller their cursor was the problem, which is an oracle.
        if (error instanceof ApplicationReadDenied) throw new Error("read denied");
        throw error;
      }
    },

    validatePage(page) {
      // Fail-closed wire boundary: the bytes are re-parsed with the ratified
      // parser here, so a page the contract cannot represent never reaches a
      // client even though the read core already produced it.
      if (page === null || typeof page !== "object") return null;
      const canonical = (page as { canonical_json?: unknown }).canonical_json;
      if (typeof canonical !== "string") return null;
      return parseSynthesizedPageJson(canonical) === null ? null : canonical;
    },

    reauthorizeBeforeEmission() {
      return Promise.resolve(true);
    },
  };

  return Object.freeze({
    reseed,
    plan: () => currentPlan,
    ownerIds,
    resolvePrincipal,
    prepareRead,
    mcpPorts,
  });
};
