import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { assertConversationContextPlan } from "../src/runtime/context-snapshot.js";
import { validateRuntimeContractFixture, validateRuntimeContractSchema } from "../src/runtime/contract-schema.js";
import { assertToolResultEnvelope } from "../src/runtime/tool-result-envelope.js";
import { normalizeRuntimeFailure, RUNTIME_FAILURE_CODES } from "../src/runtime/failures.js";

const fixtureDirectory = join(process.cwd(), "contracts", "v1");

function fixture(name: string): Record<string, any> {
  return JSON.parse(readFileSync(join(fixtureDirectory, name), "utf8")) as Record<string, any>;
}

describe("agent runtime v1 shared contract fixtures", () => {
  it("defines every cross-language contract and keeps the 620 KiB regression budget bounded", () => {
    const contract = fixture("agent-runtime-contract.fixture.json");
    const schema = fixture("agent-runtime-contract.schema.json");

    expect(contract.version).toBe(1);
    expect(validateRuntimeContractFixture(contract, schema)).toEqual([]);
    expect(contract.contextSnapshot.contextPlan).toMatchObject({
      olderHistoryStrategy: "truncated", retainedTurnCount: 64, totalTurnCount: 65, omittedTurnCount: 1,
    });
    expect(contract.toolResultEnvelope).toMatchObject({
      version: 1, truncated: true, originalBytes: 634880, projectedBytes: 8192,
    });
    expect(contract.sessionListingBudget.maxBytes).toBe(8192);
    expect(contract.sessionListingBudget.mustExclude).toEqual(expect.arrayContaining(["input", "surfaceContext"]));
    expect(contract.failureTaxonomy).toEqual(expect.arrayContaining(["bridge_start_failed", "provider_setup_needed"]));
    expect(contract.toolInvocation).toMatchObject({
      invocationId: contract.toolResultEnvelope.provenance.invocationId,
      runId: contract.toolResultEnvelope.provenance.runId,
      attemptId: contract.toolResultEnvelope.provenance.attemptId,
      toolName: contract.toolResultEnvelope.provenance.toolName,
      status: "succeeded",
    });
    expect(contract.adapterConformance).toEqual(expect.arrayContaining([
      expect.objectContaining({ adapterId: "pi-mono", transport: "node_runtime" }),
      expect.objectContaining({ adapterId: "acp", transport: "node_runtime" }),
      expect.objectContaining({ adapterId: "hermes", transport: "node_runtime" }),
      expect.objectContaining({ adapterId: "openclaw", transport: "node_runtime" }),
      expect.objectContaining({ adapterId: "gemini-realtime", transport: "swift_realtime" }),
      expect.objectContaining({ adapterId: "openai-realtime", transport: "swift_realtime" }),
    ]));
    assertConversationContextPlan(contract.contextSnapshot.contextPlan);
    assertToolResultEnvelope(contract.toolResultEnvelope);
  });

  it("rejects malformed immutable fixture cases across every shared boundary", () => {
    const malformed = fixture("malformed-context-plan.fixture.json");
    expect(() => assertConversationContextPlan(malformed.contextSnapshot.contextPlan))
      .toThrow(malformed.expectedError);
    const schema = fixture("agent-runtime-contract.schema.json");
    const contract = fixture("agent-runtime-contract.fixture.json");
    contract.adapterConformance[0].expectsToolEnvelope = false;
    expect(validateRuntimeContractSchema(contract, schema))
      .toContain("$.adapterConformance[0].expectsToolEnvelope: const mismatch");

    for (const [name, key] of [
      ["malformed-tool-result-envelope.fixture.json", "toolResultEnvelope"],
      ["malformed-permission-decision.fixture.json", "permissionDecision"],
      ["malformed-tool-invocation.fixture.json", "toolInvocation"],
      ["malformed-lifecycle.fixture.json", "lifecycle"],
      ["malformed-failure-taxonomy.fixture.json", "failureTaxonomy"],
    ] as const) {
      const malformedBoundary = fixture(name);
      const candidate = fixture("agent-runtime-contract.fixture.json");
      candidate[key] = malformedBoundary[key];
      expect(validateRuntimeContractFixture(candidate, schema)).toContain(malformedBoundary.expectedError);
    }
  });

  it("normalizes adapter and runtime detail codes into the shared bounded taxonomy", () => {
    const contract = fixture("agent-runtime-contract.fixture.json");
    for (const detailCode of [
      "adapter_process_exited",
      "adapter_process_error",
      "adapter_terminal_http_failure",
      "adapter_not_registered",
      "stale_binding",
      "provider_setup_needed",
      "policy_denied",
      "tool_result_exceeded_provider_budget",
      "owner_changed",
      "run_cancelled",
    ]) {
      const normalized = normalizeRuntimeFailure({ code: detailCode, userMessage: "fixture" });
      expect(RUNTIME_FAILURE_CODES).toContain(normalized.failureCode);
      expect(contract.failureTaxonomy).toContain(normalized.failureCode);
    }
  });
});
