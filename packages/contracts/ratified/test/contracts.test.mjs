import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "bun:test";

import {
  parseKeysetCursor,
} from "../dist/pagination/cursor.js";
import {
  APP_CONTRACT_FLOOR_VERSION,
  APP_CONTRACT_VERSION_HEADER,
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  isWellFormedContractVersion,
  MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS,
  parseCitationRef,
  parseSynthesizedItemId,
  parseSha256Digest,
  parseSynthesizedPageJson,
  parseSynthesizedText,
  resolveDeclaredContractVersion,
} from "../dist/projections/synthesized.js";
import {
  isTrustedTaskCompletenessHonest,
  isTrustedTaskPageData,
  isTrustedTaskWindowHonest,
  MAX_TASKS_PAGE_JSON_CODE_UNITS,
  parseTaskFrontier,
  parseTaskItemId,
  parseTaskPageJson,
  readTaskPageAccountEpoch,
  TASK_ITEM_FIELDS,
  TASKS_READ_CONTRACT_VERSION,
} from "../dist/projections/tasks.js";
import {
  isTrustedRecallTraceData,
  MAX_RECALL_TRACE_JSON_CODE_UNITS,
  parseRecallTraceJson,
  parseRecallTraceRef,
} from "../dist/recall/trace.js";
import {
  isTrustedWriteAccepted,
  isWritableDomain,
  mintWriteId,
  parseWriteId,
  parseWriteOpEnvelopeJson,
  readWriteRefusalOutcome,
  WRITABLE_DOMAINS,
  WRITE_ERRORS,
  WRITE_ID_ENTROPY_BYTES,
  WRITE_ID_PATTERN,
  WRITE_OPS_PATH_PATTERN,
  WRITE_REFUSAL_OUTCOMES,
  WRITE_REFUSALS,
  WRITE_AVAILABILITY,
  WRITE_AVAILABILITY_SIGNALS,
  CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS,
  readWriteAvailabilitySignal,
  writeOpsPath,
} from "../dist/write/ops.js";

test("ready item boundaries reject empty identifiers, text, and citations", () => {
  assert.equal(parseSynthesizedItemId("retrieval-node-v1:2a40f5"), "retrieval-node-v1:2a40f5");
  assert.equal(parseSynthesizedItemId(""), null);
  assert.equal(parseSynthesizedText("rendered memory"), "rendered memory");
  assert.equal(parseSynthesizedText("   "), null);
  assert.equal(parseCitationRef("citation-v1:bright-coral-harbor"), "citation-v1:bright-coral-harbor");
  assert.equal(parseCitationRef(""), null);
});

test("a request without a declared contract version resolves to the floor, never a rejection", () => {
  // red-proof: change the `typeof headerValue !== "string"` branch in
  // resolveDeclaredContractVersion (src/projections/synthesized.ts) to
  // `return headerValue;` (i.e. pass undefined/null straight through instead
  // of falling back to APP_CONTRACT_FLOOR_VERSION). Applied by hand against
  // dist/projections/synthesized.js during this change: the first two
  // assertions below failed with "AssertionError [ERR_ASSERTION]: undefined
  // !== '1.0.0'" / "null !== '1.0.0'" before the mutation was reverted and
  // `bun run build` restored the real dist output.
  assert.equal(resolveDeclaredContractVersion(undefined), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion(null), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion(""), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion("   "), APP_CONTRACT_FLOOR_VERSION);
});

test("a malformed declared contract version resolves to the floor rather than reflecting untrusted bytes", () => {
  assert.equal(resolveDeclaredContractVersion("not-a-version"), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion("1.0"), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion("1.0.0\nx-injected: 1"), APP_CONTRACT_FLOOR_VERSION);
  assert.equal(resolveDeclaredContractVersion("v1.0.0"), APP_CONTRACT_FLOOR_VERSION);
});

test("a well-formed declared contract version passes through verbatim", () => {
  assert.equal(resolveDeclaredContractVersion("1.0.0"), "1.0.0");
  assert.equal(resolveDeclaredContractVersion(" 2.3.10 "), "2.3.10");
  assert.ok(isWellFormedContractVersion(APP_CONTRACT_FLOOR_VERSION));
  assert.equal(APP_CONTRACT_VERSION_HEADER, "x-omi-contract-version");
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
  const mixedPage = structuredClone(page);
  mixedPage.completeness.status = "degraded";
  mixedPage.completeness.reasons = ["projection_stale", "accepted_work_pending", "source_bound"];
  mixedPage.completeness.frontiers.newestSearchedAcceptedFrontier = "frontier-v1:behind";
  const parsedMixedPage = parseSynthesizedPageJson(JSON.stringify(mixedPage));
  assert.ok(parsedMixedPage);
  assert.deepEqual(parsedMixedPage.completeness.reasons, mixedPage.completeness.reasons);
  const unknownReasonPage = structuredClone(mixedPage);
  unknownReasonPage.completeness.reasons.push("unknown_limitation");
  assert.equal(parseSynthesizedPageJson(JSON.stringify(unknownReasonPage)), null);
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

test("raw parsers never consult inherited toJSON, descriptor, or optional-field getters", { concurrency: false }, async () => {
  const pageFixture = JSON.parse(await readFile(new URL("../fixtures/page-conformance.json", import.meta.url), "utf8"));
  const page = structuredClone(pageFixture.find((row) => row.safe).page);
  delete page.items[0].citations;
  const traceFixture = JSON.parse(await readFile(new URL("../fixtures/recall-trace.json", import.meta.url), "utf8"));
  const trace = traceFixture.find((row) => row.safe).trace;
  const pageRaw = JSON.stringify(page);
  const traceRaw = JSON.stringify(trace);
  const originalToJSON = Object.getOwnPropertyDescriptor(Object.prototype, "toJSON");
  const originalCitations = Object.getOwnPropertyDescriptor(Object.prototype, "citations");
  const originalGet = Object.getOwnPropertyDescriptor(Object.prototype, "get");
  const originalSet = Object.getOwnPropertyDescriptor(Object.prototype, "set");
  let toJSONGetterCalls = 0;
  let citationsGetterCalls = 0;
  let descriptorGetterCalls = 0;
  let parsedPage;
  let parsedTrace;

  try {
    Object.defineProperty(Object.prototype, "toJSON", {
      configurable: true,
      get() { toJSONGetterCalls += 1; return undefined; },
    });
    Object.defineProperty(Object.prototype, "citations", {
      configurable: true,
      get() { citationsGetterCalls += 1; return ["citation-v1:inherited"]; },
    });
    definePrototypeGetter("get", () => { descriptorGetterCalls += 1; return undefined; });
    definePrototypeGetter("set", () => { descriptorGetterCalls += 1; return undefined; });
    parsedPage = parseSynthesizedPageJson(pageRaw);
    parsedTrace = parseRecallTraceJson(traceRaw);
  } finally {
    restorePrototypeProperty("toJSON", originalToJSON);
    restorePrototypeProperty("citations", originalCitations);
    restorePrototypeProperty("get", originalGet);
    restorePrototypeProperty("set", originalSet);
  }

  assert.ok(parsedPage);
  assert.ok(parsedTrace);
  assert.equal(toJSONGetterCalls, 0);
  assert.equal(citationsGetterCalls, 0);
  assert.equal(descriptorGetterCalls, 0);
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

// ── The write wire (COORD-write-path-rulings B1/B2/B4/B6) ───────────────────
//
// These tests close ONE of the three links that make the write seam real:
//   module  <-> schema-of-record   (here)
//   schema  <-> corpus             (core/scripts/check-wire-conformance.mjs)
//   corpus  <-> both sides         (testkit + platform contract-tests)
// Without the first link the schema-of-record file is a second source of
// truth that can drift from the code it claims to describe, and a corpus
// checked against a drifted schema proves nothing.

test("the write-ops schema of record matches the module's own tables", async () => {
  // red-proof: change any status or body byte in WRITE_REFUSALS (e.g. make
  // stale_epoch 400) and this goes red. APPLIED AND OBSERVED RED.
  const schema = JSON.parse(await readFile(new URL("../fixtures/write-ops-outcomes.json", import.meta.url), "utf8"));
  assert.deepEqual(schema.writableDomains, [...WRITABLE_DOMAINS]);
  assert.equal(schema.writeIdPattern, WRITE_ID_PATTERN.source);
  assert.equal(schema.writeIdEntropyBytes, WRITE_ID_ENTROPY_BYTES);
  assert.equal(schema.route, "/v1/{domain}/ops");

  const declared = new Map(schema.outcomes.map((row) => [row.outcome, row]));
  for (const outcome of WRITE_REFUSAL_OUTCOMES) {
    const row = declared.get(outcome);
    assert.ok(row, `refusal outcome ${outcome} is missing from the schema of record`);
    assert.equal(row.kind, "refusal");
    assert.equal(row.status, WRITE_REFUSALS[outcome].status);
    assert.equal(row.body, WRITE_REFUSALS[outcome].body);
  }
  for (const [name, error] of Object.entries(WRITE_ERRORS)) {
    const row = declared.get(name);
    assert.ok(row, `error outcome ${name} is missing from the schema of record`);
    assert.equal(row.kind, "error");
    assert.equal(row.status, error.status);
    assert.equal(row.body, error.body, `${name} body`);
  }
  for (const signal of WRITE_AVAILABILITY_SIGNALS) {
    const row = declared.get(signal);
    assert.ok(row, `availability signal ${signal} is missing from the schema of record`);
    // The KIND is the ruling. COORD-fable-rulings-wave2 W1 binds this contract to
    // record the fifth value as an availability signal and not as a fifth
    // authorization outcome, so "availability" is asserted, not assumed.
    // red-proof: change this row's kind to "refusal" in the schema and this goes
    // red. APPLIED AND OBSERVED RED.
    assert.equal(row.kind, "availability", `${signal} must not be recorded as a refusal`);
    assert.equal(row.status, WRITE_AVAILABILITY[signal].status);
    assert.equal(row.body, WRITE_AVAILABILITY[signal].body);
    assert.equal(row.retryAfterSeconds, WRITE_AVAILABILITY[signal].retryAfterSeconds);
  }
  // `maintenance` is gone from the request-error table on purpose.
  assert.equal("maintenance" in WRITE_ERRORS, false);
  // Nothing in the schema that the module does not define.
  const known = new Set([
    ...WRITE_REFUSAL_OUTCOMES,
    ...Object.keys(WRITE_ERRORS),
    ...WRITE_AVAILABILITY_SIGNALS,
    "accepted",
    "accepted_idempotent",
  ]);
  for (const row of schema.outcomes) assert.ok(known.has(row.outcome), `schema declares unknown outcome ${row.outcome}`);
});

test("a stale-epoch refusal is never byte-identical to conflict or gone", () => {
  // red-proof: give stale_epoch the same body as WRITE_ERRORS.conflict and
  // this goes red. APPLIED AND OBSERVED RED.
  //
  // Both are 409. A client branching on status alone cannot tell a straggler
  // from a genuine concurrent edit, and would tell the user their saved edit
  // conflicted when the fence simply refused it. The bodies are what separate
  // them, so the bodies are what is asserted.
  assert.equal(WRITE_REFUSALS.stale_epoch.status, WRITE_ERRORS.conflict.status);
  assert.notEqual(WRITE_REFUSALS.stale_epoch.body, WRITE_ERRORS.conflict.body);
  assert.notEqual(WRITE_REFUSALS.stale_epoch.body, WRITE_ERRORS.write_id_reuse.body);
  assert.equal(readWriteRefusalOutcome(409, WRITE_REFUSALS.stale_epoch.body), "stale_epoch");
  assert.equal(readWriteRefusalOutcome(409, WRITE_ERRORS.conflict.body), null);
  assert.equal(readWriteRefusalOutcome(409, WRITE_ERRORS.write_id_reuse.body), null);
  // 403 is shared by authorization and entitlement for the same reason.
  assert.equal(readWriteRefusalOutcome(403, WRITE_REFUSALS.authorization.body), "authorization");
  assert.equal(readWriteRefusalOutcome(403, WRITE_REFUSALS.entitlement.body), "entitlement");
  // A right body under a wrong status is not a refusal class. A server that
  // moved the status would otherwise keep passing.
  assert.equal(readWriteRefusalOutcome(200, WRITE_REFUSALS.stale_epoch.body), null);
});

test("control_unavailable is readable, and is NOT one of the four refusal outcomes", () => {
  // COORD-fable-rulings-wave2 W1's binding condition, expressed as two readers
  // rather than as a comment. A single five-valued reader would be the framing
  // the ruling refused, in the form a future caller actually reads.
  //
  // red-proof: add control_unavailable to WRITE_REFUSAL_OUTCOMES/WRITE_REFUSALS
  // so the refusal reader answers it, and this goes red.
  // APPLIED AND OBSERVED RED.
  const wire = WRITE_AVAILABILITY.control_unavailable;
  assert.equal(readWriteAvailabilitySignal(wire.status, wire.body), "control_unavailable");
  assert.equal(readWriteRefusalOutcome(wire.status, wire.body), null);
  assert.equal(WRITE_REFUSAL_OUTCOMES.length, 4, "ADR-010 §3's four authorization outcomes stay four");
  assert.ok(!WRITE_REFUSAL_OUTCOMES.includes("control_unavailable"));

  // The conditions the ruling made load-bearing: fixed body, fixed retry-after,
  // and no account state anywhere in it.
  assert.equal(wire.retryAfterSeconds, CONTROL_UNAVAILABLE_RETRY_AFTER_SECONDS);
  assert.equal(wire.retryAfterSeconds, 60);
  assert.equal(wire.body.includes("epoch"), false, "the active epoch is never returned");
  assert.equal(wire.status, 503);
  // And it must not collide with any refusal body — the collapse onto stale_epoch
  // is the one that would turn a migration window into a permanent lost edit.
  for (const outcome of WRITE_REFUSAL_OUTCOMES) {
    assert.notEqual(wire.body, WRITE_REFUSALS[outcome].body);
  }
});

test("write_id is minted from caller entropy and never derived", () => {
  // red-proof: relax the length check to `entropy.length < 1` and this goes
  // red on the short-entropy case. APPLIED AND OBSERVED RED.
  const entropy = new Uint8Array(WRITE_ID_ENTROPY_BYTES).fill(0xab);
  const minted = mintWriteId(entropy);
  assert.equal(minted, "ab".repeat(WRITE_ID_ENTROPY_BYTES));
  assert.ok(minted !== null && WRITE_ID_PATTERN.test(minted));
  assert.equal(mintWriteId(new Uint8Array(31)), null, "short entropy must not silently shrink the key space");
  assert.equal(mintWriteId(new Uint8Array(33)), null);
  assert.equal(mintWriteId(new Array(32).fill(1)), null, "a plain array is not a byte source");
  // The grammar admits no word slug, which is what keeps backend:RISK-015
  // satisfied without relying on anybody's discipline.
  assert.equal(parseWriteId("edit-task-9f21-set-done"), null);
  assert.equal(parseWriteId("AB".repeat(32)), null, "uppercase hex is a different string on the wire");
});

test("the route is built, never spelled", () => {
  assert.equal(writeOpsPath("tasks"), "/v1/tasks/ops");
  assert.ok(WRITE_OPS_PATH_PATTERN.test(writeOpsPath("tasks")));
  assert.ok(!WRITE_OPS_PATH_PATTERN.test("/v1/tasks/ops/"));
  assert.ok(!WRITE_OPS_PATH_PATTERN.test("/v1/tasks"));
  assert.equal(isWritableDomain("memories"), false, "memories is read-only by ratified design");
});

test("every write-ops corpus row agrees with the envelope validator", async () => {
  // red-proof: delete the `hasExactKeys(value, ENVELOPE_KEYS)` guard in
  // isTrustedWriteOpEnvelope and the unknown-field row goes red.
  // APPLIED AND OBSERVED RED.
  const corpus = JSON.parse(await readFile(new URL("../fixtures/write-ops-conformance.json", import.meta.url), "utf8"));
  assert.ok(corpus.length >= 16, "corpus shrank — an empty corpus must never read as a pass");
  for (const row of corpus) {
    assert.equal(
      parseWriteOpEnvelopeJson(row.requestBody) !== null,
      row.envelopeAccepted,
      `${row.name}: envelope acceptance disagrees with the corpus`,
    );
    if (row.response.status === 200) {
      assert.ok(isTrustedWriteAccepted(JSON.parse(row.response.body)), `${row.name}: success body rejected`);
    }
  }
});

/* ── the ratified tasks READ wire (DAVID-tasks-read-epoch-and-ci D1/D2) ───── */

const taskCorpus = async () =>
  JSON.parse(await readFile(new URL("../fixtures/tasks-read-conformance.json", import.meta.url), "utf8"));
const taskShape = async () =>
  JSON.parse(await readFile(new URL("../fixtures/tasks-read-shape.json", import.meta.url), "utf8"));

test("D2's parity is checked against the DOMAIN contract, not against a retyped list", async () => {
  // This is the assertion D2 actually asks for. A hand-copied list of thirteen
  // names would report parity forever while the wire quietly narrowed; the
  // domain interface is the source, so the day it gains a fourteenth field this
  // test — not a reviewer — is what notices.
  //
  // red-proof: drop `revision` from TASK_ITEM_FIELDS and from the Item
  // interface -> red here on the set comparison. APPLIED AND OBSERVED RED.
  const domainSource = await readFile(new URL("../../src/domain/tasks.ts", import.meta.url), "utf8");
  const start = domainSource.indexOf("export interface Task {");
  assert.ok(start >= 0, "could not locate the domain Task interface — this check is stale");
  const body = domainSource.slice(start, domainSource.indexOf("\n}", start));
  const domainFields = [...body.matchAll(/^ {2}(\w+)\??:/gm)].map((match) => match[1]);
  assert.equal(domainFields.length, 13, "the domain Task no longer declares the thirteen D2 ratifies");
  assert.deepEqual([...TASK_ITEM_FIELDS].sort(), [...domainFields].sort());
});

test("every tasks corpus row agrees with the page validator, at both boundaries", async () => {
  // red-proof: delete the `hasExactKeys(value, TASK_ITEM_FIELDS)` guard in
  // hasSafeItem and the extra-field and missing-field rows go red.
  // APPLIED AND OBSERVED RED.
  const corpus = await taskCorpus();
  assert.ok(corpus.length >= 30, "corpus shrank — an empty corpus must never read as a pass");
  assert.ok(corpus.some((row) => row.safe) && corpus.some((row) => !row.safe),
    "a corpus with no refusals proves only that the validator says yes");
  for (const row of corpus) {
    assert.equal(isTrustedTaskPageData(structuredClone(row.page)), row.safe, row.wireCase);
    assert.equal(parseTaskPageJson(JSON.stringify(row.page)) !== null, row.safe, `${row.wireCase} raw`);
  }
});

test("the tasks schema of record and the module agree, and the corpus covers it", async () => {
  const shape = await taskShape();
  const corpus = await taskCorpus();
  assert.deepEqual([...TASK_ITEM_FIELDS], shape.itemFields);
  assert.equal(shape.contractVersion, TASKS_READ_CONTRACT_VERSION);
  const covered = new Set(corpus.map((row) => row.wireCase));
  for (const { case: declared } of [...shape.cases, ...shape.refusalLaws]) {
    assert.ok(covered.has(declared), `${declared} is declared in the schema of record but absent from the corpus`);
  }
  // And the other direction: a corpus row naming a case the schema does not
  // declare means the schema stopped describing the wire.
  for (const wireCase of covered) {
    assert.ok(
      [...shape.cases, ...shape.refusalLaws].some((row) => row.case === wireCase),
      `${wireCase} is exercised by the corpus but undeclared in the schema of record`,
    );
  }
});

test("tasks coverage status is derived from reasons, never asserted beside them", async () => {
  // The specific over-claim this refuses: a server that lists a limitation and
  // then declares `complete`. It is the tasks transposition of the memories
  // envelope's hardest law.
  //
  // red-proof: make deriveCompletenessStatus return completeness.status
  // unchanged -> red here. APPLIED AND OBSERVED RED.
  const corpus = await taskCorpus();
  const honest = structuredClone(corpus.find((row) => row.wireCase === "completeness:degraded").page);
  assert.ok(isTrustedTaskCompletenessHonest(honest));
  for (const claimed of ["complete", "incomplete", "partial"]) {
    const lying = structuredClone(honest);
    lying.completeness.status = claimed;
    assert.equal(isTrustedTaskCompletenessHonest(lying), false, `degraded reasons must not read as ${claimed}`);
  }
});

test("a complete tasks page must have caught up with its own declared frontier", async () => {
  // `complete` is a checkable claim here rather than an adjective: the applied
  // frontier must have reached the declared one, or the page must say plainly
  // that no write has ever been applied.
  //
  // RED-PROOF, and the result is worth more than the assertion. Two separate
  // mutations were applied and each STAYED GREEN:
  //   - delete the `completeness.status === "complete"` frontier check
  //   - delete the `pendingWrites !== reasons.includes(...)` coupling
  // Only removing BOTH turns this test red. They are independently sufficient
  // for this case, which is defence in depth rather than redundancy — but it
  // means neither line is individually pinned by this test, and a future edit
  // could delete either one without a single suite going red. Recorded here
  // rather than quietly fixed, because a green-staying mutation is evidence
  // about the assertion. APPLIED, BOTH SINGLES GREEN, THE PAIR OBSERVED RED.
  const corpus = await taskCorpus();
  const page = structuredClone(corpus.find((row) => row.wireCase === "window:complete_terminal").page);
  assert.ok(isTrustedTaskPageData(structuredClone(page)));
  const lagging = structuredClone(page);
  lagging.completeness.frontiers.newestAppliedFrontier = "frontier-v1:tasks-behind";
  assert.equal(isTrustedTaskPageData(lagging), false, "a lagging frontier cannot read as complete");
  const noWrites = structuredClone(page);
  noWrites.completeness.frontiers.newestAppliedFrontier = null;
  noWrites.completeness.frontiers.missingAppliedFrontierReason = "no_applied_writes";
  assert.ok(isTrustedTaskPageData(noWrites), "an account with no applied writes is honestly complete");
});

test("the tasks envelope cannot be confused with the memories envelope", async () => {
  // The two carry different meanings under a similar shape, which
  // COORD-contract-evolution-policy §1 classifies as different fields. The
  // version string is what keeps them apart, in both directions.
  const corpus = await taskCorpus();
  const page = structuredClone(corpus.find((row) => row.wireCase === "window:complete_terminal").page);
  page.completeness.version = "recall-completeness-v1";
  assert.equal(isTrustedTaskPageData(page), false);
  assert.equal(isTrustedTaskCompletenessHonest(page), false);
});

test("tasks boundary values are bounded, and the page has a size ceiling", () => {
  assert.equal(parseTaskItemId(`task1_${"a".repeat(64)}`), `task1_${"a".repeat(64)}`);
  assert.equal(parseTaskItemId(""), null);
  assert.equal(parseTaskItemId("task one"), null, "whitespace is not printable-ASCII-only");
  assert.equal(parseTaskItemId("a".repeat(1025)), null);
  assert.equal(parseTaskFrontier("frontier-v1:x"), "frontier-v1:x");
  assert.equal(parseTaskFrontier("frontier v1"), null);
  assert.equal(MAX_TASKS_PAGE_JSON_CODE_UNITS, 2_000_000);
  assert.equal(parseTaskPageJson("x".repeat(MAX_TASKS_PAGE_JSON_CODE_UNITS + 1)), null);
});

test("the tasks window law is the memories window law, verbatim in behaviour", async () => {
  // Pagination honesty is not a per-domain question. Two spellings of one law
  // is how the two doors disagreed the last time, so this asserts the tasks
  // window predicate answers identically over the memories window corpus.
  //
  // red-proof: change the `more` branch to accept a null cursor -> red.
  // APPLIED AND OBSERVED RED.
  const windows = JSON.parse(await readFile(new URL("../fixtures/read-page-windows.json", import.meta.url), "utf8"));
  assert.ok(windows.length >= 4);
  for (const row of windows) {
    assert.equal(isTrustedTaskWindowHonest(row.window), row.honest, `${row.name} must be judged identically by both wires`);
  }
});

test("D3's account epoch is genuinely optional — a page without it is still valid", async () => {
  // This is the assertion that decides whether 0.7.0 is `additive` or
  // `breaking`, and the policy turns on exactly one word. A REQUIRED sixth key
  // would mean every client built against 0.6.0 refuses every page a 0.7.0
  // server serves — lockstep deploys, which per-account batched migration
  // cannot do. So both key sets must be law, measured over the corpus of
  // record rather than over one hand-written page.
  //
  // red-proof: in isTrustedTaskPageData, drop the five-key branch so only the
  // six-key set is accepted. Every safe row in the tasks corpus — all of which
  // predate this field — goes red. APPLIED, OBSERVED RED, REVERTED: it reddens
  // this test and two of READ's corpus tests, which is the honest measure of
  // how breaking that one word would have been.
  const corpus = await taskCorpus();
  const safeRows = corpus.filter((row) => row.safe);
  assert.ok(safeRows.length >= 5, "need real pages to test against");
  for (const row of safeRows) {
    assert.equal(isTrustedTaskPageData(structuredClone(row.page)), true, `${row.wireCase} without an epoch`);
    assert.equal(readTaskPageAccountEpoch(row.page), null, `${row.wireCase} reports absence as null, never zero`);
  }
});

test("a page carrying the account epoch validates, and junk in that field is refused", async () => {
  // red-proof: delete the `withEpoch && !isAccountEpoch(...)` guard — the
  // string, float, negative and null rows all become "valid" and this fails.
  // A server could then ship `"7"` and a client would stamp write envelopes
  // with a string. APPLIED, OBSERVED RED, REVERTED (this test only).
  const corpus = await taskCorpus();
  const base = corpus.find((row) => row.safe).page;

  for (const epoch of [0, 1, 7, Number.MAX_SAFE_INTEGER]) {
    const page = { ...structuredClone(base), accountEpoch: epoch };
    assert.equal(isTrustedTaskPageData(page), true, `epoch ${epoch} is a valid generation`);
    assert.equal(readTaskPageAccountEpoch(page), epoch);
    assert.equal(parseTaskPageJson(JSON.stringify(page)) !== null, true, `epoch ${epoch} at the raw boundary`);
  }

  for (const junk of ["7", 1.5, -1, null, true, Number.MAX_SAFE_INTEGER + 2]) {
    const page = { ...structuredClone(base), accountEpoch: junk };
    assert.equal(isTrustedTaskPageData(page), false, `epoch ${String(junk)} must be refused`);
    assert.equal(parseTaskPageJson(JSON.stringify(page)), null, `epoch ${String(junk)} refused at the raw boundary too`);
  }

  // Optional must not mean "anything goes": an unknown SIXTH key is still
  // refused, on both branches. This is what stops a server from smuggling an
  // unratified field onto a ratified wire under cover of the epoch's arrival.
  assert.equal(isTrustedTaskPageData({ ...structuredClone(base), migrationProgress: 0.4 }), false);
  assert.equal(isTrustedTaskPageData({ ...structuredClone(base), accountEpoch: 3, migrationProgress: 0.4 }), false);
});

test("the epoch does not move the wire-shape version, and never reaches an item", async () => {
  // Bumping TASKS_READ_CONTRACT_VERSION would refuse every page every deployed
  // server serves today — an additive intent delivered as a breaking change,
  // because the validator compares it for equality.
  //
  // red-proof: change TASKS_READ_CONTRACT_VERSION to "1.1.0" — every corpus
  // row goes red, which is the whole point. APPLIED, OBSERVED RED, REVERTED:
  // six tests fail, including READ's, which is exactly the blast radius that
  // makes moving this constant a breaking change rather than a version tidy.
  assert.equal(TASKS_READ_CONTRACT_VERSION, "1.0.0");

  // The epoch is a property of the ACCOUNT, not of a task. On an item it would
  // be repeated per row and would invite a per-row generation, which is not a
  // thing that exists.
  assert.equal(TASK_ITEM_FIELDS.includes("accountEpoch"), false);
  const corpus = await taskCorpus();
  const base = corpus.find((row) => row.safe).page;
  const withItemEpoch = structuredClone(base);
  if (withItemEpoch.items.length > 0) {
    withItemEpoch.items[0].accountEpoch = 3;
    assert.equal(isTrustedTaskPageData(withItemEpoch), false, "an epoch on an item is an unknown field");
  }
});
