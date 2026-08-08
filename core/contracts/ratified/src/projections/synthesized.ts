import type { KeysetCursor } from "../pagination/cursor.js";

/** Public wire-shape version; package versioning is reviewed separately. */
export const SYNTHESIZED_READ_CONTRACT_VERSION = "1.0.0" as const;

declare const SynthesizedItemIdBrand: unique symbol;
declare const SynthesizedTextBrand: unique symbol;
declare const CitationRefBrand: unique symbol;
declare const RecallFrontierBrand: unique symbol;

export type SynthesizedItemId = string & { readonly [SynthesizedItemIdBrand]: true };
export type SynthesizedText = string & { readonly [SynthesizedTextBrand]: true };
export type CitationRef = string & { readonly [CitationRefBrand]: true };
export type RecallFrontier = string & { readonly [RecallFrontierBrand]: true };

const OPAQUE_REF_PATTERN = /^[\x21-\x7e]{1,1024}$/;

export function parseSynthesizedItemId(raw: string): SynthesizedItemId | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as SynthesizedItemId) : null;
}

export function parseSynthesizedText(raw: string): SynthesizedText | null {
  return raw.trim().length > 0 ? (raw as SynthesizedText) : null;
}

export function parseCitationRef(raw: string): CitationRef | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as CitationRef) : null;
}

export function parseRecallFrontier(raw: string): RecallFrontier | null {
  return OPAQUE_REF_PATTERN.test(raw) ? (raw as RecallFrontier) : null;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export declare namespace SynthesizedMemoryRead {
  /** Closed, store-agnostic synthesis lineage safe for an authorized consumer. */
  interface Provenance {
    synthesisVersion: string;
    inputDigest: string;
    outputDigest: string;
  }

  interface Item {
    /** Stable opaque render id. It is not a domain RecordId and may contain a namespace/hash. */
    id: SynthesizedItemId;
    /** The one and only synthesized presentation field. */
    text: SynthesizedText;
    /** Opaque references only; never raw evidence payloads or ownership coordinates. */
    citations?: readonly CitationRef[];
    provenance?: Provenance;
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

  type IncompleteReason = "accepted_work_pending";
  type DegradedReason =
    | "projection_stale"
    | "projection_unavailable"
    | "projection_bypassed";
  type PartialReason =
    | "source_bound"
    | "time_bound"
    | "policy_bound";
  type LimitationReason = IncompleteReason | DegradedReason | PartialReason;

  type MissingStmFrontierReason = "no_eligible_stm" | LimitationReason;

  interface IncludedFrontiers {
    declaredFrontier: RecallFrontier;
    newestIncludedStmFrontier: RecallFrontier;
    missingStmFrontierReason: null;
  }

  interface MissingIncludedFrontier {
    declaredFrontier: RecallFrontier;
    newestIncludedStmFrontier: null;
    missingStmFrontierReason: MissingStmFrontierReason;
  }

  type Frontiers = IncludedFrontiers | MissingIncludedFrontier;

  interface CompleteRecall {
    version: "recall-completeness-v1";
    status: "complete";
    reasons: readonly [];
    frontiers: IncludedFrontiers | {
      declaredFrontier: RecallFrontier;
      newestIncludedStmFrontier: null;
      missingStmFrontierReason: "no_eligible_stm";
    };
  }

  interface IncompleteRecall extends FrontiersShape {
    status: "incomplete";
    reasons: readonly [IncompleteReason, ...IncompleteReason[]];
  }

  interface DegradedRecall extends FrontiersShape {
    status: "degraded";
    reasons: readonly [DegradedReason, ...DegradedReason[]];
  }

  interface PartialRecall extends FrontiersShape {
    status: "partial";
    reasons: readonly [PartialReason, ...PartialReason[]];
  }

  interface FrontiersShape {
    version: "recall-completeness-v1";
    frontiers: Frontiers;
  }

  type Completeness = CompleteRecall | IncompleteRecall | DegradedRecall | PartialRecall;

  interface QueryGap {
    kind: "query_gap";
  }

  interface PageBase {
    contractVersion: typeof SYNTHESIZED_READ_CONTRACT_VERSION;
    items: readonly Item[];
    completeness: Completeness;
  }

  interface ContinuationPage extends PageBase {
    window: ContinuationWindow;
    absence: null;
  }

  interface TerminalPage extends PageBase {
    window: TerminalWindow;
    absence: QueryGap | null;
  }

  type Page = ContinuationPage | TerminalPage;
}

/** Runtime law for JSON conformance fixtures and non-TypeScript service adapters. */
export function hasHonestPageWindow(window: {
  status: string;
  complete: boolean;
  hasMore: boolean;
  nextCursor: string | null;
}): boolean {
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

/** Rejects result envelopes that could overstate global recall absence or completeness. */
export function hasHonestRecallCompleteness(page: {
  items: readonly unknown[];
  completeness?: {
    version?: string;
    status?: string;
    reasons?: readonly string[];
    frontiers?: {
      declaredFrontier?: string;
      newestIncludedStmFrontier?: string | null;
      missingStmFrontierReason?: string | null;
    };
  };
  absence?: { kind?: string } | null;
}): boolean {
  const completeness = page.completeness;
  if (!completeness || completeness.version !== "recall-completeness-v1") return false;
  const { frontiers } = completeness;
  if (!frontiers || !OPAQUE_REF_PATTERN.test(frontiers.declaredFrontier ?? "")) return false;
  const newest = frontiers.newestIncludedStmFrontier;
  const missingReason = frontiers.missingStmFrontierReason;
  if (newest === null) {
    if (!isMissingStmFrontierReason(missingReason)) return false;
  } else if (!OPAQUE_REF_PATTERN.test(newest ?? "") || missingReason !== null) {
    return false;
  }

  const reasons = completeness.reasons;
  if (!Array.isArray(reasons)) return false;
  if (new Set(reasons).size !== reasons.length) return false;
  if (completeness.status === "complete") {
    if (reasons.length !== 0) return false;
  } else {
    const reasonFamily = REASONS_BY_STATUS[completeness.status ?? ""];
    if (!reasonFamily || reasons.length === 0 || !reasons.every((reason) => reasonFamily.has(reason))) return false;
  }

  if (newest === null) {
    if (completeness.status === "complete" && missingReason !== "no_eligible_stm") return false;
    if (isLimitationReason(missingReason) && !reasons.includes(missingReason)) return false;
  }

  const hasItems = page.items.length > 0;
  if (hasItems) return page.absence === null;
  if (page.absence?.kind !== "query_gap") return false;
  return completeness.status === "complete" || reasons.length > 0;
}

const LIMITATION_REASONS = new Set([
  "accepted_work_pending",
  "projection_stale",
  "projection_unavailable",
  "projection_bypassed",
  "source_bound",
  "time_bound",
  "policy_bound",
]);

const REASONS_BY_STATUS: Record<string, ReadonlySet<string>> = {
  incomplete: new Set(["accepted_work_pending"]),
  degraded: new Set(["projection_stale", "projection_unavailable", "projection_bypassed"]),
  partial: new Set(["source_bound", "time_bound", "policy_bound"]),
};

function isLimitationReason(value: unknown): boolean {
  return typeof value === "string" && LIMITATION_REASONS.has(value);
}

function isMissingStmFrontierReason(value: unknown): boolean {
  return value === "no_eligible_stm" || isLimitationReason(value);
}

/** Strict JSON boundary for the complete synthesized-read page and every nested object. */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export function hasSafeSynthesizedPage(value: unknown): value is SynthesizedMemoryRead.Page {
  if (!hasExactKeys(value, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const page = value as { contractVersion: unknown; items: unknown; window: unknown; completeness: unknown; absence: unknown };
  if (page.contractVersion !== SYNTHESIZED_READ_CONTRACT_VERSION || !Array.isArray(page.items)) return false;
  if (!page.items.every(hasSafeItem)) return false;
  const itemIds = page.items.map((item) => (item as { id: string }).id);
  if (new Set(itemIds).size !== itemIds.length) return false;
  if (!hasExactKeys(page.window, ["status", "complete", "hasMore", "nextCursor"])) return false;
  const window = page.window as { status: unknown; complete: unknown; hasMore: unknown; nextCursor: unknown };
  if (typeof window.status !== "string" || typeof window.complete !== "boolean" || typeof window.hasMore !== "boolean") return false;
  if (window.nextCursor !== null && (typeof window.nextCursor !== "string" || parseKeysetCursorValue(window.nextCursor) === null)) return false;
  if (!hasHonestPageWindow(window as { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null })) return false;
  if (!hasSafeCompletenessObject(page.completeness)) return false;
  if (page.absence !== null && (!hasExactKeys(page.absence, ["kind"]) || (page.absence as { kind: unknown }).kind !== "query_gap")) return false;
  if (page.absence !== null && (window.hasMore || window.nextCursor !== null)) return false;
  return hasHonestRecallCompleteness({
    items: page.items,
    completeness: page.completeness as NonNullable<Parameters<typeof hasHonestRecallCompleteness>[0]["completeness"]>,
    absence: page.absence as { kind?: string } | null,
  });
}

function hasSafeItem(value: unknown): boolean {
  if (!hasAllowedExactKeys(value, ["id", "text"], ["citations", "provenance"])) return false;
  const item = value as { id: unknown; text: unknown; citations?: unknown; provenance?: unknown };
  if (typeof item.id !== "string" || parseSynthesizedItemId(item.id) === null) return false;
  if (typeof item.text !== "string" || parseSynthesizedText(item.text) === null) return false;
  if ("citations" in item && (!Array.isArray(item.citations) || !item.citations.every((ref) => typeof ref === "string" && parseCitationRef(ref) !== null))) return false;
  if (Array.isArray(item.citations) && new Set(item.citations).size !== item.citations.length) return false;
  if ("provenance" in item) {
    if (!hasExactKeys(item.provenance, ["synthesisVersion", "inputDigest", "outputDigest"])) return false;
    const provenance = item.provenance as { synthesisVersion: unknown; inputDigest: unknown; outputDigest: unknown };
    if (![provenance.synthesisVersion, provenance.inputDigest, provenance.outputDigest].every((field) => typeof field === "string" && field.trim().length > 0)) return false;
  }
  return true;
}

function hasSafeCompletenessObject(value: unknown): boolean {
  if (!hasExactKeys(value, ["version", "status", "reasons", "frontiers"])) return false;
  const completeness = value as { version: unknown; status: unknown; reasons: unknown; frontiers: unknown };
  if (!hasExactKeys(completeness.frontiers, ["declaredFrontier", "newestIncludedStmFrontier", "missingStmFrontierReason"])) return false;
  const frontiers = completeness.frontiers as { declaredFrontier: unknown; newestIncludedStmFrontier: unknown; missingStmFrontierReason: unknown };
  if (typeof frontiers.declaredFrontier !== "string" || parseRecallFrontier(frontiers.declaredFrontier) === null) return false;
  if (frontiers.newestIncludedStmFrontier !== null && (typeof frontiers.newestIncludedStmFrontier !== "string" || parseRecallFrontier(frontiers.newestIncludedStmFrontier) === null)) return false;
  return frontiers.missingStmFrontierReason === null || isMissingStmFrontierReason(frontiers.missingStmFrontierReason);
}

function hasExactKeys(value: unknown, expected: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
}

function hasAllowedExactKeys(value: unknown, required: readonly string[], optional: readonly string[]): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value);
  return required.every((key) => actual.includes(key)) && actual.every((key) => required.includes(key) || optional.includes(key));
}

function parseKeysetCursorValue(raw: string): string | null {
  return /^[\x21-\x7e]{1,4096}$/.test(raw) ? raw : null;
}
