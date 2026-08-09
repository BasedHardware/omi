/**
 * The ratified tasks READ wire.
 *
 * RULING OF RECORD: `DAVID-tasks-read-epoch-and-ci` D1 and D2, signed by David
 * in person on 2026-08-08. D1: the tasks read mirrors the memories read model —
 * reader-scoped **opaque ids**, **cursor pagination**, and a **completeness
 * envelope**. D2: **full field parity**, all thirteen fields
 * `core/contracts/src/domain/tasks.ts` declares, because the point of parity is
 * flip-ability — the surface renders identically off either generation, so
 * `openTasks()` becomes a one-line factory change and the rollback is the same
 * line.
 *
 * WHY THIS IS A SEPARATE MODULE FROM `./projections/synthesized`, and not a
 * generic "domain read" (fable, R8). What rule 16 requires reused is one
 * CONSTRUCTION SITE per domain port type, the opaque-ref codecs, the cursor
 * adapter, and the completeness DISCIPLINE — not one file serving two domains.
 * `SynthesizedMemoryRead` is memories-specific down to its vocabulary (renders,
 * granularity, short-term overlay, accepted work). Serving tasks through it
 * would mean either widening those concepts until they mean nothing or
 * declaring memory-retrieval coverage states on a tasks response, which is a
 * false claim in a wire-visible field. The discipline transfers; the file does
 * not.
 *
 * WHAT IS THE SAME, DELIBERATELY, so the two wires cannot drift in the ways
 * that have already cost this program:
 *
 * - **The item id is an opaque reference, never a `RecordId`.** D2 is explicit:
 *   "`id` is the ratified opaque ref, not the legacy server id. The local slug ↔
 *   server id alias that `adapters-legacy/src/tasks.ts` maintains does not cross
 *   this wire." The QA door was serving `retrieval-node-v1:seed-0000` as a
 *   public item id three days ago and the cross-side test was PINNING the leak
 *   rather than catching it; reader-scoped opaque refs close that class by
 *   construction rather than by care. This module fixes the GRAMMAR (printable
 *   ASCII, bounded); the server owns the keying, and it is reader-scoped there.
 * - **The window is the same four variants** over the same `KeysetCursor`, so a
 *   pagination law proven once holds for both wires.
 * - **The completeness envelope is DECLARED, never counted.** A coverage state
 *   computed from row counts varies with rows the reader is not authorized to
 *   see, which republishes their existence in a field no item-level identity
 *   test reaches. The frontier is authorization-scoped, never the ledger head.
 *
 * WHAT IS DIFFERENT, and why each difference is honest rather than convenient:
 *
 * - The envelope is `tasks-completeness-v1`, not `recall-completeness-v1`.
 *   Tasks have no short-term overlay and no accepted-work queue, so carrying
 *   `newestSearchedStmFrontier` / `newestSearchedAcceptedFrontier` here would
 *   mean answering `no_eligible_stm` forever about a subsystem that has nothing
 *   to do with tasks. Under COORD-contract-evolution-policy §1 a field whose
 *   MEANING differs is a different field even when the shape is identical, so
 *   reusing the spelling would have been the expensive kind of reuse.
 * - Its checkable pair is `newestAppliedFrontier` against `declaredFrontier` —
 *   the direct transposition of the accepted-frontier law onto the concept
 *   tasks actually has. `POST /v1/tasks/ops` applies writes into a projection;
 *   a read whose projection lags an applied op is exactly the `incomplete`
 *   case, and `pending_writes` is that reason. Both values are produced by any
 *   server that serves this wire — nothing here is a reserved frame nobody
 *   emits, which is the shape rule 15 exists for.
 *
 * THE ACCOUNT EPOCH now rides here, as `Page.accountEpoch` — the second of the
 * night's two bumps (fable R9), landed after the non-author ADR-012 §4 check
 * R10 required returned "does not leak". See `accountEpoch` on `PageBase` for
 * the whole of that argument; the paragraph this replaces said it was coming.
 */

import type { KeysetCursor } from "../pagination/cursor.js";
import { isPlainJsonDataGraph, parseCanonicalJson } from "../wire/json.js";

/** Public wire-shape version; package versioning is reviewed separately. */
export const TASKS_READ_CONTRACT_VERSION = "1.0.0" as const;

declare const TaskItemIdBrand: unique symbol;
declare const TaskFrontierBrand: unique symbol;

/**
 * A reader-scoped opaque task handle. It is NOT a `RecordId` and carries no
 * storage vocabulary; two readers of the same task never see the same value.
 */
export type TaskItemId = string & { readonly [TaskItemIdBrand]: true };

/** An opaque, reader-scoped, content-free coverage frontier. */
export type TaskFrontier = string & { readonly [TaskFrontierBrand]: true };

export const MAX_TASKS_PAGE_JSON_CODE_UNITS = 2_000_000;

const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export function parseTaskItemId(raw: string): TaskItemId | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as TaskItemId) : null;
}

export function parseTaskFrontier(raw: string): TaskFrontier | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as TaskFrontier) : null;
}

export declare namespace TaskRead {
  /**
   * The thirteen fields of `core/contracts/src/domain/tasks.ts`, all REQUIRED
   * (D2). Every one is present on every item — an absent key would make the two
   * generations render differently, which is the one thing parity is for.
   *
   * `provenance` here is the TASKS concept ("where the task came from"), a list
   * of source labels. It is unrelated to `SynthesizedMemoryRead.Provenance`,
   * which is synthesis lineage; the two share a word and nothing else.
   */
  interface Item {
    /** Reader-scoped opaque handle. Never a `RecordId`, never a storage id. */
    id: TaskItemId;
    description: string;
    completed: boolean;
    completedAt: number | null;
    dueAt: number | null;
    owner: string | null;
    /** Where the task came from; `assistant` writes carry provenance. */
    source: string;
    provenance: readonly string[];
    sortOrder: number;
    indentLevel: number;
    createdAt: number;
    updatedAt: number;
    /** Server revision of the last write we saw; reconcile compares these. */
    revision: string | null;
  }

  /** Terminal page of the authorized projection. */
  interface CompleteTerminalWindow {
    status: "complete";
    complete: true;
    hasMore: false;
    nextCursor: null;
  }

  interface IncompleteTerminalWindow {
    status: "incomplete";
    complete: false;
    hasMore: false;
    nextCursor: null;
  }

  interface MoreContinuationWindow {
    status: "more";
    complete: false;
    hasMore: true;
    nextCursor: KeysetCursor;
  }

  interface IncompleteContinuationWindow {
    status: "incomplete";
    complete: false;
    hasMore: true;
    nextCursor: KeysetCursor;
  }

  type TerminalWindow = CompleteTerminalWindow | IncompleteTerminalWindow;
  type ContinuationWindow = MoreContinuationWindow | IncompleteContinuationWindow;
  type Window = TerminalWindow | ContinuationWindow;

  /** Applied writes the projection has not caught up with yet. */
  type IncompleteReason = "pending_writes";
  type DegradedReason =
    | "projection_stale"
    | "projection_unavailable"
    | "projection_bypassed";
  type PartialReason =
    | "source_bound"
    | "time_bound"
    | "policy_bound";
  type LimitationReason = IncompleteReason | DegradedReason | PartialReason;

  type MissingAppliedFrontierReason = "no_applied_writes" | LimitationReason;

  interface AppliedFrontier {
    newestAppliedFrontier: TaskFrontier;
    missingAppliedFrontierReason: null;
  }

  interface MissingAppliedFrontier {
    newestAppliedFrontier: null;
    missingAppliedFrontierReason: MissingAppliedFrontierReason;
  }

  type Frontiers = { declaredFrontier: TaskFrontier }
    & (AppliedFrontier | MissingAppliedFrontier);

  type CompleteFrontiers = { declaredFrontier: TaskFrontier }
    & (AppliedFrontier | {
      newestAppliedFrontier: null;
      missingAppliedFrontierReason: "no_applied_writes";
    });

  interface FrontiersShape {
    version: "tasks-completeness-v1";
    frontiers: Frontiers;
  }

  interface CompleteCoverage {
    version: "tasks-completeness-v1";
    status: "complete";
    reasons: readonly [];
    frontiers: CompleteFrontiers;
  }

  interface IncompleteCoverage extends FrontiersShape {
    status: "incomplete";
    reasons: readonly [IncompleteReason | PartialReason, ...(IncompleteReason | PartialReason)[]];
  }

  interface DegradedCoverage extends FrontiersShape {
    status: "degraded";
    reasons: readonly [LimitationReason, ...LimitationReason[]];
  }

  interface PartialCoverage extends FrontiersShape {
    status: "partial";
    reasons: readonly [PartialReason, ...PartialReason[]];
  }

  type Completeness = CompleteCoverage | IncompleteCoverage | DegradedCoverage | PartialCoverage;
  type LimitedCompleteness = IncompleteCoverage | DegradedCoverage | PartialCoverage;

  interface QueryGap {
    kind: "query_gap";
  }

  interface PageBase {
    contractVersion: typeof TASKS_READ_CONTRACT_VERSION;
    items: readonly Item[];
    /**
     * THE ACCOUNT EPOCH — `DAVID-tasks-read-epoch-and-ci` D3, signed by David
     * in person. The generation stamp a client puts on `POST /v1/{domain}/ops`
     * envelopes, so the account-epoch fence can tell a current write from a
     * straggler authored in a superseded generation.
     *
     * WHY IT RIDES HERE AND NOWHERE ELSE. D3 is explicit: no new endpoint, no
     * second auth path, no separate availability signal, no new failure mode a
     * client must handle before it can write — *a client that can read can
     * always write*. Every alternative costs a second thing that can be down,
     * a second thing that can be denied, and a second thing a write path must
     * wait on before it may journal an op.
     *
     * WHY IT IS OPTIONAL, which is what makes this bump `additive` rather than
     * `breaking`. The page predicate is exact-keys, so a REQUIRED sixth key
     * would make every client built against 0.6.0 reject every page a 0.7.0
     * server serves — lockstep deploys, which per-account batched migration
     * cannot do. Optional means: a server that has not been taught the field
     * omits it, a client that has not been taught it ignores it, and neither
     * is broken by the other. `TASKS_READ_CONTRACT_VERSION` therefore does NOT
     * move: bumping it would refuse every existing 1.0.0 page and turn an
     * additive change into a breaking one by accident.
     *
     * WHY IT IS NOT A MIGRATION-PROGRESS ORACLE, checked rather than assumed.
     * `backend:ADR-012` §4 forbids a wire that lets a caller probe migration
     * state. A NON-AUTHOR answered that question in writing before this landed
     * (`AUDIT-adr012-epoch-check.md`, R10's two named questions), and the
     * answer rests on three properties this field does not itself guarantee —
     * so they are written here, where the next person to move this code will
     * read them:
     *
     *   1. The read route resolves the account ONLY from the bearer token. No
     *      caller-supplied account id exists on any read path, so no request
     *      can address an account it lacks authority over. The epoch rides
     *      inside an already-closed channel, exactly like the thirteen fields
     *      beside it.
     *   2. The value is PER-ACCOUNT, read from a per-account control
     *      projection. It is not a fleet counter, so it cannot report anyone
     *      else's progress.
     *   3. Refusals stay epoch-free and byte-identical to an unknown route.
     *      `COORD-fable-rulings-wave2` W1's condition — "the active epoch is
     *      never returned" — is scoped to fence refusal and availability
     *      responses, and reconciles with D3 exactly there: this field is
     *      served only AFTER auth resolves. A diff that leaks it onto a
     *      refusal, an availability body, or any pre-auth surface breaks W1,
     *      not merely this comment.
     *
     * Absent is not zero and must never be read as zero. `0` is a claim about
     * a generation; "I was not told" is the absence of one, and a client that
     * defaults to zero stamps every op with a generation nobody asserted. Use
     * `readTaskPageAccountEpoch`, which returns `null` for absent.
     */
    accountEpoch?: number;
  }

  interface CompleteTerminalPage extends PageBase {
    window: CompleteTerminalWindow;
    completeness: CompleteCoverage;
    absence: QueryGap | null;
  }

  interface CompleteContinuationPage extends PageBase {
    window: MoreContinuationWindow;
    completeness: CompleteCoverage;
    absence: null;
  }

  interface LimitedTerminalPage extends PageBase {
    window: TerminalWindow;
    completeness: LimitedCompleteness;
    absence: QueryGap | null;
  }

  interface LimitedContinuationPage extends PageBase {
    window: ContinuationWindow;
    completeness: LimitedCompleteness;
    absence: null;
  }

  type Page =
    | CompleteTerminalPage
    | CompleteContinuationPage
    | LimitedTerminalPage
    | LimitedContinuationPage;
}

/**
 * Already-parsed trusted-JSON law; use `parseTaskPageJson` for untrusted bytes.
 *
 * Structurally identical to the synthesized window law, on purpose: pagination
 * honesty is not a per-domain question, and two spellings of one law is how the
 * two doors disagreed the last time.
 */
export function isTrustedTaskWindowHonest(window: {
  status: string;
  complete: boolean;
  hasMore: boolean;
  nextCursor: string | null;
}): boolean {
  if (!isPlainJsonDataGraph(window)) return false;
  if (!hasExactKeys(window, ["status", "complete", "hasMore", "nextCursor"])) return false;
  if (window.status === "complete") {
    return window.complete && !window.hasMore && window.nextCursor === null;
  }
  if (window.status === "more") {
    return !window.complete && window.hasMore && window.nextCursor !== null;
  }
  if (window.status === "incomplete") {
    return !window.complete && (window.hasMore ? window.nextCursor !== null : window.nextCursor === null);
  }
  return false;
}

/**
 * Already-parsed trusted-JSON law for the coverage envelope.
 *
 * The two claims this enforces, both of which a plausible implementation gets
 * wrong in the direction of over-claiming:
 *
 * 1. `status` is DERIVED from `reasons` by the fixed precedence
 *    `degraded > incomplete > partial > complete`, never asserted beside them.
 *    A server that lists a limitation and then declares `complete` is refused.
 * 2. `complete` requires the applied frontier to have reached the declared one,
 *    or to say plainly that no write has ever been applied. "We covered
 *    everything" is a checkable claim here, not an adjective.
 */
export function isTrustedTaskCompletenessHonest(page: {
  items: readonly unknown[];
  completeness?: {
    version?: string;
    status?: string;
    reasons?: readonly string[];
    frontiers?: {
      declaredFrontier?: string;
      newestAppliedFrontier?: string | null;
      missingAppliedFrontierReason?: string | null;
    };
  };
  absence?: { kind?: string } | null;
}): boolean {
  if (!isPlainJsonDataGraph(page)) return false;
  if (!hasExactKeys(page, ["items", "completeness", "absence"])
    && !hasExactKeys(page, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const completeness = page.completeness;
  if (!completeness || completeness.version !== "tasks-completeness-v1") return false;
  if (!hasExactKeys(completeness, ["version", "status", "reasons", "frontiers"])) return false;
  const { frontiers } = completeness;
  if (!frontiers || !OPAQUE_REF_PATTERN.test(frontiers.declaredFrontier ?? "")) return false;
  if (!hasExactKeys(frontiers, [
    "declaredFrontier",
    "newestAppliedFrontier",
    "missingAppliedFrontierReason",
  ])) return false;
  const applied = frontiers.newestAppliedFrontier;
  const missingApplied = frontiers.missingAppliedFrontierReason;
  if (applied === null) {
    if (!isMissingAppliedFrontierReason(missingApplied)) return false;
  } else if (!OPAQUE_REF_PATTERN.test(applied ?? "") || missingApplied !== null) {
    return false;
  }

  const reasons = completeness.reasons;
  if (!Array.isArray(reasons)) return false;
  if (new Set(reasons).size !== reasons.length) return false;
  const derivedStatus = deriveCompletenessStatus(reasons);
  if (derivedStatus === null || completeness.status !== derivedStatus) return false;

  // The applied frontier and the reason list must tell the same story. A server
  // whose projection lags an applied write and whose reason list omits
  // `pending_writes` is claiming coverage it does not have; one that lists
  // `pending_writes` while its frontiers say it is caught up is claiming a
  // limitation it does not have. Both are refused.
  const pendingWrites = applied === null
    ? missingApplied === "pending_writes"
    : applied !== frontiers.declaredFrontier;
  if (pendingWrites !== reasons.includes("pending_writes")) return false;
  if (completeness.status === "complete"
    && applied !== frontiers.declaredFrontier
    && missingApplied !== "no_applied_writes") return false;
  if (applied === null && isLimitationReason(missingApplied) && !reasons.includes(missingApplied)) return false;

  const hasItems = page.items.length > 0;
  if (hasItems) return page.absence === null;
  if (!hasExactKeys(page.absence, ["kind"]) || page.absence.kind !== "query_gap") return false;
  return completeness.status === "complete" || reasons.length > 0;
}

const LIMITATION_REASONS = new Set([
  "pending_writes",
  "projection_stale",
  "projection_unavailable",
  "projection_bypassed",
  "source_bound",
  "time_bound",
  "policy_bound",
]);

const DEGRADED_REASONS: ReadonlySet<unknown> = new Set(["projection_stale", "projection_unavailable", "projection_bypassed"]);
const PARTIAL_REASONS: ReadonlySet<unknown> = new Set(["source_bound", "time_bound", "policy_bound"]);

function deriveCompletenessStatus(reasons: readonly unknown[]): "degraded" | "incomplete" | "partial" | "complete" | null {
  let degraded = false;
  let incomplete = false;
  let partial = false;
  for (const reason of reasons) {
    if (!isLimitationReason(reason)) return null;
    if (DEGRADED_REASONS.has(reason)) degraded = true;
    else if (reason === "pending_writes") incomplete = true;
    else if (PARTIAL_REASONS.has(reason)) partial = true;
  }
  if (degraded) return "degraded";
  if (incomplete) return "incomplete";
  if (partial) return "partial";
  return "complete";
}

function isLimitationReason(value: unknown): boolean {
  return typeof value === "string" && LIMITATION_REASONS.has(value);
}

function isMissingAppliedFrontierReason(value: unknown): boolean {
  return value === "no_applied_writes" || isLimitationReason(value);
}

/**
 * Strict predicate for already-parsed trusted JSON. It is not a hostile-object
 * boundary — `parseTaskPageJson` is.
 */
export function isTrustedTaskPageData(value: unknown): value is TaskRead.Page {
  if (!isPlainJsonDataGraph(value)) return false;
  // D3's `accountEpoch` is OPTIONAL, so both key sets are law: a 0.6.0 server
  // omits it and a 0.7.0 server sends it, and neither page may be refused by a
  // client that knows the other. Spelled as two exact key sets rather than as
  // "at least these keys", because the exactness is the guard — an unknown
  // sixth key is still refused, which is what stops a server from smuggling an
  // unratified field onto a ratified wire.
  const withEpoch = hasExactKeys(value, ["contractVersion", "items", "window", "completeness", "absence", "accountEpoch"]);
  if (!withEpoch && !hasExactKeys(value, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const page = value as { contractVersion: unknown; items: unknown; window: unknown; completeness: unknown; absence: unknown; accountEpoch?: unknown };
  if (page.contractVersion !== TASKS_READ_CONTRACT_VERSION || !Array.isArray(page.items)) return false;
  // Present means valid. `undefined` is unreachable here — the key set above
  // decides presence — so a present-but-junk epoch is refused rather than
  // silently ignored, which would let a server ship `"3"` and a client stamp
  // its ops with a string.
  if (withEpoch && !isAccountEpoch(page.accountEpoch)) return false;
  if (!page.items.every(hasSafeItem)) return false;
  const itemIds = page.items.map((item) => (item as { id: string }).id);
  if (new Set(itemIds).size !== itemIds.length) return false;
  if (!hasExactKeys(page.window, ["status", "complete", "hasMore", "nextCursor"])) return false;
  const window = page.window as { status: unknown; complete: unknown; hasMore: unknown; nextCursor: unknown };
  if (typeof window.status !== "string" || typeof window.complete !== "boolean" || typeof window.hasMore !== "boolean") return false;
  if (window.nextCursor !== null && (typeof window.nextCursor !== "string" || parseKeysetCursorValue(window.nextCursor) === null)) return false;
  if (!isTrustedTaskWindowHonest(window as { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null })) return false;
  if (!hasSafeCompletenessObject(page.completeness)) return false;
  const completenessStatus = (page.completeness as { status: unknown }).status;
  if (window.status === "incomplete" && completenessStatus === "complete") return false;
  if (page.absence !== null && (!hasExactKeys(page.absence, ["kind"]) || (page.absence as { kind: unknown }).kind !== "query_gap")) return false;
  if (page.absence !== null && (window.hasMore || window.nextCursor !== null)) return false;
  return isTrustedTaskCompletenessHonest({
    items: page.items,
    completeness: page.completeness as NonNullable<Parameters<typeof isTrustedTaskCompletenessHonest>[0]["completeness"]>,
    absence: page.absence as { kind?: string } | null,
  });
}

/** Authoritative no-execution boundary for untrusted canonical JSON text. */
export function parseTaskPageJson(raw: string): TaskRead.Page | null {
  return parseCanonicalJson(raw, MAX_TASKS_PAGE_JSON_CODE_UNITS, isTrustedTaskPageData);
}

/** A generation counter: a safe non-negative integer. Never a float, never a string. */
function isAccountEpoch(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

/**
 * The account epoch this page reports, or `null` when the server did not send
 * one (D3).
 *
 * A named reader rather than a property access, so there is one place that
 * decides what absence means and it cannot quietly become `?? 0` at a call
 * site. Zero is a real epoch; "not told" is not an epoch at all, and a client
 * that conflates them stamps write envelopes with a generation no server ever
 * asserted — which the fence would then refuse as a straggler, turning a
 * missing field into lost edits.
 */
export function readTaskPageAccountEpoch(page: TaskRead.Page): number | null {
  const epoch = (page as { accountEpoch?: unknown }).accountEpoch;
  return isAccountEpoch(epoch) ? epoch : null;
}

/**
 * Every one of the thirteen fields is required and exactly typed, and NO other
 * key is permitted.
 *
 * On the numeric bounds, or rather their absence: these are safe-integer and
 * finiteness checks, not range checks. `core/contracts/src/domain/tasks.ts`
 * bounds none of them, and a ceiling invented here would refuse a real row —
 * a data-loss path dressed as validation. Payload size is already bounded by
 * `MAX_TASKS_PAGE_JSON_CODE_UNITS` at the parse boundary, which is where a
 * size limit belongs.
 *
 * `sortOrder` permits fractions and negatives deliberately: fractional order
 * keys are how an insert-between lands without renumbering the list, and the
 * domain type is a plain `number`.
 */
function hasSafeItem(value: unknown): boolean {
  if (!hasExactKeys(value, TASK_ITEM_FIELDS)) return false;
  const item = value as {
    id: unknown;
    description: unknown;
    completed: unknown;
    completedAt: unknown;
    dueAt: unknown;
    owner: unknown;
    source: unknown;
    provenance: unknown;
    sortOrder: unknown;
    indentLevel: unknown;
    createdAt: unknown;
    updatedAt: unknown;
    revision: unknown;
  };
  if (typeof item.id !== "string" || parseTaskItemId(item.id) === null) return false;
  if (typeof item.description !== "string") return false;
  if (typeof item.completed !== "boolean") return false;
  if (!isNullableTimestamp(item.completedAt)) return false;
  if (!isNullableTimestamp(item.dueAt)) return false;
  if (item.owner !== null && typeof item.owner !== "string") return false;
  if (typeof item.source !== "string") return false;
  if (!Array.isArray(item.provenance) || !item.provenance.every((entry) => typeof entry === "string")) return false;
  if (typeof item.sortOrder !== "number" || !Number.isFinite(item.sortOrder)) return false;
  if (!Number.isSafeInteger(item.indentLevel) || (item.indentLevel as number) < 0) return false;
  if (!Number.isSafeInteger(item.createdAt)) return false;
  if (!Number.isSafeInteger(item.updatedAt)) return false;
  return item.revision === null || typeof item.revision === "string";
}

/**
 * The thirteen, in the order `core/contracts/src/domain/tasks.ts` declares
 * them. Exported so a parity check can assert the wire and the domain agree on
 * the SET rather than on someone's memory of it — D2's whole point is that a
 * narrower surface makes the flip visible to users.
 */
export const TASK_ITEM_FIELDS: readonly string[] = Object.freeze([
  "id",
  "description",
  "completed",
  "completedAt",
  "dueAt",
  "owner",
  "source",
  "provenance",
  "sortOrder",
  "indentLevel",
  "createdAt",
  "updatedAt",
  "revision",
]);

function isNullableTimestamp(value: unknown): boolean {
  return value === null || Number.isSafeInteger(value);
}

function hasSafeCompletenessObject(value: unknown): boolean {
  if (!hasExactKeys(value, ["version", "status", "reasons", "frontiers"])) return false;
  const completeness = value as { version: unknown; status: unknown; reasons: unknown; frontiers: unknown };
  if (!hasExactKeys(completeness.frontiers, [
    "declaredFrontier",
    "newestAppliedFrontier",
    "missingAppliedFrontierReason",
  ])) return false;
  const frontiers = completeness.frontiers as {
    declaredFrontier: unknown;
    newestAppliedFrontier: unknown;
    missingAppliedFrontierReason: unknown;
  };
  if (typeof frontiers.declaredFrontier !== "string" || parseTaskFrontier(frontiers.declaredFrontier) === null) return false;
  if (frontiers.newestAppliedFrontier !== null && (typeof frontiers.newestAppliedFrontier !== "string" || parseTaskFrontier(frontiers.newestAppliedFrontier) === null)) return false;
  return frontiers.missingAppliedFrontierReason === null || isMissingAppliedFrontierReason(frontiers.missingAppliedFrontierReason);
}

function hasExactKeys(value: unknown, expected: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
}

function parseKeysetCursorValue(raw: string): string | null {
  return /^[\x21-\x7e]{1,4096}$/.test(raw) ? raw : null;
}
