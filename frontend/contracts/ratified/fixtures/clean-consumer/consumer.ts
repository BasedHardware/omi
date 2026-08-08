import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";

import {
  APP_CONTRACT_FLOOR_VERSION,
  APP_CONTRACT_VERSION_HEADER,
  SYNTHESIZED_READ_CONTRACT_VERSION,
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  isWellFormedContractVersion,
  parseCitationRef,
  parseRecallFrontier,
  parseSha256Digest,
  parseSynthesizedPageJson,
  parseSynthesizedItemId,
  parseSynthesizedText,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";
import {
  isTrustedRecallTraceData,
  parseRecallTraceJson,
  parseRecallTraceRef,
} from "@omi-core/ratified-contracts/recall/trace";
import type { RecallTraceV1 } from "@omi-core/ratified-contracts/recall/trace";
import {
  isTrustedWriteOpEnvelope,
  isWritableDomain,
  mintWriteId,
  parseWriteId,
  parseWriteOpEnvelopeJson,
  readWriteRefusalOutcome,
  WRITE_ERRORS,
  WRITE_ID_ENTROPY_BYTES,
  WRITE_REFUSALS,
  writeOpsPath,
} from "@omi-core/ratified-contracts/write/ops";
import type { WriteId, WriteOpEnvelope, WriteRefusalOutcome } from "@omi-core/ratified-contracts/write/ops";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import type { SynthesizedMemoryRead as Read } from "@omi-core/ratified-contracts/projections/synthesized";

const id = parseSynthesizedItemId("retrieval-node-v1:2a40f5");
const text = parseSynthesizedText("You use Omi for a synthesized memory workflow.");
const citation = parseCitationRef("citation-v1:bright-coral-harbor");
const cursor = parseKeysetCursor("v1.signature.payload");
const declaredFrontier = parseRecallFrontier("frontier-v1:declared");
const includedFrontier = parseRecallFrontier("frontier-v1:included");
const behindFrontier = parseRecallFrontier("frontier-v1:behind");
const inputDigest = parseSha256Digest("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
const outputDigest = parseSha256Digest("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
const traceRef = parseRecallTraceRef("trace-v1:fixture");
if (!id || !text || !citation || !cursor || !declaredFrontier || !includedFrontier || !behindFrontier || !inputDigest || !outputDigest || !traceRef) {
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
      inputDigest,
      outputDigest,
    },
  }],
  window: { status: "more", complete: false, hasMore: true, nextCursor: cursor },
  completeness: {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier,
      newestSearchedAcceptedFrontier: declaredFrontier,
      missingAcceptedFrontierReason: null,
      // domain-pending(DIV-DOMCORE-006)
      newestSearchedStmFrontier: includedFrontier,
      missingStmFrontierReason: null,
    },
  },
  absence: null,
};

if (!isTrustedPageWindowHonest(page.window)) throw new Error("valid page window rejected");
if (!isTrustedRecallCompletenessHonest(page)) throw new Error("valid completeness envelope rejected");
if (!isTrustedSynthesizedPageData(page)) throw new Error("valid trusted page rejected");
if (!parseSynthesizedPageJson(JSON.stringify(page))) throw new Error("valid canonical page JSON rejected");

const mixedDegradedRecall: Read.DegradedRecall = {
  version: "recall-completeness-v1",
  status: "degraded",
  reasons: ["projection_stale", "accepted_work_pending", "source_bound"],
  frontiers: {
    declaredFrontier,
    newestSearchedAcceptedFrontier: behindFrontier,
    missingAcceptedFrontierReason: null,
    // domain-pending(DIV-DOMCORE-006)
    newestSearchedStmFrontier: includedFrontier,
    missingStmFrontierReason: null,
  },
};
const mixedIncompleteRecall: Read.IncompleteRecall = {
  ...mixedDegradedRecall,
  status: "incomplete",
  reasons: ["accepted_work_pending", "time_bound"],
};
void mixedDegradedRecall;
void mixedIncompleteRecall;

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
if (!isTrustedRecallTraceData(trace)) throw new Error("valid content-safe trace rejected");
if (!parseRecallTraceJson(JSON.stringify(trace))) throw new Error("valid canonical trace JSON rejected");

const invalidDigest: Read.Provenance = {
  synthesisVersion: "synthesis-v1",
  // @ts-expect-error provenance digests must come from the lowercase SHA-256 parser.
  inputDigest: "arbitrary\nwire-value",
  outputDigest,
};
void invalidDigest;

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

// @ts-expect-error an incomplete terminal window cannot claim complete recall.
const invalidCompleteRecallIncompleteTerminal: Read.Page = {
  ...page,
  window: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
};
void invalidCompleteRecallIncompleteTerminal;

// @ts-expect-error an incomplete continuation window cannot claim complete recall.
const invalidCompleteRecallIncompleteContinuation: Read.Page = {
  ...page,
  window: { status: "incomplete", complete: false, hasMore: true, nextCursor: cursor },
};
void invalidCompleteRecallIncompleteContinuation;

const invalidIncompleteReason: Read.IncompleteRecall = {
  version: "recall-completeness-v1",
  status: "incomplete",
  // @ts-expect-error incomplete recall excludes the higher-precedence degraded family.
  reasons: ["projection_stale"],
  frontiers: page.completeness.frontiers,
};
void invalidIncompleteReason;

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

// The declared-version resolver never rejects: absent, empty, and malformed
// input all fall back to the floor rather than throwing or reflecting the
// raw value.
if (resolveDeclaredContractVersion(undefined) !== APP_CONTRACT_FLOOR_VERSION) throw new Error("missing header must resolve to the floor");
if (resolveDeclaredContractVersion(null) !== APP_CONTRACT_FLOOR_VERSION) throw new Error("null header must resolve to the floor");
if (resolveDeclaredContractVersion("") !== APP_CONTRACT_FLOOR_VERSION) throw new Error("empty header must resolve to the floor");
if (resolveDeclaredContractVersion("not-a-version") !== APP_CONTRACT_FLOOR_VERSION) throw new Error("malformed header must resolve to the floor");
if (resolveDeclaredContractVersion("2.3.1") !== "2.3.1") throw new Error("well-formed header must pass through verbatim");
if (!isWellFormedContractVersion(APP_CONTRACT_FLOOR_VERSION)) throw new Error("the floor itself must be well-formed");
if (APP_CONTRACT_VERSION_HEADER !== "x-omi-contract-version") throw new Error("header name must stay stable across the tarball boundary");

export const consumerResult = {
  contractVersion: page.contractVersion,
  firstId: page.items[0]?.id,
  complete: page.window.complete,
  declaredContractVersionHeader: APP_CONTRACT_VERSION_HEADER,
  declaredContractFloorVersion: APP_CONTRACT_FLOOR_VERSION,
} as const;

// ── The write wire, exercised across the tarball boundary ──────────────────
// A consumer that only typechecks proves the .d.ts parses. These lines prove
// the shipped RUNTIME behaves, which is the half that has been wrong before.
const mintedWriteId: WriteId | null = mintWriteId(new Uint8Array(WRITE_ID_ENTROPY_BYTES).fill(0x5a));
if (mintedWriteId === null) throw new Error("minting from 32 bytes must succeed");
if (parseWriteId("edit-task-set-done") !== null) throw new Error("a word slug must never parse as a write_id");
if (isWritableDomain("memories")) throw new Error("memories is read-only by ratified design");
if (writeOpsPath("tasks") !== "/v1/tasks/ops") throw new Error("route shape drifted");

const staleEpochOutcome: WriteRefusalOutcome | null = readWriteRefusalOutcome(
  WRITE_REFUSALS.stale_epoch.status,
  WRITE_REFUSALS.stale_epoch.body,
);
if (staleEpochOutcome !== "stale_epoch") throw new Error("stale_epoch must be readable off the wire body");
if (readWriteRefusalOutcome(WRITE_ERRORS.conflict.status, WRITE_ERRORS.conflict.body) !== null) {
  throw new Error("conflict must never read as a refusal outcome — it is not one");
}
// The 503 body is under escalation and is deliberately unratified; a consumer
// must be able to see that as a value rather than discovering an empty string.
if (WRITE_ERRORS.maintenance.body !== null) throw new Error("the 503 body must stay unratified");

const sampleEnvelope: WriteOpEnvelope | null = parseWriteOpEnvelopeJson(
  JSON.stringify({
    write_id: mintedWriteId,
    account_epoch: 7,
    domain: "tasks",
    op: { op: "patch", record_id: "task-9f21", patch: { done: true } },
  }),
);
if (sampleEnvelope === null || !isTrustedWriteOpEnvelope(sampleEnvelope)) {
  throw new Error("a well-formed tasks envelope must parse");
}
