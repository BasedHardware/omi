// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMX-002)
import { Database } from "bun:sqlite";

import type { SqliteQaRecallLimits } from "../../drivers/sqlite/application-recall-read";
import type { ContentSafeRecallTrace } from "../../core/retrieve/recall-integrity";
import { createBunMcpHttpHandler } from "../mcp/bun-http";
import { createMcpProtocolHandler } from "../mcp/protocol";
import type { McpCursorSigningKeyset } from "../mcp/cursor";
import { createServiceApp } from "../service/app";
import { QA_CODEC_SECRET } from "./codec-scope";
import { createQaDevAuthRegistry, type QaPrincipal } from "./dev-auth";
import { createQaMcpPorts } from "./mcp-ports";
import { createQaRecallReader, type QaRecallReader } from "./recall-service";
import { seedQaSnapshot } from "./seed";

/**
 * The QA localhost server: Hono shell -> Bun MCP adapter -> MCP protocol ->
 * QA ports -> application read -> SQLite QA snapshot.
 *
 * Loopback only, dev-issued tokens, deterministic seed, hermetic clock. This is
 * a QA surface; it selects no production runtime, bind policy, or identity
 * provider, and SQLite here is never a production authority.
 */

/** BE-FLOW's allocation from the board's port registry. Never another agent's. */
export const QA_DEFAULT_PORT = 4801;
export const QA_LOOPBACK_HOSTNAME = "127.0.0.1";

export interface QaServerOptions {
  readonly port?: number;
  readonly owner_account_id?: string;
  readonly app_id?: string;
  readonly key_id?: string;
  readonly token?: string;
  readonly claim_count?: number;
  /** Logical indices seeded invisible-but-present. See seed.ts. */
  readonly hidden_indices?: readonly number[];
  /** Physical row insertion order; content is identical either way. */
  readonly insertion_order?: "ascending" | "descending";
  readonly account_timezone?: string;
  readonly limits?: SqliteQaRecallLimits;
  readonly read_timestamp_epoch_seconds?: number;
  readonly signing_keyset?: McpCursorSigningKeyset;
  /** Extra origins beyond the loopback default. */
  readonly allowed_origins?: readonly string[];
  /**
   * Invoked when the application read emits its trace — i.e. after the page
   * bytes exist but before the protocol's final pre-emission reauthorization.
   *
   * This is the only place a test can land a genuinely mid-flow revocation. A
   * grant revoked before the request is caught by the visibility gate, which
   * never reaches the final fence, so without this hook the fence can only be
   * asserted to exist and never observed refusing.
   */
  readonly onTraceEmitted?: () => void;
  /** Default item granularity for this server. Explicit, never transport-implied. */
  // domain-pending(DIV-DOMCORE-008)
  readonly granularity?: "temporal_leaf" | "all_nodes";
}

export interface QaServer {
  readonly url: string;
  readonly port: number;
  readonly token: string;
  readonly principal: QaPrincipal;
  readonly registry: ReturnType<typeof createQaDevAuthRegistry>;
  readonly reader: QaRecallReader;
  readonly traces: () => readonly ContentSafeRecallTrace[];
  readonly telemetry: () => readonly Readonly<Record<string, unknown>>[];
  readonly counters: () => Readonly<Record<string, number>>;
  readonly stop: () => Promise<void>;
}

const DEFAULT_KEYSET: McpCursorSigningKeyset = Object.freeze({
  active_key_id: "qa-local-key-1",
  // A fixed QA secret. This is deliberately not a credential: the server binds
  // loopback only and issues its own dev tokens. Nothing here is a production
  // key, and no production key may ever be placed here.
  keys: Object.freeze([Object.freeze({
    key_id: "qa-local-key-1",
    secret: new Uint8Array(32).fill(0x5a),
  })]),
});

export const startQaServer = async (options: QaServerOptions = {}): Promise<QaServer> => {
  const port = options.port ?? QA_DEFAULT_PORT;
  const ownerAccountId = options.owner_account_id ?? "owner:qa-local";
  const appId = options.app_id ?? "app:qa-local";
  const keyId = options.key_id ?? "key:qa-local";
  const token = options.token ?? "qa_local_dev_token";
  const accountTimezone = options.account_timezone ?? "UTC";
  const claimCount = options.claim_count ?? 5;
  const readTimestamp = options.read_timestamp_epoch_seconds ?? 1_800_000_000;

  const db = new Database(":memory:");
  seedQaSnapshot(db, {
    owner_account_id: ownerAccountId,
    account_timezone: accountTimezone,
    claim_count: claimCount,
    ...(options.hidden_indices === undefined ? {} : { hidden_indices: options.hidden_indices }),
    ...(options.insertion_order === undefined ? {} : { insertion_order: options.insertion_order }),
  });

  const principal: QaPrincipal = Object.freeze({
    owner_account_id: ownerAccountId,
    app_id: appId,
    key_id: keyId,
    scopes: Object.freeze(["memories.read"]),
  });

  const registry = createQaDevAuthRegistry();
  registry.register(principal, token);

  const traces: ContentSafeRecallTrace[] = [];
  const telemetry: Readonly<Record<string, unknown>>[] = [];

  const reader = createQaRecallReader({
    db,
    principal: {
      owner_account_id: ownerAccountId,
      app_id: appId,
      key_id: keyId,
    },
    account_timezone: accountTimezone,
    limits: options.limits ?? { max_items: 256, max_bytes: 4_000_000 },
    // Key material only. Reader SCOPING is derived by the shared composition
    // from the authorization boundary's `principal_digest`, so the two doors
    // cannot scope the same reader differently — which is what used to give the
    // same memory different public ids while every node-level cross-door
    // assertion kept passing.
    codec_root_secret: QA_CODEC_SECRET,
    cursor_signing_keyset: options.signing_keyset ?? DEFAULT_KEYSET,
    authorization: {
      resolveAuthorizationRequest: () => ({
        owner_account_id: ownerAccountId,
        credential: registry.resolveCredential(principal),
        persisted_grant: registry.resolveGrant(principal),
      }),
    },
    read_timestamp_epoch_seconds: readTimestamp,
    ...(options.granularity === undefined ? {} : { granularity: options.granularity }),
    traceSink: (trace) => {
      traces.push(trace);
      options.onTraceEmitted?.();
    },
  });
  await reader.refresh();

  // Resolved after bind: with port 0 the real port is not known until Bun.serve
  // returns, and an allow-list naming the wrong port would either reject every
  // request or, worse, be quietly widened to compensate.
  let boundPort = port;
  const handle = createQaMcpPorts({
    registry,
    principal,
    reader,
    allowed_origins: () => [
      `http://${QA_LOOPBACK_HOSTNAME}:${boundPort}`,
      `http://localhost:${boundPort}`,
      ...(options.allowed_origins ?? []),
    ],
    telemetrySink: (event) => { telemetry.push(event); },
  });

  const app = createServiceApp(createBunMcpHttpHandler(createMcpProtocolHandler(handle.ports)));

  const server = Bun.serve({
    // Loopback only. Never 0.0.0.0: this surface has dev-issued tokens and a
    // deterministic seed, and must not be reachable from the LAN. The bind is
    // asserted, not assumed -- see apps/qa/loopback.ts.
    hostname: QA_LOOPBACK_HOSTNAME,
    port,
    fetch: app.fetch,
  });
  boundPort = server.port;

  return Object.freeze({
    url: `http://${QA_LOOPBACK_HOSTNAME}:${server.port}`,
    port: server.port,
    token,
    principal,
    registry,
    reader,
    traces: () => Object.freeze([...traces]),
    telemetry: () => Object.freeze([...telemetry]),
    counters: () => Object.freeze({ ...reader.counters(), ...handle.counters() }),
    stop: async () => { await server.stop(true); },
  });
};
