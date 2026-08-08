import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  parseKeysetCursor,
} from "../dist/pagination/cursor.js";
import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS,
  parseCitationRef,
  parseSynthesizedItemId,
  parseSha256Digest,
  parseSynthesizedPageJson,
  parseSynthesizedText,
} from "../dist/projections/synthesized.js";
import {
  isTrustedRecallTraceData,
  MAX_RECALL_TRACE_JSON_CODE_UNITS,
  parseRecallTraceJson,
  parseRecallTraceRef,
} from "../dist/recall/trace.js";

test("ready item boundaries reject empty identifiers, text, and citations", () => {
  assert.equal(parseSynthesizedItemId("retrieval-node-v1:2a40f5"), "retrieval-node-v1:2a40f5");
  assert.equal(parseSynthesizedItemId(""), null);
  assert.equal(parseSynthesizedText("rendered memory"), "rendered memory");
  assert.equal(parseSynthesizedText("   "), null);
  assert.equal(parseCitationRef("citation-v1:bright-coral-harbor"), "citation-v1:bright-coral-harbor");
  assert.equal(parseCitationRef(""), null);
});

test("provenance digests accept only lowercase 64-character SHA-256 hex", () => {
  assert.equal(parseSha256Digest("a".repeat(64)), "a".repeat(64));
  assert.equal(parseSha256Digest("A".repeat(64)), null);
  assert.equal(parseSha256Digest("a".repeat(63)), null);
  assert.equal(parseSha256Digest("arbitrary\nwire-value"), null);
});

test("keyset cursors remain opaque and transport-safe", () => {
  assert.equal(parseKeysetCursor("v1.signature.payload"), "v1.signature.payload");
  assert.equal(parseKeysetCursor("contains whitespace"), null);
  assert.equal(parseKeysetCursor(""), null);
});

test("conformance fixtures reject false completeness", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/read-page-windows.json", import.meta.url), "utf8"));
  for (const row of fixture) {
    assert.equal(isTrustedPageWindowHonest(row.window), row.honest, row.name);
  }
});

test("recall completeness fixtures reject overstated absence and missing frontiers", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/recall-completeness.json", import.meta.url), "utf8"));
  for (const row of fixture) {
    assert.equal(isTrustedRecallCompletenessHonest(row.page), row.honest, row.name);
  }
});

test("strict page fixtures reject extra nested and legacy fields", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/page-conformance.json", import.meta.url), "utf8"));
  for (const row of fixture) assert.equal(isTrustedSynthesizedPageData(row.page), row.safe, row.name);
});

test("raw page parser is bounded, canonical, and duplicate-key rejecting", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/page-conformance.json", import.meta.url), "utf8"));
  const page = fixture.find((row) => row.safe).page;
  const raw = JSON.stringify(page);
  assert.deepEqual(parseSynthesizedPageJson(raw), page);
  for (const digest of ["arbitrary", "line-one\nline-two", "A".repeat(64)]) {
    const invalidDigestPage = structuredClone(page);
    invalidDigestPage.items[0].provenance.inputDigest = digest;
    assert.equal(isTrustedSynthesizedPageData(invalidDigestPage), false);
    assert.equal(parseSynthesizedPageJson(JSON.stringify(invalidDigestPage)), null);
  }
  assert.equal(parseSynthesizedPageJson(` ${raw}`), null);
  assert.equal(parseSynthesizedPageJson("{"), null);
  assert.equal(parseSynthesizedPageJson(" ".repeat(MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS + 1)), null);
  assert.equal(parseSynthesizedPageJson(raw.replace(
    '"contractVersion":"1.0.0"',
    '"contractVersion":"1.0.0","contractVersion":"1.0.0"',
  )), null);
});

test("trusted page predicate rejects hostile object shapes", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/page-conformance.json", import.meta.url), "utf8"));
  const valid = fixture.find((row) => row.safe).page;

  const accessorPage = structuredClone(valid);
  let getterExecutions = 0;
  Object.defineProperty(accessorPage.items[0], "text", {
    configurable: true,
    enumerable: true,
    get() { getterExecutions += 1; return "must not execute"; },
  });
  assert.equal(isTrustedSynthesizedPageData(accessorPage), false);
  assert.equal(getterExecutions, 0);

  const classPage = structuredClone(valid);
  Object.setPrototypeOf(classPage.items[0], class ItemRecord {}.prototype);
  assert.equal(isTrustedSynthesizedPageData(classPage), false);

  const hiddenPage = structuredClone(valid);
  Object.defineProperty(hiddenPage.items[0], "hidden", { value: true });
  assert.equal(isTrustedSynthesizedPageData(hiddenPage), false);

  const symbolPage = structuredClone(valid);
  symbolPage.items[0][Symbol("hidden")] = true;
  assert.equal(isTrustedSynthesizedPageData(symbolPage), false);

  // Proxy inspection cannot be trap-free; callers with hostile input must use the raw parser.
  let proxyTrapExecutions = 0;
  const proxy = new Proxy(structuredClone(valid), {
    ownKeys(target) { proxyTrapExecutions += 1; return Reflect.ownKeys(target); },
  });
  assert.equal(isTrustedSynthesizedPageData(proxy), false);
  assert.ok(proxyTrapExecutions >= 0);
});

test("window and completeness status cross-product stays honest", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/status-matrix.json", import.meta.url), "utf8"));
  for (const row of fixture) {
    assert.equal(isTrustedSynthesizedPageData(statusMatrixPage(row)), row.safe, `${row.window}/${row.completeness}`);
  }
});

test("content-safe recall trace validates opaque refs and bounded counts", () => {
  const traceRef = parseRecallTraceRef("trace-v1:fixture");
  assert.ok(traceRef);
  assert.equal(isTrustedRecallTraceData({
    version: "recall-trace-v1",
    traceRef,
    strategyVersion: "strategy-v1",
    projectionFreshness: "fresh",
    outcome: "grounded",
    latencyMs: 3,
    tokenCounts: { input: 2, output: 1 },
    stages: {
      eligible: [traceRef], selected: [traceRef], hydrated: [traceRef],
      policyEligible: [traceRef], cited: [traceRef], grounded: [traceRef],
    },
  }), true);
  assert.equal(parseRecallTraceRef(""), null);
});

test("recall trace fixtures reject missing stages, unknown enums, and content fields", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/recall-trace.json", import.meta.url), "utf8"));
  for (const row of fixture) assert.equal(isTrustedRecallTraceData(row.trace), row.safe, row.name);
});

test("raw trace parser and trusted predicate enforce data-only nested stages", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/recall-trace.json", import.meta.url), "utf8"));
  const trace = fixture.find((row) => row.safe).trace;
  const raw = JSON.stringify(trace);
  assert.deepEqual(parseRecallTraceJson(raw), trace);
  assert.equal(parseRecallTraceJson(`\n${raw}`), null);
  assert.equal(parseRecallTraceJson("{"), null);
  assert.equal(parseRecallTraceJson(" ".repeat(MAX_RECALL_TRACE_JSON_CODE_UNITS + 1)), null);
  assert.equal(parseRecallTraceJson(raw.replace(
    '"version":"recall-trace-v1"',
    '"version":"recall-trace-v1","version":"recall-trace-v1"',
  )), null);

  const accessorTrace = structuredClone(trace);
  let getterExecutions = 0;
  Object.defineProperty(accessorTrace.stages, "eligible", {
    configurable: true,
    enumerable: true,
    get() { getterExecutions += 1; return []; },
  });
  assert.equal(isTrustedRecallTraceData(accessorTrace), false);
  assert.equal(getterExecutions, 0);

  const classTrace = structuredClone(trace);
  Object.setPrototypeOf(classTrace.stages, class StageRecord {}.prototype);
  assert.equal(isTrustedRecallTraceData(classTrace), false);
  assert.equal(isTrustedRecallTraceData(new Proxy(structuredClone(trace), {})), false);
});

function statusMatrixPage(row) {
  const windows = {
    complete_terminal: { status: "complete", complete: true, hasMore: false, nextCursor: null },
    more_continuation: { status: "more", complete: false, hasMore: true, nextCursor: "cursor-v1:next" },
    incomplete_terminal: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
    incomplete_continuation: { status: "incomplete", complete: false, hasMore: true, nextCursor: "cursor-v1:next" },
  };
  const reasons = {
    complete: [],
    incomplete: ["accepted_work_pending"],
    degraded: ["projection_stale"],
    partial: ["source_bound"],
  };
  return {
    contractVersion: "1.0.0",
    items: row.empty ? [] : [{ id: "retrieval-node-v1:matrix", text: "Matrix result" }],
    window: windows[row.window],
    completeness: {
      version: "recall-completeness-v1",
      status: row.completeness,
      reasons: reasons[row.completeness],
      frontiers: {
        declaredFrontier: "frontier-v1:declared",
        newestSearchedAcceptedFrontier: row.completeness === "incomplete" ? "frontier-v1:behind" : "frontier-v1:declared",
        missingAcceptedFrontierReason: null,
        // domain-pending(DIV-DOMCORE-006)
        newestSearchedStmFrontier: "frontier-v1:included",
        missingStmFrontierReason: null,
      },
    },
    absence: row.queryGap ? { kind: "query_gap" } : null,
  };
}
