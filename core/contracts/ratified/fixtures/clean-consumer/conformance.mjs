import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";
import {
  isTrustedTaskCompletenessHonest,
  isTrustedTaskPageData,
  isTrustedTaskWindowHonest,
  parseTaskPageJson,
  TASK_ITEM_FIELDS,
} from "@omi-core/ratified-contracts/projections/tasks";
import { isTrustedRecallTraceData, parseRecallTraceJson } from "@omi-core/ratified-contracts/recall/trace";
import {
  parseWriteOpEnvelopeJson,
  readWriteAvailabilitySignal,
  readWriteRefusalOutcome,
  WRITE_AVAILABILITY,
  WRITE_REFUSALS,
} from "@omi-core/ratified-contracts/write/ops";

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

const mixedReasonPage = structuredClone((await fixture("page-conformance.json")).find((row) => row.safe).page);
mixedReasonPage.completeness.status = "degraded";
mixedReasonPage.completeness.reasons = ["projection_stale", "accepted_work_pending", "source_bound"];
mixedReasonPage.completeness.frontiers.newestSearchedAcceptedFrontier = "frontier-v1:behind";
const parsedMixedReasonPage = parseSynthesizedPageJson(JSON.stringify(mixedReasonPage));
assert.ok(parsedMixedReasonPage);
assert.deepEqual(parsedMixedReasonPage.completeness.reasons, mixedReasonPage.completeness.reasons);

const canonicalPage = structuredClone((await fixture("page-conformance.json")).find((row) => row.safe).page);
delete canonicalPage.items[0].citations;
const canonicalTrace = (await fixture("recall-trace.json")).find((row) => row.safe).trace;
const canonicalPageRaw = JSON.stringify(canonicalPage);
const canonicalTraceRaw = JSON.stringify(canonicalTrace);
const originalToJSON = Object.getOwnPropertyDescriptor(Object.prototype, "toJSON");
const originalCitations = Object.getOwnPropertyDescriptor(Object.prototype, "citations");
const originalGet = Object.getOwnPropertyDescriptor(Object.prototype, "get");
const originalSet = Object.getOwnPropertyDescriptor(Object.prototype, "set");
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
  definePrototypeGetter("get", () => { inheritedGetterCalls += 1; return undefined; });
  definePrototypeGetter("set", () => { inheritedGetterCalls += 1; return undefined; });
  parsedPage = parseSynthesizedPageJson(canonicalPageRaw);
  parsedTrace = parseRecallTraceJson(canonicalTraceRaw);
} finally {
  restorePrototypeProperty("toJSON", originalToJSON);
  restorePrototypeProperty("citations", originalCitations);
  restorePrototypeProperty("get", originalGet);
  restorePrototypeProperty("set", originalSet);
}
assert.ok(parsedPage);
assert.ok(parsedTrace);
assert.equal(inheritedGetterCalls, 0);

// The write-ops corpus of record, read from the INSTALLED package rather than
// from source: this is the only consumer in the tree that sees exactly the
// bytes a backend would install, and rule 15 is about the real shape.
const writeOpsSchema = await fixture("write-ops-outcomes.json");
for (const row of writeOpsSchema.outcomes) {
  if (row.kind === "availability") {
    assert.equal(WRITE_AVAILABILITY[row.outcome].status, row.status, `${row.outcome} status`);
    assert.equal(WRITE_AVAILABILITY[row.outcome].body, row.body, `${row.outcome} body`);
    assert.equal(readWriteAvailabilitySignal(row.status, row.body), row.outcome, `${row.outcome} round trip`);
    assert.equal(readWriteRefusalOutcome(row.status, row.body), null, `${row.outcome} is not a refusal outcome`);
    continue;
  }
  if (row.kind !== "refusal") continue;
  assert.equal(WRITE_REFUSALS[row.outcome].status, row.status, `${row.outcome} status`);
  assert.equal(WRITE_REFUSALS[row.outcome].body, row.body, `${row.outcome} body`);
  assert.equal(readWriteRefusalOutcome(row.status, row.body), row.outcome, `${row.outcome} round trip`);
}
for (const row of await fixture("write-ops-conformance.json")) {
  assert.equal(parseWriteOpEnvelopeJson(row.requestBody) !== null, row.envelopeAccepted, row.name);
}

// The tasks read corpus of record, read from the INSTALLED package for the same
// reason the write-ops corpus is: a consumer that hand-authors the counterpart's
// payload is testing its author's memory of the wire (rule 15).
const tasksShape = await fixture("tasks-read-shape.json");
const tasksCorpus = await fixture("tasks-read-conformance.json");
assert.ok(tasksCorpus.length >= tasksShape.cases.length + tasksShape.refusalLaws.length,
  "the tasks corpus must cover at least every declared case and refusal law");
assert.deepEqual([...TASK_ITEM_FIELDS], tasksShape.itemFields,
  "the shipped module and the shipped schema of record must agree on the thirteen fields");
const tasksCovered = new Set();
for (const row of tasksCorpus) {
  assert.equal(isTrustedTaskPageData(row.page), row.safe, row.wireCase);
  assert.equal(parseTaskPageJson(JSON.stringify(row.page)) !== null, row.safe, `${row.wireCase} raw`);
  // The window law is checked independently of the page law: a page can be
  // rejected for a dozen reasons, so asserting only at the page level would let
  // a broken window law hide behind an unrelated refusal.
  if (row.safe) assert.ok(isTrustedTaskWindowHonest(row.page.window), `${row.wireCase} window`);
  if (row.safe) assert.ok(isTrustedTaskCompletenessHonest(row.page), `${row.wireCase} coverage`);
  tasksCovered.add(row.wireCase);
}
for (const { case: declared } of [...tasksShape.cases, ...tasksShape.refusalLaws]) {
  assert.ok(tasksCovered.has(declared), `tasks case ${declared} is declared but has no corpus row`);
}

async function fixture(name) {
  return JSON.parse(await readFile(new URL(name, fixtureRoot), "utf8"));
}

function restorePrototypeProperty(name, descriptor) {
  Reflect.deleteProperty(Object.prototype, name);
  if (descriptor) Object.defineProperty(Object.prototype, name, copyPropertyDescriptor(descriptor));
}

function definePrototypeGetter(name, getter) {
  const descriptor = Object.create(null);
  descriptor.configurable = true;
  descriptor.get = getter;
  Object.defineProperty(Object.prototype, name, descriptor);
}

function copyPropertyDescriptor(source) {
  const copy = Object.create(null);
  for (const key of ["configurable", "enumerable", "value", "writable", "get", "set"]) {
    if (Object.hasOwn(source, key)) copy[key] = source[key];
  }
  return copy;
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
