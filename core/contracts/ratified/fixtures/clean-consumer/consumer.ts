import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";

import {
  SYNTHESIZED_READ_CONTRACT_VERSION,
  hasHonestPageWindow,
  hasHonestRecallCompleteness,
  parseCitationRef,
  parseRecallFrontier,
  parseSynthesizedItemId,
  parseSynthesizedText,
} from "@omi-core/ratified-contracts/projections/synthesized";
import {
  hasSafeRecallTrace,
  parseRecallTraceRef,
} from "@omi-core/ratified-contracts/recall/trace";
import type { RecallTraceV1 } from "@omi-core/ratified-contracts/recall/trace";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import type { SynthesizedMemoryRead as Read } from "@omi-core/ratified-contracts/projections/synthesized";

const id = parseSynthesizedItemId("retrieval-node-v1:2a40f5");
const text = parseSynthesizedText("You use Omi for a synthesized memory workflow.");
const citation = parseCitationRef("citation-v1:bright-coral-harbor");
const cursor = parseKeysetCursor("v1.signature.payload");
const declaredFrontier = parseRecallFrontier("frontier-v1:declared");
const includedFrontier = parseRecallFrontier("frontier-v1:included");
const traceRef = parseRecallTraceRef("trace-v1:fixture");
if (!id || !text || !citation || !cursor || !declaredFrontier || !includedFrontier || !traceRef) {
  throw new Error("fixture boundary values must parse");
}

const page: Read.Page = {
  contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
  items: [{
    id,
    text,
    citations: [citation],
    provenance: {
      synthesisVersion: "synthesis-v1",
      inputDigest: "sha256:input-fixture",
      outputDigest: "sha256:output-fixture",
    },
  }],
  window: { status: "more", complete: false, hasMore: true, nextCursor: cursor },
  completeness: {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier,
      newestIncludedStmFrontier: includedFrontier,
      missingStmFrontierReason: null,
    },
  },
  absence: null,
};

if (!hasHonestPageWindow(page.window)) throw new Error("valid page window rejected");
if (!hasHonestRecallCompleteness(page)) throw new Error("valid completeness envelope rejected");

const trace: RecallTraceV1 = {
  version: "recall-trace-v1",
  traceRef,
  strategyVersion: "strategy-v1",
  projectionFreshness: "fresh",
  outcome: "grounded",
  latencyMs: 12,
  tokenCounts: { input: 10, output: 4 },
  stages: {
    eligible: [traceRef], selected: [traceRef], hydrated: [traceRef],
    policyEligible: [traceRef], cited: [traceRef], grounded: [traceRef],
  },
};
if (!hasSafeRecallTrace(trace)) throw new Error("valid content-safe trace rejected");

// @ts-expect-error a complete page cannot advertise a continuation cursor.
const invalidComplete: Read.Page = { ...page, window: { status: "complete", complete: true, hasMore: false, nextCursor: cursor } };
void invalidComplete;

// @ts-expect-error a page with continuation cannot serialize query-gap absence.
const invalidContinuationAbsence: Read.Page = { ...page, absence: { kind: "query_gap" } };
void invalidContinuationAbsence;

// @ts-expect-error a terminal incomplete window cannot carry a cursor.
const invalidTerminalCursor: Read.Window = { status: "incomplete", complete: false, hasMore: false, nextCursor: cursor };
void invalidTerminalCursor;

// @ts-expect-error a continuing incomplete window requires its opaque cursor.
const invalidMissingCursor: Read.Window = { status: "incomplete", complete: false, hasMore: true, nextCursor: null };
void invalidMissingCursor;

// @ts-expect-error unvalidated strings cannot bypass the non-empty item-id boundary.
const invalidEmptyId: Read.Item = { ...page.items[0]!, id: "" };
void invalidEmptyId;

// @ts-expect-error unvalidated strings cannot bypass the non-empty text boundary.
const invalidEmptyText: Read.Item = { ...page.items[0]!, text: "" };
void invalidEmptyText;

// @ts-expect-error no-selection means the selected stage is empty.
const invalidNoSelectionTrace: RecallTraceV1 = { ...trace, outcome: "no_selection", stages: { ...trace.stages, selected: [traceRef], hydrated: [], policyEligible: [], cited: [], grounded: [] } };
void invalidNoSelectionTrace;

// @ts-expect-error degraded traces require a non-fresh projection state.
const invalidFreshDegradedTrace: RecallTraceV1 = { ...trace, outcome: "degraded", projectionFreshness: "fresh", stages: { ...trace.stages, grounded: [] } };
void invalidFreshDegradedTrace;

// @ts-expect-error grounded outcomes require at least one grounded reference.
const invalidEmptyGroundedTrace: RecallTraceV1 = { ...trace, stages: { ...trace.stages, grounded: [] } };
void invalidEmptyGroundedTrace;

type AssertNever<Value extends never> = Value;
type ExactKeys<Actual, Expected extends PropertyKey> =
  Exclude<keyof Actual, Expected> | Exclude<Expected, keyof Actual>;
type ItemShapeMustStayFrozen = AssertNever<ExactKeys<Read.Item, "id" | "text" | "citations" | "provenance">>;
type ProvenanceShapeMustStayFrozen = AssertNever<ExactKeys<Read.Provenance, "synthesisVersion" | "inputDigest" | "outputDigest">>;
type PageShapeMustStayFrozen = AssertNever<ExactKeys<Read.Page, "contractVersion" | "items" | "window" | "completeness" | "absence">>;
type WindowShapeMustStayFrozen = AssertNever<ExactKeys<Read.Window, "status" | "complete" | "hasMore" | "nextCursor">>;
void (null as unknown as ItemShapeMustStayFrozen);
void (null as unknown as ProvenanceShapeMustStayFrozen);
void (null as unknown as PageShapeMustStayFrozen);
void (null as unknown as WindowShapeMustStayFrozen);
type ForbiddenPublicFields = Extract<
  keyof Read.Item | keyof Read.Page | keyof Read.Provenance | keyof Read.Window,
  | "content" | "locked" | "visibility" | "category" | "review" | "reviewed"
  | "transcript" | "tags" | "tier" | "layer" | "cohort" | "store"
  | "appId" | "app" | "ownerId" | "owner" | "key" | "summary"
  | "displayOrder" | "order" | "stale" | "failure"
  | "accountGeneration" | "ownerGeneration" | "projectionGeneration" | "graphGeneration"
  | "commitId" | "frontierId" | "renderManifest" | "policyLabel" | "policyClass"
>;
type ForbiddenFieldsMustStayAbsent = AssertNever<ForbiddenPublicFields>;
void (null as unknown as ForbiddenFieldsMustStayAbsent);

// @ts-expect-error the package root is deliberately not exported.
type PackageRootMustStayAbsent = import("@omi-core/ratified-contracts").Memory;
void (null as unknown as PackageRootMustStayAbsent);

export const consumerResult = {
  contractVersion: page.contractVersion,
  firstId: page.items[0]?.id,
  complete: page.window.complete,
} as const;
