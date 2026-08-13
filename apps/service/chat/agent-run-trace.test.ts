import { describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

import { createInMemoryAgentRunEventStore } from "./agent-run-events";
import { runAgentRunScenario } from "./agent-run-scenario";
import { exportAgentRunTrace, replayAgentRunTrace } from "./agent-run-trace";

const HASH = `sha256:${"a".repeat(64)}`;

const makeStore = (capabilityId = "internal-capability") => {
  const result = runAgentRunScenario({
    runId: "internal-run-42",
    attemptId: "internal-attempt-1",
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
