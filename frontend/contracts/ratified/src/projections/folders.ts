/**
 * The ratified folders READ wire.
 *
 * Ruling of record: the platform-conversations lane brief. Folders ride in
 * the same lane as conversations because Home's conversation list is not
 * honest without folder membership, and the service already serves all four
 * verbs. Two decisions, already made:
 *
 * 1. Dangling `conversation.folder_id` after folder deletion is legal. The
 *    service never creates system/default folders, so reassignment can leave
 *    an identifier that does not resolve. Treat folder ids as opaque.
 * 2. There is no maximum-folder cap. Legacy's limit is not ratified.
 *
 * WHY A SEPARATE MODULE. Same reason as conversations vs tasks: the
 * pagination law and completeness discipline transfer; the item vocabulary
 * and envelope version do not. Folders have no short-term overlay and no
 * write-ops envelope (create/patch/delete stay the four verbs already
 * served). The GET the prototype served was an unpaginated bare array;
 * v1 wraps the same records in the memories-style completeness envelope
 * so `complete` is a server declaration, never a client inference.
 *
 * Item ids are the storage ids already served, so a platform folders read
 * and a legacy folders read of one origin return the same records.
 */

import type { KeysetCursor } from "../pagination/cursor.js";
import { isPlainJsonDataGraph, parseCanonicalJson } from "../wire/json.js";

export const FOLDERS_READ_CONTRACT_VERSION = "1.0.0" as const;

declare const FolderItemIdBrand: unique symbol;
declare const FolderFrontierBrand: unique symbol;

export type FolderItemId = string & { readonly [FolderItemIdBrand]: true };
export type FolderFrontier = string & { readonly [FolderFrontierBrand]: true };

export const MAX_FOLDERS_PAGE_JSON_CODE_UNITS = 2_000_000;

const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export function parseFolderItemId(raw: string): FolderItemId | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as FolderItemId) : null;
}

export function parseFolderFrontier(raw: string): FolderFrontier | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as FolderFrontier) : null;
}

export declare namespace FolderRead {
  /**
   * The fields `frontend/contracts/src/domain/folders.ts` already declares.
   * `revision` is present and may be null: the folders store has no
   * state-revision column today, and inventing one here would be a parallel
   * convention. `isSystem` / `isDefault` stay: delete policy needs them.
   */
  interface Item {
    id: FolderItemId;
    name: string;
    description: string | null;
    color: string;
    icon: string;
    createdAt: number;
    updatedAt: number;
    order: number;
    isDefault: boolean;
    isSystem: boolean;
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
    newestAppliedFrontier: FolderFrontier;
    missingAppliedFrontierReason: null;
  }

  interface MissingAppliedFrontier {
    newestAppliedFrontier: null;
    missingAppliedFrontierReason: MissingAppliedFrontierReason;
  }

  type Frontiers = { declaredFrontier: FolderFrontier }
    & (AppliedFrontier | MissingAppliedFrontier);

  type CompleteFrontiers = { declaredFrontier: FolderFrontier }
    & (AppliedFrontier | {
      newestAppliedFrontier: null;
      missingAppliedFrontierReason: "no_applied_writes";
    });

  interface FrontiersShape {
    version: "folders-completeness-v1";
    frontiers: Frontiers;
  }

  interface CompleteCoverage {
    version: "folders-completeness-v1";
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
    contractVersion: typeof FOLDERS_READ_CONTRACT_VERSION;
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

export function isTrustedFolderWindowHonest(window: {
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

export function isTrustedFolderCompletenessHonest(page: {
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
  if (!completeness || completeness.version !== "folders-completeness-v1") return false;
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

export function isTrustedFolderPageData(value: unknown): value is FolderRead.Page {
  if (!isPlainJsonDataGraph(value)) return false;
  if (!hasExactKeys(value, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const page = value as { contractVersion: unknown; items: unknown; window: unknown; completeness: unknown; absence: unknown };
  if (page.contractVersion !== FOLDERS_READ_CONTRACT_VERSION || !Array.isArray(page.items)) return false;
  if (!page.items.every(hasSafeItem)) return false;
  const itemIds = page.items.map((item) => (item as { id: string }).id);
  if (new Set(itemIds).size !== itemIds.length) return false;
  if (!hasExactKeys(page.window, ["status", "complete", "hasMore", "nextCursor"])) return false;
  const window = page.window as { status: unknown; complete: unknown; hasMore: unknown; nextCursor: unknown };
  if (typeof window.status !== "string" || typeof window.complete !== "boolean" || typeof window.hasMore !== "boolean") return false;
  if (window.nextCursor !== null && (typeof window.nextCursor !== "string" || parseKeysetCursorValue(window.nextCursor) === null)) return false;
  if (!isTrustedFolderWindowHonest(window as { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null })) return false;
  if (!hasSafeCompletenessObject(page.completeness)) return false;
  const completenessStatus = (page.completeness as { status: unknown }).status;
  if (window.status === "incomplete" && completenessStatus === "complete") return false;
  if (page.absence !== null && (!hasExactKeys(page.absence, ["kind"]) || (page.absence as { kind: unknown }).kind !== "query_gap")) return false;
  if (page.absence !== null && (window.hasMore || window.nextCursor !== null)) return false;
  return isTrustedFolderCompletenessHonest({
    items: page.items,
    completeness: page.completeness as NonNullable<Parameters<typeof isTrustedFolderCompletenessHonest>[0]["completeness"]>,
    absence: page.absence as { kind?: string } | null,
  });
}

export function parseFolderPageJson(raw: string): FolderRead.Page | null {
  return parseCanonicalJson(raw, MAX_FOLDERS_PAGE_JSON_CODE_UNITS, isTrustedFolderPageData);
}

function hasSafeItem(value: unknown): boolean {
  if (!hasExactKeys(value, FOLDER_ITEM_FIELDS)) return false;
  const item = value as {
    id: unknown;
    name: unknown;
    description: unknown;
    color: unknown;
    icon: unknown;
    createdAt: unknown;
    updatedAt: unknown;
    order: unknown;
    isDefault: unknown;
    isSystem: unknown;
    revision: unknown;
  };
  if (typeof item.id !== "string" || parseFolderItemId(item.id) === null) return false;
  if (typeof item.name !== "string") return false;
  if (item.description !== null && typeof item.description !== "string") return false;
  if (typeof item.color !== "string") return false;
  if (typeof item.icon !== "string") return false;
  if (!Number.isSafeInteger(item.createdAt)) return false;
  if (!Number.isSafeInteger(item.updatedAt)) return false;
  if (typeof item.order !== "number" || !Number.isFinite(item.order)) return false;
  if (typeof item.isDefault !== "boolean") return false;
  if (typeof item.isSystem !== "boolean") return false;
  return item.revision === null || typeof item.revision === "string";
}

export const FOLDER_ITEM_FIELDS: readonly string[] = Object.freeze([
  "id",
  "name",
  "description",
  "color",
  "icon",
  "createdAt",
  "updatedAt",
  "order",
  "isDefault",
  "isSystem",
  "revision",
]);

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
  if (typeof frontiers.declaredFrontier !== "string" || parseFolderFrontier(frontiers.declaredFrontier) === null) return false;
  if (frontiers.newestAppliedFrontier !== null && (typeof frontiers.newestAppliedFrontier !== "string" || parseFolderFrontier(frontiers.newestAppliedFrontier) === null)) return false;
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
