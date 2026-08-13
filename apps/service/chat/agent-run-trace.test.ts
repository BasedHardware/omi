import { describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

import { createInMemoryAgentRunEventStore } from "./agent-run-events";
import { runAgentRunScenario } from "./agent-run-scenario";
import { canonicalTraceJson, exportAgentRunTrace, replayAgentRunTrace } from "./agent-run-trace";

const HASH = `sha256:${"a".repeat(64)}`;

const makeStore = (
  capabilityId = "internal-capability",
  runId = "internal-run-42",
  attemptId = "internal-attempt-1",
) => {
  const result = runAgentRunScenario({
    runId,
    attemptId,
    capability: { capabilityId, tier: "deterministic-scripted", adapter: "scripted", deterministic: true },
    context: {
      contextReceiptId: "internal-context", sourceKind: "memory", sourceRef: "internal-source",
      sourceHash: HASH, ownerRef: "internal-owner", expiresAt: 100, redactedPreview: "Safe context",
      tokenEstimate: 2, inclusionReason: "bounded", policyDecision: "included",
    },
    statuses: [{ status: "generating", progressPct: 50 }],
    tools: [{ callId: "internal-call", toolName: "safe.lookup", timeoutMs: 1000, idempotencyKey: "internal-idem", result: { summary: "Safe result", durationMs: 4, retryable: false } }],
    usage: { usageId: "internal-usage", inputTokens: 3, outputTokens: 2, totalTokens: 5, durationMs: 7 },
    terminal: { outcome: "completed", code: "completed", retryable: false, recoveryAction: null },
  });
  const store = createInMemoryAgentRunEventStore();
  store.restore({ runs: [{ runId: result.runId, events: result.events }] });
  return { store, runId: result.runId };
};

describe("agent-run redacted export and hermetic replay", () => {
  test("exports deterministic bytes with safe labels and replays the same projection", () => {
    const first = makeStore();
    const second = makeStore();
    const exported = exportAgentRunTrace(first.store, first.runId, { buildId: "platform-test-build" });
    const repeated = exportAgentRunTrace(second.store, second.runId, { buildId: "platform-test-build" });
    expect(exported.bytes).toBe(repeated.bytes);
    expect(exported.bytes.endsWith("\n")).toBe(true);
    expect(exported.bundle.runId).toBe("run:1");
    expect(exported.bundle.bundleDigest).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(exported.bundle.eventTrace.every((event) => event.runLabel === "run:1")).toBe(true);
    for (const raw of [first.runId, "internal-attempt-1", "internal-context", "internal-source", "internal-owner", "internal-call", "internal-idem", HASH]) {
      expect(exported.bytes).not.toContain(raw);
    }
    const replay = replayAgentRunTrace(JSON.parse(exported.bytes));
    expect(replay.projection).toEqual(exported.bundle.projection);
    expect(replay.projectionDigest).toBe(exported.bundle.projectionDigest);
    expect(replay.projection.events.at(-1)?.details).toEqual({
      terminalOutcome: "completed", terminalCode: "completed", retryable: false, recoveryAction: null,
    });
  });

  test("tampered trace, projection, and forbidden raw fields fail closed", () => {
    const { store, runId } = makeStore();
    const exported = exportAgentRunTrace(store, runId, { buildId: "platform-test-build" });
    expect(() => replayAgentRunTrace({ ...exported.bundle, traceDigest: "sha256:bad" })).toThrow();
    expect(() => replayAgentRunTrace({ ...exported.bundle, bundleDigest: `sha256:${"b".repeat(64)}` })).toThrow();
    expect(() => replayAgentRunTrace({ ...exported.bundle, projection: { ...exported.bundle.projection, runId: "internal-run-42" } })).toThrow();
    expect(() => replayAgentRunTrace({ ...exported.bundle, eventTrace: exported.bundle.eventTrace.map((event) => ({ ...event, payload: { ...event.payload, prompt: "secret" } })) })).toThrow();

    const detailMutations: readonly [keyof typeof exported.bundle, unknown][] = [
      ["contextReceipts", [...exported.bundle.contextReceipts, { ...exported.bundle.contextReceipts[0]! }]],
      ["toolEnvelopes", [...exported.bundle.toolEnvelopes, { ...exported.bundle.toolEnvelopes[0]! }]],
      ["timings", exported.bundle.timings.map((entry, index) => index === 0 ? { ...entry, createdAt: entry.createdAt + 1 } : entry)],
      ["durableState", exported.bundle.durableState.map((entry, index) => index === 0 ? { ...entry, stateKind: "status" } : entry)],
      ["buildId", "different-build"],
      ["schema", "omi.agent-run-trace-tampered"],
      ["runId", "run:2"],
    ];
    for (const [key, value] of detailMutations) {
      expect(() => replayAgentRunTrace({ ...exported.bundle, [key]: value })).toThrow();
    }
    const recomputedDetails = {
      ...exported.bundle,
      contextReceipts: [...exported.bundle.contextReceipts, { ...exported.bundle.contextReceipts[0]! }],
    };
    const { bundleDigest: _ignoredDigest, ...unsignedRecomputedDetails } = recomputedDetails;
    const recomputedDigest = `sha256:${createHash("sha256")
      .update(canonicalTraceJson(unsignedRecomputedDetails as Parameters<typeof canonicalTraceJson>[0]), "utf8")
      .digest("hex")}`;
    expect(() => replayAgentRunTrace({ ...recomputedDetails, bundleDigest: recomputedDigest }))
      .toThrow("contextReceipts");

    const attachment = {
      ...exported.bundle,
      projection: {
        ...exported.bundle.projection,
        events: exported.bundle.projection.events.map((event, index) => index === 0
          ? { ...event, safeSummary: "attachment_opaque123" }
          : event),
      },
    };
    expect(() => replayAgentRunTrace(attachment)).toThrow("attachment");

    // Every prose-bearing event payload is inside the same denylist walk;
    // exercise each shape rather than only the top-level projection summary.
    for (const payloadKey of ["redactedPreview", "inclusionReason", "resultSummary"] as const) {
      const eventIndex = exported.bundle.eventTrace.findIndex((event) => payloadKey in event.payload);
      expect(eventIndex).toBeGreaterThanOrEqual(0);
      const event = exported.bundle.eventTrace[eventIndex]!;
      const poisoned = {
        ...exported.bundle,
        eventTrace: exported.bundle.eventTrace.map((candidate, index) => index === eventIndex
          ? { ...candidate, payload: { ...candidate.payload, [payloadKey]: "attachment_opaque123" } }
          : candidate),
      };
      expect(() => replayAgentRunTrace(poisoned)).toThrow("attachment");
      expect(event.payload[payloadKey]).not.toBe("attachment_opaque123");
    }

    const unsafeSource = makeStore();
    const sourceSnapshot = unsafeSource.store.snapshot();
    unsafeSource.store.restore({
      runs: sourceSnapshot.runs.map((run) => ({
        ...run,
        events: run.events.map((event, index) => index === 0
          ? { ...event, safeSummary: "attachment_opaque123" }
          : event),
      })),
    });
    expect(() => exportAgentRunTrace(unsafeSource.store, unsafeSource.runId, { buildId: "platform-test-build" }))
      .toThrow("attachment");
  });

  test("raw IDs are checked as value tokens, not substrings of safe field names", () => {
    const { store, runId } = makeStore("cap");
    const exported = exportAgentRunTrace(store, runId, { buildId: "platform-test-build" });
    expect(exported.bytes).toContain("capability:1");
    expect(exported.bytes).not.toContain('"cap"');
    expect(replayAgentRunTrace(JSON.parse(exported.bytes)).projection.events.length).toBeGreaterThan(0);

    // Source identifiers may legitimately equal an adapter/tool value. They
    // are not leaked merely because the same value is present in a semantic
    // field; only source-visible prose is checked below.
    const semanticCollision = makeStore("scripted");
    expect(() => exportAgentRunTrace(semanticCollision.store, semanticCollision.runId, { buildId: "platform-test-build" })).not.toThrow();
  });

  test("generated labels do not collide with valid short or event-like source IDs", () => {
    const shortIds = makeStore("cap", "run:1", "attempt");
    const snapshot = shortIds.store.snapshot();
    shortIds.store.restore({
      runs: snapshot.runs.map((run) => ({
        ...run,
        events: run.events.map((event, index) => index === 0 ? { ...event, eventId: "event:1" } : event),
      })),
    });
    const labels = exportAgentRunTrace(shortIds.store, shortIds.runId, { buildId: "platform-test-build" });
    expect(labels.bundle.runId).toBe("run:1");
    expect(labels.bundle.eventTrace[0]?.attemptLabel).toBe("attempt:1");
    expect(labels.bundle.eventTrace[0]?.eventLabel).toBe("event:1");
    expect(replayAgentRunTrace(JSON.parse(labels.bytes)).projection.events.length).toBeGreaterThan(0);

    const productionIds = makeStore(
      "550e8400-e29b-41d4-a716-446655440000",
      "run-production-uuid",
      "1d7f4b24-5c7e-4c46-9f32-7eb87f4d7c2a",
    );
    const productionSnapshot = productionIds.store.snapshot();
    productionIds.store.restore({
      runs: productionSnapshot.runs.map((run) => ({
        ...run,
        events: run.events.map((event, index) => index === 0
          ? { ...event, eventId: "8f5e2c15-8a4c-4d79-9d0b-8d2e4f7b1a33" }
          : event),
      })),
    });
    const productionExport = exportAgentRunTrace(productionIds.store, productionIds.runId, { buildId: "platform-test-build" });
    for (const raw of [
      productionIds.runId,
      "550e8400-e29b-41d4-a716-446655440000",
      "1d7f4b24-5c7e-4c46-9f32-7eb87f4d7c2a",
      "8f5e2c15-8a4c-4d79-9d0b-8d2e4f7b1a33",
    ]) expect(productionExport.bytes).not.toContain(raw);
    expect(replayAgentRunTrace(JSON.parse(productionExport.bytes)).projection.events.length).toBeGreaterThan(0);

    for (const [runId, attemptId] of [["a", "attempt-safe"], ["run-safe", "id"]] as const) {
      const source = makeStore("cap", runId, attemptId);
      const sourceSnapshot = source.store.snapshot();
      source.store.restore({
        runs: sourceSnapshot.runs.map((run) => ({
          ...run,
          events: run.events.map((event, index) => index === 0
            ? { ...event, safeSummary: runId === "a" ? "a" : "id" }
            : event),
        })),
      });
      expect(() => exportAgentRunTrace(source.store, source.runId, { buildId: "platform-test-build" }))
        .toThrow("raw");
    }
  });

  test("CLI replays only the artifact and emits a bounded receipt", () => {
    const { store, runId } = makeStore();
    const exported = exportAgentRunTrace(store, runId, { buildId: "platform-test-build" });
    const directory = mkdtempSync(join(tmpdir(), "omi-agent-trace-"));
    const path = join(directory, "trace.json");
    writeFileSync(path, exported.bytes, "utf8");
    const result = spawnSync("bun", ["scripts/replay-agent-run.ts", path], { cwd: new URL("../../..", import.meta.url).pathname, encoding: "utf8" });
    expect(result.status).toBe(0);
    expect(JSON.parse(result.stdout)).toMatchObject({ ok: true, schema: "omi.agent-run-trace", runId: "run:1", eventCount: exported.bundle.eventTrace.length });
    expect(result.stdout).not.toContain("internal-run-42");
    expect(readFileSync(path, "utf8")).toBe(exported.bytes);
  });
});
