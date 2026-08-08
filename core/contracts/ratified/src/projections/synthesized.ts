import type { KeysetCursor } from "../pagination/cursor.js";
import { isPlainJsonDataGraph, parseCanonicalJson } from "../wire/json.js";

/** Public wire-shape version; package versioning is reviewed separately. */
export const SYNTHESIZED_READ_CONTRACT_VERSION = "1.0.0" as const;

declare const SynthesizedItemIdBrand: unique symbol;
declare const SynthesizedTextBrand: unique symbol;
declare const CitationRefBrand: unique symbol;
declare const RecallFrontierBrand: unique symbol;
declare const Sha256DigestBrand: unique symbol;

export type SynthesizedItemId = string & { readonly [SynthesizedItemIdBrand]: true };
export type SynthesizedText = string & { readonly [SynthesizedTextBrand]: true };
export type CitationRef = string & { readonly [CitationRefBrand]: true };
export type RecallFrontier = string & { readonly [RecallFrontierBrand]: true };
export type Sha256Digest = string & { readonly [Sha256DigestBrand]: true };

export const MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS = 2_000_000;

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

export function parseSha256Digest(raw: string): Sha256Digest | null {
  return /^[0-9a-f]{64}$/.test(raw) ? (raw as Sha256Digest) : null;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export declare namespace SynthesizedMemoryRead {
  /** Closed, store-agnostic synthesis lineage safe for an authorized consumer. */
  interface Provenance {
    synthesisVersion: string;
    inputDigest: Sha256Digest;
    outputDigest: Sha256Digest;
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

  type MissingAcceptedFrontierReason = "no_accepted_work" | LimitationReason;
  // domain-pending(DIV-DOMCORE-006)
  type MissingStmFrontierReason = "no_eligible_stm" | LimitationReason;

  interface SearchedAcceptedFrontier {
    newestSearchedAcceptedFrontier: RecallFrontier;
    missingAcceptedFrontierReason: null;
  }

  interface MissingAcceptedFrontier {
    newestSearchedAcceptedFrontier: null;
    missingAcceptedFrontierReason: MissingAcceptedFrontierReason;
  }

  // domain-pending(DIV-DOMCORE-006)
  interface SearchedStmFrontier {
    newestSearchedStmFrontier: RecallFrontier;
    missingStmFrontierReason: null;
  }

  // domain-pending(DIV-DOMCORE-006)
  interface MissingStmFrontier {
    newestSearchedStmFrontier: null;
    missingStmFrontierReason: MissingStmFrontierReason;
  }

  type Frontiers = { declaredFrontier: RecallFrontier }
    & (SearchedAcceptedFrontier | MissingAcceptedFrontier)
    & (SearchedStmFrontier | MissingStmFrontier);

  type CompleteFrontiers = { declaredFrontier: RecallFrontier }
    & (SearchedAcceptedFrontier | {
      newestSearchedAcceptedFrontier: null;
      missingAcceptedFrontierReason: "no_accepted_work";
    })
    & (SearchedStmFrontier | {
      newestSearchedStmFrontier: null;
      missingStmFrontierReason: "no_eligible_stm";
    });

  interface CompleteRecall {
    version: "recall-completeness-v1";
    status: "complete";
    reasons: readonly [];
    frontiers: CompleteFrontiers;
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
  type LimitedCompleteness = IncompleteRecall | DegradedRecall | PartialRecall;

  interface QueryGap {
    kind: "query_gap";
  }

  interface PageBase {
    contractVersion: typeof SYNTHESIZED_READ_CONTRACT_VERSION;
    items: readonly Item[];
  }

  interface CompleteRecallTerminalPage extends PageBase {
    window: CompleteTerminalWindow;
    completeness: CompleteRecall;
    absence: QueryGap | null;
  }

  interface CompleteRecallContinuationPage extends PageBase {
    window: MoreContinuationWindow;
    completeness: CompleteRecall;
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
    | CompleteRecallTerminalPage
    | CompleteRecallContinuationPage
    | LimitedTerminalPage
    | LimitedContinuationPage;
}

/** Already-parsed trusted-JSON law; use parseSynthesizedPageJson for untrusted bytes. */
export function isTrustedPageWindowHonest(window: {
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

/** Already-parsed trusted-JSON law; use parseSynthesizedPageJson for untrusted bytes. */
export function isTrustedRecallCompletenessHonest(page: {
  items: readonly unknown[];
  completeness?: {
    version?: string;
    status?: string;
    reasons?: readonly string[];
    frontiers?: {
      declaredFrontier?: string;
      newestSearchedAcceptedFrontier?: string | null;
      missingAcceptedFrontierReason?: string | null;
      // domain-pending(DIV-DOMCORE-006)
      newestSearchedStmFrontier?: string | null;
      missingStmFrontierReason?: string | null;
    };
  };
  absence?: { kind?: string } | null;
}): boolean {
  if (!isPlainJsonDataGraph(page)) return false;
  if (!hasExactKeys(page, ["items", "completeness", "absence"])
    && !hasExactKeys(page, ["contractVersion", "items", "window", "completeness", "absence"])) return false;
  const completeness = page.completeness;
  if (!completeness || completeness.version !== "recall-completeness-v1") return false;
  if (!hasExactKeys(completeness, ["version", "status", "reasons", "frontiers"])) return false;
  const { frontiers } = completeness;
  if (!frontiers || !OPAQUE_REF_PATTERN.test(frontiers.declaredFrontier ?? "")) return false;
  if (!hasExactKeys(frontiers, [
    "declaredFrontier",
    "newestSearchedAcceptedFrontier",
    "missingAcceptedFrontierReason",
    "newestSearchedStmFrontier",
    "missingStmFrontierReason",
  ])) return false;
  const accepted = frontiers.newestSearchedAcceptedFrontier;
  const missingAccepted = frontiers.missingAcceptedFrontierReason;
  if (accepted === null) {
    if (!isMissingAcceptedFrontierReason(missingAccepted)) return false;
  } else if (!OPAQUE_REF_PATTERN.test(accepted ?? "") || missingAccepted !== null) {
    return false;
  }
  // domain-pending(DIV-DOMCORE-006)
  const stm = frontiers.newestSearchedStmFrontier;
  const missingStm = frontiers.missingStmFrontierReason;
  if (stm === null) {
    if (!isMissingStmFrontierReason(missingStm)) return false;
  } else if (!OPAQUE_REF_PATTERN.test(stm ?? "") || missingStm !== null) {
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

  const acceptedWorkPending = accepted === null
    ? missingAccepted === "accepted_work_pending"
    : accepted !== frontiers.declaredFrontier;
  if (acceptedWorkPending) {
    if (completeness.status !== "incomplete" || !reasons.includes("accepted_work_pending")) return false;
  } else if (completeness.status === "incomplete") {
    return false;
  }
  if (completeness.status === "complete") {
    if (accepted !== frontiers.declaredFrontier && missingAccepted !== "no_accepted_work") return false;
    if (stm === null && missingStm !== "no_eligible_stm") return false;
  }
  if (accepted === null && isLimitationReason(missingAccepted) && !reasons.includes(missingAccepted)) return false;
  if (stm === null && isLimitationReason(missingStm) && !reasons.includes(missingStm)) return false;

  const hasItems = page.items.length > 0;
  if (hasItems) return page.absence === null;
  if (!hasExactKeys(page.absence, ["kind"]) || page.absence.kind !== "query_gap") return false;
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

// domain-pending(DIV-DOMCORE-006)
function isMissingStmFrontierReason(value: unknown): boolean {
  return value === "no_eligible_stm" || isLimitationReason(value);
}

function isMissingAcceptedFrontierReason(value: unknown): boolean {
  return value === "no_accepted_work" || isLimitationReason(value);
}

/** Strict predicate for already-parsed trusted JSON. It is not a hostile-object boundary. */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export function isTrustedSynthesizedPageData(value: unknown): value is SynthesizedMemoryRead.Page {
  if (!isPlainJsonDataGraph(value)) return false;
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
  if (!isTrustedPageWindowHonest(window as { status: string; complete: boolean; hasMore: boolean; nextCursor: string | null })) return false;
  if (!hasSafeCompletenessObject(page.completeness)) return false;
  const completenessStatus = (page.completeness as { status: unknown }).status;
  if (window.status === "incomplete" && completenessStatus === "complete") return false;
  if (page.absence !== null && (!hasExactKeys(page.absence, ["kind"]) || (page.absence as { kind: unknown }).kind !== "query_gap")) return false;
  if (page.absence !== null && (window.hasMore || window.nextCursor !== null)) return false;
  return isTrustedRecallCompletenessHonest({
    items: page.items,
    completeness: page.completeness as NonNullable<Parameters<typeof isTrustedRecallCompletenessHonest>[0]["completeness"]>,
    absence: page.absence as { kind?: string } | null,
  });
}

/** Authoritative no-execution boundary for untrusted canonical JSON text. */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export function parseSynthesizedPageJson(raw: string): SynthesizedMemoryRead.Page | null {
  return parseCanonicalJson(raw, MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS, isTrustedSynthesizedPageData);
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
    if (typeof provenance.synthesisVersion !== "string" || provenance.synthesisVersion.trim().length === 0) return false;
    if (typeof provenance.inputDigest !== "string" || parseSha256Digest(provenance.inputDigest) === null) return false;
    if (typeof provenance.outputDigest !== "string" || parseSha256Digest(provenance.outputDigest) === null) return false;
  }
  return true;
}

function hasSafeCompletenessObject(value: unknown): boolean {
  if (!hasExactKeys(value, ["version", "status", "reasons", "frontiers"])) return false;
  const completeness = value as { version: unknown; status: unknown; reasons: unknown; frontiers: unknown };
  if (!hasExactKeys(completeness.frontiers, [
    "declaredFrontier",
    "newestSearchedAcceptedFrontier",
    "missingAcceptedFrontierReason",
    "newestSearchedStmFrontier",
    "missingStmFrontierReason",
  ])) return false;
  const frontiers = completeness.frontiers as {
    declaredFrontier: unknown;
    newestSearchedAcceptedFrontier: unknown;
    missingAcceptedFrontierReason: unknown;
    // domain-pending(DIV-DOMCORE-006)
    newestSearchedStmFrontier: unknown;
    missingStmFrontierReason: unknown;
  };
  if (typeof frontiers.declaredFrontier !== "string" || parseRecallFrontier(frontiers.declaredFrontier) === null) return false;
  if (frontiers.newestSearchedAcceptedFrontier !== null && (typeof frontiers.newestSearchedAcceptedFrontier !== "string" || parseRecallFrontier(frontiers.newestSearchedAcceptedFrontier) === null)) return false;
  if (frontiers.missingAcceptedFrontierReason !== null && !isMissingAcceptedFrontierReason(frontiers.missingAcceptedFrontierReason)) return false;
  if (frontiers.newestSearchedStmFrontier !== null && (typeof frontiers.newestSearchedStmFrontier !== "string" || parseRecallFrontier(frontiers.newestSearchedStmFrontier) === null)) return false;
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
