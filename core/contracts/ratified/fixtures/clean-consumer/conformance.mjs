import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";
import { isTrustedRecallTraceData, parseRecallTraceJson } from "@omi-core/ratified-contracts/recall/trace";

const fixtureRoot = new URL("./node_modules/@omi-core/ratified-contracts/fixtures/", import.meta.url);
for (const row of await fixture("page-conformance.json")) {
  assert.equal(isTrustedSynthesizedPageData(row.page), row.safe, row.name);
  assert.equal(parseSynthesizedPageJson(JSON.stringify(row.page)) !== null, row.safe, `${row.name} raw`);
}
for (const row of await fixture("read-page-windows.json")) {
  assert.equal(isTrustedPageWindowHonest(row.window), row.honest, row.name);
}
for (const row of await fixture("recall-completeness.json")) {
  assert.equal(isTrustedRecallCompletenessHonest(row.page), row.honest, row.name);
}
for (const row of await fixture("recall-trace.json")) {
  assert.equal(isTrustedRecallTraceData(row.trace), row.safe, row.name);
  assert.equal(parseRecallTraceJson(JSON.stringify(row.trace)) !== null, row.safe, `${row.name} raw`);
}
for (const row of await fixture("status-matrix.json")) {
  assert.equal(isTrustedSynthesizedPageData(statusMatrixPage(row)), row.safe, `${row.window}/${row.completeness}`);
}

const canonicalPage = structuredClone((await fixture("page-conformance.json")).find((row) => row.safe).page);
delete canonicalPage.items[0].citations;
const canonicalTrace = (await fixture("recall-trace.json")).find((row) => row.safe).trace;
const canonicalPageRaw = JSON.stringify(canonicalPage);
const canonicalTraceRaw = JSON.stringify(canonicalTrace);
const originalToJSON = Object.getOwnPropertyDescriptor(Object.prototype, "toJSON");
const originalCitations = Object.getOwnPropertyDescriptor(Object.prototype, "citations");
let inheritedGetterCalls = 0;
let parsedPage;
let parsedTrace;
try {
  Object.defineProperty(Object.prototype, "toJSON", {
    configurable: true,
    get() { inheritedGetterCalls += 1; return undefined; },
  });
  Object.defineProperty(Object.prototype, "citations", {
    configurable: true,
    get() { inheritedGetterCalls += 1; return ["citation-v1:inherited"]; },
  });
  parsedPage = parseSynthesizedPageJson(canonicalPageRaw);
  parsedTrace = parseRecallTraceJson(canonicalTraceRaw);
} finally {
  restorePrototypeProperty("toJSON", originalToJSON);
  restorePrototypeProperty("citations", originalCitations);
}
assert.ok(parsedPage);
assert.ok(parsedTrace);
assert.equal(inheritedGetterCalls, 0);

async function fixture(name) {
  return JSON.parse(await readFile(new URL(name, fixtureRoot), "utf8"));
}

function restorePrototypeProperty(name, descriptor) {
  if (descriptor) Object.defineProperty(Object.prototype, name, descriptor);
  else delete Object.prototype[name];
}

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
