import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  parseKeysetCursor,
} from "../dist/pagination/cursor.js";
import {
  hasHonestPageWindow,
  hasHonestRecallCompleteness,
  hasSafeSynthesizedPage,
  parseCitationRef,
  parseSynthesizedItemId,
  parseSynthesizedText,
} from "../dist/projections/synthesized.js";
import { hasSafeRecallTrace, parseRecallTraceRef } from "../dist/recall/trace.js";

test("ready item boundaries reject empty identifiers, text, and citations", () => {
  assert.equal(parseSynthesizedItemId("retrieval-node-v1:2a40f5"), "retrieval-node-v1:2a40f5");
  assert.equal(parseSynthesizedItemId(""), null);
  assert.equal(parseSynthesizedText("rendered memory"), "rendered memory");
  assert.equal(parseSynthesizedText("   "), null);
  assert.equal(parseCitationRef("citation-v1:bright-coral-harbor"), "citation-v1:bright-coral-harbor");
  assert.equal(parseCitationRef(""), null);
});

test("keyset cursors remain opaque and transport-safe", () => {
  assert.equal(parseKeysetCursor("v1.signature.payload"), "v1.signature.payload");
  assert.equal(parseKeysetCursor("contains whitespace"), null);
  assert.equal(parseKeysetCursor(""), null);
});

test("conformance fixtures reject false completeness", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/read-page-windows.json", import.meta.url), "utf8"));
  for (const row of fixture) {
    assert.equal(hasHonestPageWindow(row.window), row.honest, row.name);
  }
});

test("recall completeness fixtures reject overstated absence and missing frontiers", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/recall-completeness.json", import.meta.url), "utf8"));
  for (const row of fixture) {
    assert.equal(hasHonestRecallCompleteness(row.page), row.honest, row.name);
  }
});

test("strict page fixtures reject extra nested and legacy fields", async () => {
  const fixture = JSON.parse(await readFile(new URL("../fixtures/page-conformance.json", import.meta.url), "utf8"));
  for (const row of fixture) assert.equal(hasSafeSynthesizedPage(row.page), row.safe, row.name);
});

test("content-safe recall trace validates opaque refs and bounded counts", () => {
  const traceRef = parseRecallTraceRef("trace-v1:fixture");
  assert.ok(traceRef);
  assert.equal(hasSafeRecallTrace({
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
  for (const row of fixture) assert.equal(hasSafeRecallTrace(row.trace), row.safe, row.name);
});
