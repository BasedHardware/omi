/**
 * THE composition root for the tasks read path.
 *
 * ONE CONSTRUCTION SITE for `TasksReadPorts`, registered in
 * `scripts/lint-import-graph.ts`'s `PORT_REGISTRY`. Rule 16 exists because
 * `ApplicationReadPorts` was built twice — once for the REST door and once for
 * MCP — and the two, both green and both reviewed, served the SAME memory under
 * DIFFERENT public item ids (`mem1_eca59618…` vs `mem1_dd73274c…`) because they
 * keyed the opaque-ref codecs differently. Every node-level cross-door assertion
 * passed the whole time. Tasks is the night's largest new surface and gets one
 * construction site from the start rather than after the second one appears.
 *
 * WHY THIS IS A SEPARATE MODULE FROM `memory-read.ts` (fable, R8, explicitly).
 * "Reuse the registered composition" must NOT be read as serving tasks through
 * `memory-read.ts`: that module is memories-specific down to its vocabulary —
 * renders, granularity, the short-term overlay, accepted work. What rule 16
 * requires reused is one construction site PER DOMAIN PORT TYPE, plus the
 * machinery and the discipline:
 *
 *   - `createReaderScopedOpaqueCodecs`, reused with a tasks domain label and
 *     never forked (`codecs/opaque-refs.ts`);
 *   - the cursor module `apps/mcp/cursor.ts`, reused whole — same signing, same
 *     15-slot binding vocabulary, same single public failure shape;
 *   - the completeness discipline, carried over exactly as `memory-read.ts`'s
 *     comments teach it: coverage is DECLARED, never counted, and every
 *     generation is AUTHORIZATION-SCOPED, never the ledger head.
 *
 * ── THE TWO RULES THIS FILE EXISTS TO HOLD ──────────────────────────────────
 *
 * 1. NO STORAGE COORDINATE REACHES THE WIRE. The store's `record_id` is a
 *    storage-scoped value; the wire carries `encodeTaskItemRef(record_id)`,
 *    which is reader-scoped. Three days before this landed, the QA door was
 *    serving `retrieval-node-v1:seed-0000` — a raw fixture row id — as a public
 *    item id, and the cross-side test was PINNING that leak rather than catching
 *    it. D2 closes the class by construction: the alias `adapters-legacy`
 *    maintains between a local slug and a server id does not cross this wire.
 *
 * 2. COVERAGE IS DECLARED BY THE CALLER, NEVER COMPUTED HERE FROM THE STORE.
 *    A coverage state derived from row counts varies with rows the reader is not
 *    authorized to see, which republishes their existence in a wire-visible
 *    field that no item-level identity test reaches. `memory-read.ts` shipped
 *    that bug once (an STM state derived from an eligible-row count) and a test
 *    caught it; the lesson transfers verbatim.
 *
 * ── THE PROJECTION, AND THE CONSTRAINT OPS STATED ───────────────────────────
 *
 * `stores/tasks-store.ts` says it plainly in its own header: it refuses to know
 * task field semantics (R6 — 0.5.0's field bags are opaque and no ruling exists
 * on task field vocabulary), so "any field of the ratified tasks read model that
 * is not a store-owned fact must come out of the opaque bag ... the projection
 * of bag -> named fields is the change, and it happens in the read composition,
 * not here." This is that projection, and it is deliberately the IDENTITY
 * mapping: bag key `description` is wire field `description`. Nothing else is
 * available and nothing else would let the two sides agree — the client's own
 * write path builds its ops out of the same `Task` field names.
 *
 * TWO fields do NOT come from the bag, because the store owns them: `id` (the
 * opaque encoding of `record_id`) and `revision` (the store's hash chain).
 *
 * WHAT HAPPENS TO A BAG THAT WILL NOT PROJECT — ruled here, blast radius stated,
 * because the alternatives are all worse and one of them is a data-loss path:
 *
 *   The read FAILS CLOSED. A record whose bag does not yield a contract-valid
 *   item makes the whole page unavailable; it is never dropped from `items` and
 *   never patched up with a default.
 *
 *   Rejected: fabricating a value (an invented `completed: false` is the exact
 *   class as the fabricated `locked: false` that `adapters-legacy/src/memories.ts`
 *   documents as a data-loss path — it tells the user something false about
 *   their own record). Rejected: silently omitting the record, which serves a
 *   short page that looks complete — the precise thing the completeness envelope
 *   exists to make impossible. Rejected: declaring a `partial` coverage reason,
 *   because that would assign a load-bearing new MEANING to a ratified reason
 *   code, and doing that unilaterally at night is above this lane's bar.
 *
 *   BLAST RADIUS IF REVERSED: one branch in `projectRecord` plus its test. No
 *   wire byte moves — every alternative serves the same page shape — and no
 *   client behaviour changes, because a client cannot distinguish "this server
 *   fails closed" from "this server had no such record" without a second
 *   observation it does not have.
 *
 * TWO GUARDS FROM FABLE'S R16 BIND THIS FILE, and both are pinned by tests
 * rather than by this comment:
 *
 *   1. NO TEXT HERE CLAIMS AUTHORSHIP OF ANY FIELD. Whether a timestamp is
 *      authored by a client or by a server is field MEANING on a ratified wire,
 *      it is parked for David, and a doc comment asserting it would narrow an
 *      owner signature by prose. This module states types and provenance-within-
 *      the-system (which value came from the bag, which from the store) and
 *      stops there.
 *   2. `first_seen_seq` NEVER PROJECTS INTO `sortOrder`. See the note at the
 *      projection.
 *
 * Everything this module produces is valid under either answer to the parked
 * question, which is why the read wire could be built before it was settled.
 *
 * Hermetic: no wall clock, no randomness, no I/O. The read timestamp is passed
 * in, exactly as `memory-read.ts` takes it, so two reads of one snapshot agree.
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
import type { TasksReadStore, TasksRecord } from "../stores/tasks-store";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";

/** Port-call instrumentation vocabulary. Counts only; carries no content. */
export type TasksReadPortCall = "resolve" | "records" | "item" | "frontier" | "verify" | "issue";

/**
 * DECLARED coverage for the tasks read, supplied by the caller.
 *
 * `applied_frontier` is the caller's statement of how far the projection it is
 * serving has caught up with applied writes. `"caught_up"` means the read covers
 * every write this server has applied; `"no_applied_writes"` means none has ever
 * been applied to this account; `"lagging"` means the projection is behind, and
 * the ratified envelope then carries `pending_writes` and the page is
 * `incomplete`.
 *
 * It is a DECLARATION, not a measurement taken here, and that is the point. A
 * caller may only say `caught_up` when it can establish it from something other
 * than counting rows at request time — which the app-facing binding can, because
 * the write route applies synchronously into the very store this read serves
 * from, so there is no window in which an applied write is missing. It proves
 * that at its own call site rather than asserting it here.
 */
export type TasksAppliedFrontierState = "caught_up" | "no_applied_writes" | "lagging";

export interface TasksReadAuthorization {
  /** The authenticated account. Never taken from a request body or a query. */
  readonly owner_account_id: string;
  readonly app_id: string;
  readonly key_id: string;
}

export interface TasksReadCompositionConfig {
  /** The store's READ interface. OPS owns the module; this is a read-only consumer. */
  readonly store: TasksReadStore;
  /**
   * LIVE authorization, re-resolved per attempt — a thunk, not a value, for the
   * same reason `memory-read.ts` takes one: the REST door once captured one
   * authorization at prepare time and handed the same frozen object to every
   * revalidation, so a grant revoked between the page build and its
   * revalidation was never observed.
   */
  readonly resolveAuthorization: () => TasksReadAuthorization;
  /** HMAC root for the reader-scoped handles. QA-supplied; never a production secret. */
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
  readonly cursorTtlSeconds?: number;
  /** Authoritative read timestamp. Passed in, never read from a clock. */
  readonly readTimestampEpochSeconds: number;
  /** DECLARED, never computed here. See TasksAppliedFrontierState. */
  readonly appliedFrontierState: TasksAppliedFrontierState;
  readonly onPortCall?: (call: TasksReadPortCall) => void;
}

/**
 * The port type this module is the ONE construction site for.
 * `PORT_REGISTRY` in `scripts/lint-import-graph.ts` is what keeps it that way.
 */
export interface TasksReadPorts {
  readonly resolveAttempt: () => TasksReadAuthorization;
  readonly loadRecords: (accountId: string) => readonly TasksRecord[];
  readonly encodeItemRef: (recordId: string) => string;
  readonly encodeFrontier: (internalFrontier: string) => string;
  /**
   * The opaque encoding of a record's ORDERING key — what a cursor actually
   * carries. Reader-scoped like everything else, so a cursor minted for one
   * reader resolves to nothing for another instead of paging their tasks.
   */
  readonly encodeVisibleKey: (orderingKey: string) => string;
  readonly issueCursor: (lastVisibleKey: string, bindings: McpCursorBindings) => string;
  readonly verifyCursor: (cursor: string, bindings: McpCursorBindings) => string;
  readonly bindingsFor: (authorization: TasksReadAuthorization) => McpCursorBindings;
}

export interface PreparedTasksRead {
  readonly ports: TasksReadPorts;
  readonly appliedFrontierState: TasksAppliedFrontierState;
  readonly readTimestampEpochSeconds: number;
}

export interface TasksPageRequest {
  readonly limit: number;
  readonly cursor: string | null;
}

export interface TasksPageResult {
  readonly canonical_json: string;
  readonly served: number;
}

/**
 * Raised when a stored record's opaque bag cannot produce a contract-valid item.
 * Distinct from an invalid cursor because it is a SERVER fault, not a
 * client-controlled one, and the route must not answer them alike: collapsing
 * them would let a caller learn something about stored state from a 400.
 */
export class UnprojectableTaskRecordError extends Error {
  readonly code = "unprojectable_task_record" as const;
  constructor() {
    // No record id, no field name, no count. The message is a constant: an
    // exception message that names what was wrong describes stored state, and
    // this one can reach a log line.
    super("stored task record does not satisfy the ratified read model");
    this.name = "UnprojectableTaskRecordError";
  }
}

const digestOf = (label: string, value: unknown): string =>
  createHash("sha256")
    .update(`omi.tasks-read-${label}.v1`, "ascii")
    .update("\0", "ascii")
    .update(JSON.stringify(value) ?? "null", "utf8")
    .digest("hex");

const CONTRACT_VERSION = "1.0.0" as const;
const COMPLETENESS_VERSION = "tasks-completeness-v1" as const;

export const prepareTasksRead = (config: TasksReadCompositionConfig): PreparedTasksRead => {
  const onPortCall = config.onPortCall ?? ((): void => {});
  const prepareAuthorization = config.resolveAuthorization();

  // The codec scope covers owner/app/key ONLY — deliberately, and this mirrors
  // `memory-read.ts`'s `principal_digest`. It must be stable across a grant
  // change, or revoking and re-granting would renumber every one of a reader's
  // tasks.
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

  /**
   * Every one of the cursor module's 15 binding slots is filled from a
   * tasks-scoped digest.
   *
   * TOTALITY IS THE SECURITY PROPERTY, exactly as `apps/qa/cursor-bindings.ts`
   * states it for the memories door: a slot left constant is a dimension a
   * cursor is NOT bound to, so a cursor minted under one read could be redeemed
   * under a different one. The slots whose memories meaning has no tasks
   * analogue are bound to a constant that NAMES the absence rather than to an
   * empty string, so "this read has no query" is a bound fact rather than a gap.
   */
  const bindingsFor = (authorization: TasksReadAuthorization): McpCursorBindings => Object.freeze({
    owner_digest: digestOf("owner", authorization.owner_account_id),
    app_digest: digestOf("app", authorization.app_id),
    credential_key_digest: digestOf("credential", authorization.key_id),
    authorization_generation_digest: digestOf("authorization-generation", {
      owner: authorization.owner_account_id,
      app: authorization.app_id,
      key: authorization.key_id,
    }),
    grant_generation_digest: digestOf("grant-generation", { grant: "dev-local" }),
    // AUTHORIZATION-SCOPED, never the ledger head. The store is per-account by
    // construction (`listRecords(accountId)` cannot reach another account), so
    // binding the account rather than a global sequence is what keeps a hidden
    // row in another account from moving this reader's cursor.
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
      policy_version: "tasks-read-cursor-v1",
      ttl_seconds: cursorTtlSeconds,
    }),
    source_digest: digestOf("source", { sources: ["tasks-store"] }),
    read_mode_digest: digestOf("read-mode", { mode: "live_records" }),
  });

  const ports: TasksReadPorts = {
    resolveAttempt: () => {
      onPortCall("resolve");
      return config.resolveAuthorization();
    },
    loadRecords: (accountId) => {
      onPortCall("records");
      return config.store.listRecords(accountId);
    },
    encodeItemRef: (recordId) => {
      onPortCall("item");
      return codecs.encodeTaskItemRef(recordId);
    },
    encodeFrontier: (internalFrontier) => {
      onPortCall("frontier");
      return codecs.encodeTaskFrontier(internalFrontier);
    },
    encodeVisibleKey: (orderingKey) => codecs.encodeVisibleKey(orderingKey),
    issueCursor: (lastVisibleKey, bindings) => {
      onPortCall("issue");
      return issueMcpCursor(
        {
          last_visible_key: asOpaqueVisibleKeyset(codecs.encodeVisibleKey(lastVisibleKey)),
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

/**
 * Projects one stored record onto the ratified item.
 *
 * Strict on every field, with no repair anywhere. This is the boundary the
 * store's header hands to this module, and the whole reason a strict validator
 * exists on the contract side is that a wire produced by guesswork is a wire
 * nobody can check.
 */
const projectRecord = (record: TasksRecord, encodeItemRef: (recordId: string) => string): unknown => {
  const bag = record.content;
  const str = (key: string): string => {
    const value = bag[key];
    if (typeof value !== "string") throw new UnprojectableTaskRecordError();
    return value;
  };
  const bool = (key: string): boolean => {
    const value = bag[key];
    if (typeof value !== "boolean") throw new UnprojectableTaskRecordError();
    return value;
  };
  const int = (key: string): number => {
    const value = bag[key];
    if (!Number.isSafeInteger(value)) throw new UnprojectableTaskRecordError();
    return value as number;
  };
  const nullableInt = (key: string): number | null => {
    const value = bag[key];
    if (value === null || value === undefined) return null;
    if (!Number.isSafeInteger(value)) throw new UnprojectableTaskRecordError();
    return value as number;
  };
  const nullableStr = (key: string): string | null => {
    const value = bag[key];
    if (value === null || value === undefined) return null;
    if (typeof value !== "string") throw new UnprojectableTaskRecordError();
    return value;
  };
  const finite = (key: string): number => {
    const value = bag[key];
    if (typeof value !== "number" || !Number.isFinite(value)) throw new UnprojectableTaskRecordError();
    return value;
  };
  const strings = (key: string): readonly string[] => {
    const value = bag[key];
    if (!Array.isArray(value) || !value.every((entry) => typeof entry === "string")) {
      throw new UnprojectableTaskRecordError();
    }
    return [...value] as readonly string[];
  };
  const indentLevel = int("indentLevel");
  if (indentLevel < 0) throw new UnprojectableTaskRecordError();

  // Key ORDER matters: the contract's parse boundary is defined over canonical
  // bytes, and the corpus of record fixes this order. Emitting the thirteen in
  // the domain's declaration order keeps the server's bytes and the corpus's
  // bytes comparable rather than merely equivalent.
  return {
    id: encodeItemRef(record.record_id),
    description: str("description"),
    completed: bool("completed"),
    completedAt: nullableInt("completedAt"),
    dueAt: nullableInt("dueAt"),
    owner: nullableStr("owner"),
    source: str("source"),
    provenance: strings("provenance"),
    // `sortOrder` COMES FROM THE BAG AND NEVER FROM `first_seen_seq` (fable,
    // R16 guard 2). They are different facts: `first_seen_seq` is a
    // store-internal observation of admission order, `sortOrder` is product
    // meaning the user can change. Substituting one for the other would decide
    // by accident the exact question R16 parked for David, and it would look
    // right in every fixture where the two happen to agree. `orderingKeyOf`
    // below is the ONLY place `first_seen_seq` is read, and it feeds the cursor,
    // never an item field. `tasks-read.test.ts` pins the separation.
    sortOrder: finite("sortOrder"),
    indentLevel,
    createdAt: int("createdAt"),
    updatedAt: int("updatedAt"),
    // STORE-OWNED, never from the bag. The store's hash chain is the only thing
    // entitled to state a record's revision.
    revision: record.revision,
  };
};

/**
 * Reads one page of canonical ratified JSON through the prepared ports.
 *
 * The ratified cursor grammar is checked HERE, before the cursor module sees the
 * bytes, in the invalid-cursor currency. `memory-read.ts` documents why: the
 * core raises a plain `TypeError` for an over-long or non-printable cursor, and
 * a `TypeError` reports as an internal error rather than an invalid cursor — so
 * two mutations of one token produced two different public outcomes, which tells
 * an attacker which half of their guess was wrong. Measured on the REST door
 * before it was closed: a 4096-character cursor answered 400, a 4097-character
 * one answered 500.
 */
export const readTasksPage = (request: TasksPageRequest, prepared: PreparedTasksRead): TasksPageResult => {
  if (request.cursor !== null && !isSyntacticallyRedeemableTasksCursor(request.cursor)) {
    throw new InvalidMcpCursorError();
  }

  const authorization = prepared.ports.resolveAttempt();
  const bindings = prepared.ports.bindingsFor(authorization);
  const records = prepared.ports.loadRecords(authorization.owner_account_id);

  let startIndex = 0;
  if (request.cursor !== null) {
    const lastVisibleKey = prepared.ports.verifyCursor(request.cursor, bindings);
    // The cursor carries the opaque encoding of the last served record's
    // ordering key, so resolution is a scan for the matching encoding rather
    // than an offset. An offset would silently skip or repeat rows whenever the
    // set changed between pages; matching the key means a row that disappeared
    // ends the walk honestly instead of shifting everything after it.
    const found = records.findIndex(
      (record) => prepared.ports.encodeVisibleKey(orderingKeyOf(record)) === lastVisibleKey,
    );
    if (found < 0) throw new InvalidMcpCursorError();
    startIndex = found + 1;
  }

  const window = records.slice(startIndex, startIndex + request.limit);
  const hasMore = startIndex + window.length < records.length;
  const items = window.map((record) => projectRecord(record, prepared.ports.encodeItemRef));

  const declaredFrontier = prepared.ports.encodeFrontier(
    `tasks:${authorization.owner_account_id}:declared`,
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
    // An empty page is a CLAIM and must say so. Silence would read as "no tasks
    // exist", which is exactly the sentence a client must never infer.
    absence: items.length === 0 ? { kind: "query_gap" } : null,
  };

  return { canonical_json: JSON.stringify(page), served: items.length };
};

const buildFrontiers = (prepared: PreparedTasksRead, declaredFrontier: string): unknown => {
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
      newestAppliedFrontier: prepared.ports.encodeFrontier("tasks:applied:behind"),
      missingAppliedFrontierReason: null,
    };
  }
  return {
    declaredFrontier,
    newestAppliedFrontier: declaredFrontier,
    missingAppliedFrontierReason: null,
  };
};

/**
 * The record's ordering key — the store-owned total order, never a task field.
 * `first_seen_seq` alone would be ambiguous if two records ever shared one, so
 * the record id is folded in as the tiebreak the store itself pins.
 */
export const orderingKeyOf = (record: TasksRecord): string =>
  `${String(record.first_seen_seq).padStart(16, "0")}:${record.record_id}`;

/** Ratified keyset grammar, checked before the cursor module sees the bytes. */
export const isSyntacticallyRedeemableTasksCursor = (cursor: unknown): cursor is string =>
  typeof cursor === "string"
  && cursor.length > 0
  && cursor.length <= MAX_MCP_CURSOR_ENCODED_BYTES
  && /^[\x21-\x7e]+$/.test(cursor);
