import { describe, expect, test } from "bun:test";

import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
} from "./agent-run-events";
import {
  runGatewayAgentScenario,
  type GatewayAgentScenario,
} from "./gateway-agent-scenario";

const sourceHash = `sha256:${"1".repeat(64)}`;

const source = (sourceId: string) => Object.freeze({
  sourceKind: "memory",
  sourceId,
  claimId: null,
  evidenceId: `evidence:${sourceId}`,
  ownerAccountId: "gateway-scenario-account",
  sourceHash,
  capturedAt: 1,
  expiresAt: null,
  redactedPreview: `Safe context for ${sourceId}.`,
  tokenEstimate: 4,
  inclusionReason: "scenario-authorized context",
});

const toolSchema = Object.freeze({
  name: "safe.fixture_status",
  description: "Read the current fixture status.",
  parameters: Object.freeze({
    type: "object" as const,
    additionalProperties: false as const,
    properties: Object.freeze({
      scope: Object.freeze({ type: "string" as const, enum: Object.freeze(["current"]) }),
    }),
    required: Object.freeze(["scope"]),
  }),
});

const initialState = () => {
  const store = createInMemoryAgentRunEventStore();
  let now = 0;
  const events = createAgentRunEventSupervisor({
    events: store,
    nowEpochMilliseconds: () => now++,
    eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
  });
  events.accepted({ runId: "prior-run", attemptId: "prior-attempt", admissionId: "prior-admission" });
  events.terminal({ runId: "prior-run", attemptId: "prior-attempt", terminalOutcome: "completed",
    terminalCode: "completed", retryable: false, recoveryAction: null });
  return store.snapshot();
};

const scenario = (): GatewayAgentScenario => ({
  initialDurableState: initialState(),
  userTurns: [{
    generationId: "turn-1",
    attemptId: "turn-1-attempt",
    prompt: "Check the fixture.",
    contextSources: [source("source-1")],
  }, {
    generationId: "turn-2",
    attemptId: "turn-2-attempt",
    prompt: "Continue from the first answer.",
    contextSources: [source("source-2")],
    approvals: [{
      approvalId: "approval-1",
      callId: "planned-call-1",
      reason: "Scenario approval state only; the safe tool does not require it.",
      expiresAt: 10_000,
      resolution: "approved",
    }],
  }],
  availableTools: [{
    schema: toolSchema,
    timeoutMs: 100,
    result: { summary: "Fixture is ready.", durationMs: 2, retryable: false },
  }],
  providerScript: [{
    kind: "tool_call",
    providerCallId: "provider-private-call",
    toolName: "safe.fixture_status",
    arguments: { scope: "current" },
  }, {
    kind: "answer",
    deltas: ["Use tool ", "result."],
    usage: { inputTokens: 8, outputTokens: 3 },
  }, {
    kind: "answer",
    deltas: ["Second answer."],
  }],
});

describe("declarative gateway agent scenario", () => {
  test("joins initial state, user turns, context, a gateway tool, approvals, durable rows, and rendered observations", async () => {
    const first = await runGatewayAgentScenario(scenario());
    expect(first.replayStable).toBe(true);
    expect(first.toolExecutions).toBe(1);
    expect(first.gatewayRequests.map(({ messageContentHashes: _hashes, ...request }) => request)).toEqual([{
      model: "omi:auto:chat-agent-scenario",
      toolChoice: "auto",
      messageRoles: ["system", "user"],
    }, {
      model: "omi:auto:chat-agent-scenario",
      toolChoice: "none",
      messageRoles: ["system", "user", "assistant", "tool"],
    }, {
      model: "omi:auto:chat-agent-scenario",
      toolChoice: "auto",
      messageRoles: ["system", "user", "assistant", "user"],
    }]);
    expect(first.gatewayRequests.map((request) => request.messageContentHashes.length)).toEqual([2, 4, 4]);
    expect(first.gatewayRequests.flatMap((request) => request.messageContentHashes)
      .every((hash) => /^sha256:[0-9a-f]{64}$/u.test(hash))).toBe(true);
    expect(first.gatewayRequests[0]?.messageContentHashes[0])
      .not.toBe(first.gatewayRequests[2]?.messageContentHashes[0]);
    expect(first.eventTrace).toEqual([
      "prior-run:1:run_accepted",
      "prior-run:2:terminal",
      "turn-1:1:run_accepted",
      "turn-1:2:capability_receipt",
      "turn-1:3:context_receipt",
      "turn-1:4:tool_request",
      "turn-1:5:tool_result",
      "turn-1:6:usage",
      "turn-1:7:terminal",
      "turn-2:1:run_accepted",
      "turn-2:2:capability_receipt",
      "turn-2:3:context_receipt",
      "turn-2:4:approval_requested",
      "turn-2:5:approval_resolved",
      "turn-2:6:terminal",
    ]);
    expect(first.durableRows).toEqual([{
      runId: "prior-run",
      eventCount: 2,
      kinds: ["run_accepted", "terminal"],
      terminalKind: "completed",
    }, {
      runId: "turn-1",
      eventCount: 7,
      kinds: ["run_accepted", "capability_receipt", "context_receipt", "tool_request", "tool_result", "usage", "terminal"],
      terminalKind: "completed",
    }, {
      runId: "turn-2",
      eventCount: 6,
      kinds: ["run_accepted", "capability_receipt", "context_receipt", "approval_requested", "approval_resolved", "terminal"],
      terminalKind: "completed",
    }]);
    expect(first.renderedObservations).toEqual([{
      generationId: "turn-1",
      text: "Use tool result.",
      terminal: "completed",
      errorCode: null,
    }, {
      generationId: "turn-2",
      text: "Second answer.",
      terminal: "completed",
      errorCode: null,
    }]);
    expect(JSON.stringify(first.durableState)).not.toContain("provider-private-call");
    expect(JSON.stringify(first.durableState)).not.toContain("scenario-only-token");
    expect(JSON.stringify(first.durableState)).not.toContain("\"scope\"");

    const checked = scenario();
    const second = await runGatewayAgentScenario({
      ...checked,
      expected: {
        eventTrace: first.eventTrace,
        durableRows: first.durableRows,
        renderedObservations: first.renderedObservations,
        gatewayRequests: first.gatewayRequests,
      },
    });
    expect(second).toEqual(first);
  });

  test("scheduled gateway faults terminate truthfully without a fake answer", async () => {
    const result = await runGatewayAgentScenario({
      userTurns: [{
        generationId: "fault-turn",
        attemptId: "fault-attempt",
        prompt: "This must fail.",
        contextSources: [source("fault-source")],
      }],
      availableTools: [],
      providerScript: [{ kind: "answer", deltas: ["must not render"] }],
      scheduledFaults: [{ exchange: 1, kind: "http_503" }],
    });
    expect(result.renderedObservations).toEqual([{
      generationId: "fault-turn",
      text: "",
      terminal: "failed",
      errorCode: "generation_provider_failed",
    }]);
    expect(result.durableRows[0]?.terminalKind).toBe("failed");
    expect(result.gatewayRequests).toHaveLength(1);
  });

  test("fails closed on mismatched executable expectations and invalid multi-tool expansion", async () => {
    const base = scenario();
    await expect(runGatewayAgentScenario({
      ...base,
      expected: {
        eventTrace: [],
        durableRows: [],
        renderedObservations: [],
        gatewayRequests: [],
      },
    })).rejects.toThrow("gateway agent scenario expectation mismatch");
    await expect(runGatewayAgentScenario({
      ...base,
      availableTools: [...base.availableTools, base.availableTools[0]!],
    })).rejects.toThrow("invalid gateway agent scenario");
    await expect(runGatewayAgentScenario({
      ...base,
      availableTools: [],
    })).rejects.toThrow("invalid gateway agent provider script");
    await expect(runGatewayAgentScenario({
      ...base,
      scheduledFaults: [{ exchange: 99, kind: "throw" }],
    })).rejects.toThrow("scheduled gateway fault was not reached");

    await expect(runGatewayAgentScenario({
      ...base,
      providerScript: new Proxy(base.providerScript, {}),
    })).rejects.toThrow("gateway agent scenario must be plain data");

    let reads = 0;
    const accessorTurn = Object.defineProperty({ ...base.userTurns[0] }, "prompt", {
      enumerable: true,
      get: () => (++reads === 1 ? "safe during validation" : "secret after validation"),
    });
    await expect(runGatewayAgentScenario({
      ...base,
      userTurns: [accessorTurn as GatewayAgentScenario["userTurns"][number], base.userTurns[1]!],
    })).rejects.toThrow("gateway agent scenario must be plain data");
    expect(reads).toBe(0);

    await expect(runGatewayAgentScenario({
      ...base,
      userTurns: [{ ...base.userTurns[0]!, extra: "unexpected" } as GatewayAgentScenario["userTurns"][number],
        base.userTurns[1]!],
    })).rejects.toThrow("invalid gateway agent scenario turn");
    await expect(runGatewayAgentScenario({
      ...base,
      providerScript: [{ ...base.providerScript[0]!, extra: "unexpected" } as GatewayAgentScenario["providerScript"][number],
        ...base.providerScript.slice(1)],
    })).rejects.toThrow("invalid gateway agent provider script");
  });
});
