/**
 * THE composition root for the folders read path.
 *
 * ONE CONSTRUCTION SITE for `FoldersReadPorts`, registered in
 * `scripts/lint-import-graph.ts`'s `PORT_REGISTRY`. Same discipline as
 * conversations: HMAC keyset cursor over ingest sequence, coverage declared
 * never counted, item ids are storage ids already served.
 *
 * `revision` is always null — the folders store has no state_revision today,
 * and inventing one here would be a parallel convention. Dangling folder
 * references on conversations are legal; this read does not invent a default
 * folder to close them.
 *
 * A record that will not project fails the whole page closed.
 *
 * Hermetic: no wall clock, no randomness, no I/O.
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
import type { FoldersStore, OrderedFolderRecord } from "../stores/folders-store";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";

export type FoldersReadPortCall =
  | "resolve"
  | "records"
  | "frontier"
  | "verify"
  | "issue";

export type FoldersAppliedFrontierState = "caught_up" | "no_applied_writes" | "lagging";

export interface FoldersReadAuthorization {
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
}

export interface FoldersReadCompositionConfig {
  readonly store: FoldersStore;
  readonly resolveAuthorization: () => FoldersReadAuthorization;
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  readonly cursorTtlSeconds?: number;
  readonly readTimestampEpochSeconds: number;
  readonly appliedFrontierState: FoldersAppliedFrontierState;
  readonly onPortCall?: (call: FoldersReadPortCall) => void;
}

export interface FoldersReadPorts {
  readonly resolveAttempt: () => FoldersReadAuthorization;
  readonly loadOrderedRecords: (accountId: string) => readonly OrderedFolderRecord[];
  readonly encodeFrontier: (internalFrontier: string) => string;
  readonly encodeVisibleKey: (orderingKey: string) => string;
  readonly issueCursor: (lastVisibleKey: string, bindings: McpCursorBindings) => string;
  readonly verifyCursor: (cursor: string, bindings: McpCursorBindings) => string;
  readonly bindingsFor: (authorization: FoldersReadAuthorization) => McpCursorBindings;
}

export interface PreparedFoldersRead {
  readonly ports: FoldersReadPorts;
  readonly appliedFrontierState: FoldersAppliedFrontierState;
  readonly readTimestampEpochSeconds: number;
}

export interface FoldersPageRequest {
  readonly limit: number;
  readonly cursor: string | null;
}

export interface FoldersPageResult {
  readonly canonical_json: string;
  readonly served: number;
}

export class UnprojectableFolderRecordError extends Error {
  readonly code = "unprojectable_folder_record" as const;
  constructor() {
    super("stored folder record does not satisfy the ratified read model");
    this.name = "UnprojectableFolderRecordError";
  }
}

const digestOf = (label: string, value: unknown): string =>
  createHash("sha256")
    .update(`omi.folders-read-${label}.v1`, "ascii")
    .update("\0", "ascii")
    .update(JSON.stringify(value) ?? "null", "utf8")
    .digest("hex");

const CONTRACT_VERSION = "1.0.0" as const;
const COMPLETENESS_VERSION = "folders-completeness-v1" as const;
const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export const prepareFoldersRead = (
  config: FoldersReadCompositionConfig,
): PreparedFoldersRead => {
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

  const bindingsFor = (authorization: FoldersReadAuthorization): McpCursorBindings =>
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
        policy_version: "folders-read-cursor-v1",
        ttl_seconds: cursorTtlSeconds,
      }),
      source_digest: digestOf("source", { sources: ["folders-store"] }),
      read_mode_digest: digestOf("read-mode", { mode: "live_records" }),
    });

  const ports: FoldersReadPorts = {
    resolveAttempt: () => {
      onPortCall("resolve");
      return config.resolveAuthorization();
    },
    loadOrderedRecords: (accountId) => {
      onPortCall("records");
      return config.store.listOrderedFolders(accountId);
    },
    encodeFrontier: (internalFrontier) => {
      onPortCall("frontier");
      return codecs.encodeVisibleKey(`folders:${internalFrontier}`);
    },
    encodeVisibleKey: (orderingKey) => codecs.encodeVisibleKey(`folders:${orderingKey}`),
    issueCursor: (lastVisibleKey, bindings) => {
      onPortCall("issue");
      return issueMcpCursor(
        {
          last_visible_key: asOpaqueVisibleKeyset(
            codecs.encodeVisibleKey(`folders:${lastVisibleKey}`),
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
  });
};

export const readFoldersPage = (
  request: FoldersPageRequest,
  prepared: PreparedFoldersRead,
): FoldersPageResult => {
  if (request.cursor !== null && !isSyntacticallyRedeemableFoldersCursor(request.cursor)) {
    throw new InvalidMcpCursorError();
  }

  const authorization = prepared.ports.resolveAttempt();
  const bindings = prepared.ports.bindingsFor(authorization);
  const records = prepared.ports.loadOrderedRecords(authorization.owner_account_id);

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
  const items = window.map((row) => projectRecord(row.record));

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

const projectRecord = (record: OrderedFolderRecord["record"]): unknown => {
  if (!OPAQUE_REF_PATTERN.test(record.id)) throw new UnprojectableFolderRecordError();
  if (typeof record.name !== "string") throw new UnprojectableFolderRecordError();
  if (record.description !== null && typeof record.description !== "string") {
    throw new UnprojectableFolderRecordError();
  }
  if (typeof record.color !== "string") throw new UnprojectableFolderRecordError();
  if (typeof record.icon !== "string") throw new UnprojectableFolderRecordError();
  if (typeof record.order !== "number" || !Number.isFinite(record.order)) {
    throw new UnprojectableFolderRecordError();
  }
  return {
    id: record.id,
    name: record.name,
    description: record.description,
    color: record.color,
    icon: record.icon,
    createdAt: isoToMs(record.created_at),
    updatedAt: isoToMs(record.updated_at),
    order: record.order,
    isDefault: record.is_default,
    isSystem: record.is_system,
    revision: null,
  };
};

const isoToMs = (value: string): number => {
  const ms = Date.parse(value);
  if (!Number.isSafeInteger(ms)) throw new UnprojectableFolderRecordError();
  return ms;
};

const buildFrontiers = (prepared: PreparedFoldersRead, declaredFrontier: string): unknown => {
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

export const orderingKeyOf = (row: OrderedFolderRecord): string =>
  `${String(row.sequence).padStart(16, "0")}:${row.record.id}`;

export const isSyntacticallyRedeemableFoldersCursor = (cursor: unknown): cursor is string =>
  typeof cursor === "string"
  && cursor.length > 0
  && cursor.length <= MAX_MCP_CURSOR_ENCODED_BYTES
  && /^[\x21-\x7e]+$/.test(cursor);
