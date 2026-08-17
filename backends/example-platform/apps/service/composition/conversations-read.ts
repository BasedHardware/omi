// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
/**
 * THE composition root for the conversations read path.
 *
 * ONE CONSTRUCTION SITE for `ConversationsReadPorts`, registered in
 * `scripts/lint-import-graph.ts`'s `PORT_REGISTRY`. Same discipline as
 * `tasks-read.ts`: one construction, reused HMAC cursor module, coverage
 * DECLARED never counted.
 *
 * Item ids are the storage ids the service already serves — not reader-scoped
 * opaque refs. A platform read and a legacy read of one origin must return the
 * same records. Frontiers and cursor keys still go through `encodeVisibleKey`
 * with a conversations namespace so a cursor minted here cannot be redeemed
 * against another domain.
 *
 * A record that will not project fails the whole page closed. Never drop it,
 * never repair it, never declare a short page complete.
 *
 * Hermetic: no wall clock, no randomness, no I/O. The read timestamp is passed
 * in.
 */

import { createHash } from "node:crypto";

import {
  InvalidMcpCursorError,
  MAX_MCP_CURSOR_ENCODED_BYTES,
  asOpaqueVisibleKeyset,
  issueMcpCursor,
  verifyMcpCursor,
  type McpCursorBindings,
  type McpCursorSigningKeyset,
} from "../../mcp/cursor";
import type {
  ConversationsStore,
  OrderedConversationRecord,
} from "../stores/conversations-store";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";

export type ConversationsReadPortCall =
  | "resolve"
  | "records"
  | "frontier"
  | "verify"
  | "issue";

export type ConversationsAppliedFrontierState =
  | "caught_up"
  | "no_applied_writes"
  | "lagging";

export interface ConversationsReadAuthorization {
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
}

export interface ConversationsReadCompositionConfig {
  readonly store: ConversationsStore;
  readonly resolveAuthorization: () => ConversationsReadAuthorization;
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  readonly cursorTtlSeconds?: number;
  readonly readTimestampEpochSeconds: number;
  readonly appliedFrontierState: ConversationsAppliedFrontierState;
  readonly onPortCall?: (call: ConversationsReadPortCall) => void;
}

export interface ConversationsReadPorts {
  readonly resolveAttempt: () => ConversationsReadAuthorization;
  readonly loadOrderedRecords: (accountId: string) => readonly OrderedConversationRecord[];
  readonly encodeFrontier: (internalFrontier: string) => string;
  readonly encodeVisibleKey: (orderingKey: string) => string;
  readonly issueCursor: (lastVisibleKey: string, bindings: McpCursorBindings) => string;
  readonly verifyCursor: (cursor: string, bindings: McpCursorBindings) => string;
  readonly bindingsFor: (authorization: ConversationsReadAuthorization) => McpCursorBindings;
}

export interface PreparedConversationsRead {
  readonly ports: ConversationsReadPorts;
  readonly appliedFrontierState: ConversationsAppliedFrontierState;
  readonly readTimestampEpochSeconds: number;
  readonly stateRevision: (accountId: string) => number;
}

export interface ConversationsPageRequest {
  readonly limit: number;
  readonly cursor: string | null;
}

export interface ConversationsPageResult {
  readonly canonical_json: string;
  readonly served: number;
}

export class UnprojectableConversationRecordError extends Error {
  readonly code = "unprojectable_conversation_record" as const;
  constructor() {
    super("stored conversation record does not satisfy the ratified read model");
    this.name = "UnprojectableConversationRecordError";
  }
}

const digestOf = (label: string, value: unknown): string =>
  createHash("sha256")
    .update(`omi.conversations-read-${label}.v1`, "ascii")
    .update("\0", "ascii")
    .update(JSON.stringify(value) ?? "null", "utf8")
    .digest("hex");

const CONTRACT_VERSION = "1.0.0" as const;
const COMPLETENESS_VERSION = "conversations-completeness-v1" as const;
const VISIBILITIES = new Set(["public", "private", "shared"]);
const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export const prepareConversationsRead = (
  config: ConversationsReadCompositionConfig,
): PreparedConversationsRead => {
  const onPortCall = config.onPortCall ?? ((): void => {});
  const prepareAuthorization = config.resolveAuthorization();
  const readerProjectionDigest = digestOf("reader", {
    owner: prepareAuthorization.owner_account_id,
    app: prepareAuthorization.app_id,
    key: prepareAuthorization.key_id,
  });
  const codecs = createReaderScopedOpaqueCodecs({
    root_secret: config.codecRootSecret,
    reader_projection_digest: readerProjectionDigest,
  });
  const cursorTtlSeconds = config.cursorTtlSeconds ?? 900;

  const bindingsFor = (authorization: ConversationsReadAuthorization): McpCursorBindings =>
    Object.freeze({
      owner_digest: digestOf("owner", authorization.owner_account_id),
      app_digest: digestOf("app", authorization.app_id),
      credential_key_digest: digestOf("credential", authorization.key_id),
      authorization_generation_digest: digestOf("authorization-generation", {
        owner: authorization.owner_account_id,
        app: authorization.app_id,
        key: authorization.key_id,
      }),
      grant_generation_digest: digestOf("grant-generation", { grant: "dev-local" }),
      account_generation_digest: digestOf("account-generation", authorization.owner_account_id),
      graph_generation_digest: digestOf("graph-generation", authorization.owner_account_id),
      projection_generation_digest: digestOf("projection-generation", {
        applied_frontier: config.appliedFrontierState,
      }),
      projection_commit_digest: digestOf("projection-commit", {
        applied_frontier: config.appliedFrontierState,
      }),
      visibility_digest: digestOf("visibility", { live_records_only: true }),
      filter_digest: digestOf("filter", { filters: [] }),
      query_digest: digestOf("query", { query: null }),
      cursor_policy_digest: digestOf("cursor-policy", {
        policy_version: "conversations-read-cursor-v1",
        ttl_seconds: cursorTtlSeconds,
      }),
      source_digest: digestOf("source", { sources: ["conversations-store"] }),
      read_mode_digest: digestOf("read-mode", { mode: "live_records" }),
    });

  const ports: ConversationsReadPorts = {
    resolveAttempt: () => {
      onPortCall("resolve");
      return config.resolveAuthorization();
    },
    loadOrderedRecords: (accountId) => {
      onPortCall("records");
      return config.store.listOrderedRecords(accountId);
    },
    encodeFrontier: (internalFrontier) => {
      onPortCall("frontier");
      return codecs.encodeVisibleKey(`conversations:${internalFrontier}`);
    },
    encodeVisibleKey: (orderingKey) => codecs.encodeVisibleKey(`conversations:${orderingKey}`),
    issueCursor: (lastVisibleKey, bindings) => {
      onPortCall("issue");
      return issueMcpCursor(
        {
          last_visible_key: asOpaqueVisibleKeyset(
            codecs.encodeVisibleKey(`conversations:${lastVisibleKey}`),
          ),
          bindings,
          issued_at_epoch_seconds: config.readTimestampEpochSeconds,
          ttl_seconds: cursorTtlSeconds,
        },
        config.cursorSigningKeyset,
      );
    },
    verifyCursor: (cursor, bindings) => {
      onPortCall("verify");
      return verifyMcpCursor(
        cursor,
        { bindings, now_epoch_seconds: config.readTimestampEpochSeconds },
        config.cursorSigningKeyset,
      ).last_visible_key;
    },
    bindingsFor,
  };

  return Object.freeze({
    ports,
    appliedFrontierState: config.appliedFrontierState,
    readTimestampEpochSeconds: config.readTimestampEpochSeconds,
    stateRevision: (accountId: string) => config.store.readStateRevision(accountId),
  });
};

export const readConversationsPage = (
  request: ConversationsPageRequest,
  prepared: PreparedConversationsRead,
): ConversationsPageResult => {
  if (request.cursor !== null && !isSyntacticallyRedeemableConversationsCursor(request.cursor)) {
    throw new InvalidMcpCursorError();
  }

  const authorization = prepared.ports.resolveAttempt();
  const bindings = prepared.ports.bindingsFor(authorization);
  const records = prepared.ports.loadOrderedRecords(authorization.owner_account_id);
  const revision = String(prepared.stateRevision(authorization.owner_account_id));

  let startIndex = 0;
  if (request.cursor !== null) {
    const lastVisibleKey = prepared.ports.verifyCursor(request.cursor, bindings);
    const found = records.findIndex(
      (row) => prepared.ports.encodeVisibleKey(orderingKeyOf(row)) === lastVisibleKey,
    );
    if (found < 0) throw new InvalidMcpCursorError();
    startIndex = found + 1;
  }

  const window = records.slice(startIndex, startIndex + request.limit);
  const hasMore = startIndex + window.length < records.length;
  const items = window.map((row) => projectRecord(row.record, revision));

  const declaredFrontier = prepared.ports.encodeFrontier(
    `${authorization.owner_account_id}:declared`,
  );
  const frontiers = buildFrontiers(prepared, declaredFrontier);
  const reasons = prepared.appliedFrontierState === "lagging" ? ["pending_writes"] : [];
  const status = reasons.length > 0 ? "incomplete" : "complete";

  const page = {
    contractVersion: CONTRACT_VERSION,
    items,
    window: hasMore
      ? {
          status: status === "complete" ? "more" : "incomplete",
          complete: false,
          hasMore: true,
          nextCursor: prepared.ports.issueCursor(orderingKeyOf(window[window.length - 1]!), bindings),
        }
      : {
          status: status === "complete" ? "complete" : "incomplete",
          complete: status === "complete",
          hasMore: false,
          nextCursor: null,
        },
    completeness: {
      version: COMPLETENESS_VERSION,
      status,
      reasons,
      frontiers,
    },
    absence: items.length === 0 ? { kind: "query_gap" } : null,
  };

  return { canonical_json: JSON.stringify(page), served: items.length };
};

const projectRecord = (record: OrderedConversationRecord["record"], revision: string): unknown => {
  if (!OPAQUE_REF_PATTERN.test(record.id)) throw new UnprojectableConversationRecordError();
  if (!VISIBILITIES.has(record.visibility)) throw new UnprojectableConversationRecordError();
  if (record.folder_id !== null && typeof record.folder_id !== "string") {
    throw new UnprojectableConversationRecordError();
  }
  return {
    id: record.id,
    title: record.structured.title,
    overview: record.structured.overview,
    createdAt: isoToMs(record.created_at),
    updatedAt: isoToMs(record.updated_at),
    startedAt: isoToMs(record.started_at),
    finishedAt: isoToMs(record.finished_at),
    source: record.source,
    status: record.status,
    discarded: record.discarded,
    starred: record.starred,
    visibility: record.visibility,
    isLocked: record.is_locked,
    folderId: record.folder_id,
    revision,
  };
};

const isoToMs = (value: string): number => {
  const ms = Date.parse(value);
  if (!Number.isSafeInteger(ms)) throw new UnprojectableConversationRecordError();
  return ms;
};

const buildFrontiers = (
  prepared: PreparedConversationsRead,
  declaredFrontier: string,
): unknown => {
  if (prepared.appliedFrontierState === "no_applied_writes") {
    return {
      declaredFrontier,
      newestAppliedFrontier: null,
      missingAppliedFrontierReason: "no_applied_writes",
    };
  }
  if (prepared.appliedFrontierState === "lagging") {
    return {
      declaredFrontier,
      newestAppliedFrontier: prepared.ports.encodeFrontier("applied:behind"),
      missingAppliedFrontierReason: null,
    };
  }
  return {
    declaredFrontier,
    newestAppliedFrontier: declaredFrontier,
    missingAppliedFrontierReason: null,
  };
};

export const orderingKeyOf = (row: OrderedConversationRecord): string =>
  `${String(row.sequence).padStart(16, "0")}:${row.record.id}`;

export const isSyntacticallyRedeemableConversationsCursor = (cursor: unknown): cursor is string =>
  typeof cursor === "string"
  && cursor.length > 0
  && cursor.length <= MAX_MCP_CURSOR_ENCODED_BYTES
  && /^[\x21-\x7e]+$/.test(cursor);
