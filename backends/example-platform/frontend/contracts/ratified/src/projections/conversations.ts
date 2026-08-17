/**
 * The ratified conversations READ wire.
 *
 * Ruling of record: the platform-conversations lane brief, implementing David's
 * decision that the new UI may use only the new backend, and that Home cannot
 * be honest until conversations are served through a platform adapter. There
 * is no prior ratified conversations contract; this module ratifies the v1
 * item the service already serves, flattened the way
 * `frontend/contracts/src/domain/conversations.ts` already does, plus
 * `revision` backed by the store's `state_revision`.
 *
 * WHY THIS IS A SEPARATE MODULE FROM `./projections/tasks` AND
 * `./projections/synthesized`. What transfers is the pagination law, the
 * HMAC keyset cursor, and the completeness DISCIPLINE — not one file serving
 * three domains. Conversations have no short-term overlay, no accepted-work
 * queue, and no write-ops envelope (writes stay the four per-field PATCHes
 * and `DELETE ?cascade=false` until memories-write). Serving them through
 * `TaskRead` would put `pending_writes` on a wire whose writes are not that
 * door, and serving them through `SynthesizedMemoryRead` would declare
 * memory-retrieval coverage on a conversations page.
 *
 * WHAT IS THE SAME, DELIBERATELY:
 *
 * - **The window is the same four variants** over the same `KeysetCursor`.
 * - **The completeness envelope is DECLARED, never counted.** Its checkable
 *   pair is `newestAppliedFrontier` against `declaredFrontier`. Client
 *   mutations (the four PATCHes and delete) apply synchronously into the
 *   store this read serves from; `pending_writes` is the lagging case.
 * - Item ids are bounded printable ASCII. Unlike tasks, they are the storage
 *   ids the service already serves — ratifying a wire, not minting reader-
 *   scoped handles. Platform and legacy reads of one origin must return the
 *   same records, and opaque re-keying would make that comparison a lie.
 *
 * WHAT IS DIFFERENT, and why:
 *
 * - The envelope is `conversations-completeness-v1`.
 * - `interrupted` conversations stay visible. Hiding a status the server
 *   holds was a legacy default-filter wart, not v1.
 * - `folderId` may dangle: deleting a folder without a default target leaves
 *   the identifier in place. Treat it as opaque; do not dereference it.
 * - Transcript access is out of scope for v1.
 * - There is no client create. Conversations are server-originated via the
 *   finalizer. Polling is the v1 freshness mechanism; there is no
 *   finalization event.
 */

import type { KeysetCursor } from "../pagination/cursor.js";
import { isPlainJsonDataGraph, parseCanonicalJson } from "../wire/json.js";

/** Public wire-shape version; package versioning is reviewed separately. */
export const CONVERSATIONS_READ_CONTRACT_VERSION = "1.0.0" as const;

declare const ConversationItemIdBrand: unique symbol;
declare const ConversationFrontierBrand: unique symbol;

/**
 * A conversations item handle. Grammar only (printable ASCII, bounded).
 * Unlike `TaskItemId`, this is the storage id the service already serves.
 */
export type ConversationItemId = string & { readonly [ConversationItemIdBrand]: true };

/** An opaque, reader-scoped, content-free coverage frontier. */
export type ConversationFrontier = string & { readonly [ConversationFrontierBrand]: true };

export const MAX_CONVERSATIONS_PAGE_JSON_CODE_UNITS = 2_000_000;

const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export function parseConversationItemId(raw: string): ConversationItemId | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as ConversationItemId) : null;
}

export function parseConversationFrontier(raw: string): ConversationFrontier | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as ConversationFrontier) : null;
}

export declare namespace ConversationRead {
  /**
   * The flattened v1 item: the fields `frontend/contracts/src/domain/conversations.ts`
   * already declares, with `revision` populated from the store's
   * `state_revision`. Every field is present on every item.
   */
  interface Item {
    id: ConversationItemId;
    title: string;
    overview: string;
    createdAt: number;
    updatedAt: number;
    startedAt: number | null;
    finishedAt: number | null;
    source: string;
    status: string;
    discarded: boolean;
    starred: boolean;
    visibility: "public" | "private" | "shared";
    isLocked: boolean;
    /**
     * Opaque folder handle. `null` = unfiled. A non-null value is NOT a
     * promise that a folder row exists — deletion may leave this dangling.
     */
    folderId: string | null;
    /** Account-level store revision of the last client mutation we saw. */
    revision: string | null;
  }

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
    newestAppliedFrontier: ConversationFrontier;
    missingAppliedFrontierReason: null;
  }

  interface MissingAppliedFrontier {
    newestAppliedFrontier: null;
    missingAppliedFrontierReason: MissingAppliedFrontierReason;
  }

  type Frontiers = { declaredFrontier: ConversationFrontier }
    & (AppliedFrontier | MissingAppliedFrontier);

  type CompleteFrontiers = { declaredFrontier: ConversationFrontier }
    & (AppliedFrontier | {
      newestAppliedFrontier: null;
      missingAppliedFrontierReason: "no_applied_writes";
    });

  interface FrontiersShape {
    version: "conversations-completeness-v1";
    frontiers: Frontiers;
  }

  interface CompleteCoverage {
    version: "conversations-completeness-v1";
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
    contractVersion: typeof CONVERSATIONS_READ_CONTRACT_VERSION;
    items: readonly Item[];
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

export function isTrustedConversationWindowHonest(window: {
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

export function isTrustedConversationCompletenessHonest(page: {
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
  if (!completeness || completeness.version !== "conversations-completeness-v1") return false;
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
const VISIBILITIES: ReadonlySet<unknown> = new Set(["public", "private", "shared"]);

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

export function isTrustedConversationPageData(value: unknown): value is ConversationRead.Page {
  if (!isPlainJsonDataGraph(value)) return false;
  if (!hasExactKeys(value, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const page = value as { contractVersion: unknown; items: unknown; window: unknown; completeness: unknown; absence: unknown };
  if (page.contractVersion !== CONVERSATIONS_READ_CONTRACT_VERSION || !Array.isArray(page.items)) return false;
  if (!page.items.every(hasSafeItem)) return false;
  const itemIds = page.items.map((item) => (item as { id: string }).id);
  if (new Set(itemIds).size !== itemIds.length) return false;
  if (!hasExactKeys(page.window, ["status", "complete", "hasMore", "nextCursor"])) return false;
  const window = page.window as { status: unknown; complete: unknown; hasMore: unknown; nextCursor: unknown };
  if (typeof window.status !== "string" || typeof window.complete !== "boolean" || typeof window.hasMore !== "boolean") return false;
  if (window.nextCursor !== null && (typeof window.nextCursor !== "string" || parseKeysetCursorValue(window.nextCursor) === null)) return false;
  if (!isTrustedConversationWindowHonest(window as { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null })) return false;
  if (!hasSafeCompletenessObject(page.completeness)) return false;
  const completenessStatus = (page.completeness as { status: unknown }).status;
  if (window.status === "incomplete" && completenessStatus === "complete") return false;
  if (page.absence !== null && (!hasExactKeys(page.absence, ["kind"]) || (page.absence as { kind: unknown }).kind !== "query_gap")) return false;
  if (page.absence !== null && (window.hasMore || window.nextCursor !== null)) return false;
  return isTrustedConversationCompletenessHonest({
    items: page.items,
    completeness: page.completeness as NonNullable<Parameters<typeof isTrustedConversationCompletenessHonest>[0]["completeness"]>,
    absence: page.absence as { kind?: string } | null,
  });
}

export function parseConversationPageJson(raw: string): ConversationRead.Page | null {
  return parseCanonicalJson(raw, MAX_CONVERSATIONS_PAGE_JSON_CODE_UNITS, isTrustedConversationPageData);
}

function hasSafeItem(value: unknown): boolean {
  if (!hasExactKeys(value, CONVERSATION_ITEM_FIELDS)) return false;
  const item = value as {
    id: unknown;
    title: unknown;
    overview: unknown;
    createdAt: unknown;
    updatedAt: unknown;
    startedAt: unknown;
    finishedAt: unknown;
    source: unknown;
    status: unknown;
    discarded: unknown;
    starred: unknown;
    visibility: unknown;
    isLocked: unknown;
    folderId: unknown;
    revision: unknown;
  };
  if (typeof item.id !== "string" || parseConversationItemId(item.id) === null) return false;
  if (typeof item.title !== "string") return false;
  if (typeof item.overview !== "string") return false;
  if (!Number.isSafeInteger(item.createdAt)) return false;
  if (!Number.isSafeInteger(item.updatedAt)) return false;
  if (!isNullableTimestamp(item.startedAt)) return false;
  if (!isNullableTimestamp(item.finishedAt)) return false;
  if (typeof item.source !== "string") return false;
  if (typeof item.status !== "string") return false;
  if (typeof item.discarded !== "boolean") return false;
  if (typeof item.starred !== "boolean") return false;
  if (!VISIBILITIES.has(item.visibility)) return false;
  if (typeof item.isLocked !== "boolean") return false;
  if (item.folderId !== null && typeof item.folderId !== "string") return false;
  return item.revision === null || typeof item.revision === "string";
}

export const CONVERSATION_ITEM_FIELDS: readonly string[] = Object.freeze([
  "id",
  "title",
  "overview",
  "createdAt",
  "updatedAt",
  "startedAt",
  "finishedAt",
  "source",
  "status",
  "discarded",
  "starred",
  "visibility",
  "isLocked",
  "folderId",
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
  if (typeof frontiers.declaredFrontier !== "string" || parseConversationFrontier(frontiers.declaredFrontier) === null) return false;
  if (frontiers.newestAppliedFrontier !== null && (typeof frontiers.newestAppliedFrontier !== "string" || parseConversationFrontier(frontiers.newestAppliedFrontier) === null)) return false;
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
