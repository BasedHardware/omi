import { describe, expect, test } from "bun:test";

import {
  CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION,
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
  parseAgentRunEvent,
  projectAgentRunTimeline,
  scanAgentRunRedactions,
} from "./agent-run-events";
import { runAgentRunScenario } from "./agent-run-scenario";

const HASH = `sha256:${"a".repeat(64)}`;

const scenario = {
  runId: "run-alpha",
  attemptId: "attempt-1",
  capability: {
    capabilityId: "cap-1",
    tier: "deterministic-scripted" as const,
    adapter: "scripted-chat-generation",
    deterministic: true,
  },
  context: {
    contextReceiptId: "ctx-1",
    sourceKind: "memory",
    sourceRef: "memory-ref-1",
    sourceHash: HASH,
    ownerRef: "owner-ref-1",
    expiresAt: 100,
    redactedPreview: "Relevant memory summary",
    tokenEstimate: 12,
    inclusionReason: "Matches the current turn",
    policyDecision: "included" as const,
  },
  statuses: [
    { status: "queued" as const, progressPct: 0 },
    { status: "gathering_context" as const, progressPct: 25 },
    { status: "using_tool" as const, progressPct: 50 },
    { status: "generating" as const, progressPct: 80 },
  ],
  tools: [{
    callId: "call-1",
    toolName: "safe.lookup",
    timeoutMs: 10_000,
    idempotencyKey: "idem-1",
    result: { summary: "Lookup completed", durationMs: 8, retryable: false },
  }],
  approval: {
    approvalId: "approval-1",
    callId: "call-1",
    reason: "A scoped approval is required",
    expiresAt: 100,
    resolution: "approved" as const,
  },
  usage: { usageId: "usage-1", inputTokens: 10, outputTokens: 5, totalTokens: 15, durationMs: 12 },
  recovery: {
    recoveryId: "recovery-1",
    action: "reconnect" as const,
    reason: "Connection resumed",
    fromAttemptId: "attempt-1",
    toAttemptId: "attempt-2",
  },
  terminal: { outcome: "completed" as const, code: "completed" as const, retryable: false, recoveryAction: null },
};

describe("versioned agent run events", () => {
  test("scenario appends every lifecycle event and reloads byte/order deterministically", () => {
    const first = runAgentRunScenario(scenario);
    const second = runAgentRunScenario(scenario);
    expect(first.events.map((event) => event.kind)).toEqual([
      "run_accepted", "capability_receipt", "context_receipt", "status", "status", "status", "status",
      "tool_request", "tool_result", "approval_requested", "approval_resolved", "usage", "recovery", "terminal",
    ]);
    expect(first.events.map((event) => event.sequence)).toEqual(first.events.map((_, index) => index + 1));
    expect(JSON.stringify(first.events)).toBe(JSON.stringify(second.events));
    expect(JSON.stringify(first.replayEvents)).toBe(JSON.stringify(first.events));
    expect(first.timeline).not.toBeNull();
    expect(first.timeline?.events.at(-1)?.details).toEqual({
      terminalOutcome: "completed", terminalCode: "completed", retryable: false, recoveryAction: null,
    });
    expect(scanAgentRunRedactions(first.timeline)).toEqual([]);
  });

  test("declarative durable initial state resumes with tools and approval then reloads exactly", () => {
    let now = 40;
    const seeded = createInMemoryAgentRunEventStore();
    const seedSupervisor = createAgentRunEventSupervisor({
      events: seeded,
      nowEpochMilliseconds: () => now++,
      eventId: (runId, sequence, kind) => `${runId}:${sequence}:${kind}`,
    });
    seedSupervisor.accepted({ runId: "run-resumed", attemptId: "attempt-1", admissionId: "admission-resumed" });
    seedSupervisor.context({
      runId: "run-resumed",
      attemptId: "attempt-1",
      contextReceiptId: "context-resumed",
      sourceKind: "memory",
      sourceRef: "memory-safe-ref",
      sourceHash: HASH,
      ownerRef: "owner-safe-ref",
      expiresAt: 100,
      redactedPreview: "Safe resumed context",
      tokenEstimate: 4,
      inclusionReason: "Continuation context",
      policyDecision: "included",
    });

    const resumed = runAgentRunScenario({
      initialSnapshot: seeded.snapshot(),
      runId: "run-resumed",
      attemptId: "attempt-2",
      statuses: [{ status: "using_tool", progressPct: 50 }],
      tools: [{
        callId: "call-resumed",
        toolName: "safe.lookup",
        timeoutMs: 1_000,
        idempotencyKey: "idem-resumed",
        result: { summary: "Lookup resumed", durationMs: 3, retryable: false },
      }],
      approval: {
        approvalId: "approval-resumed",
        callId: "call-resumed",
        reason: "Approval remained scoped",
        expiresAt: 200,
        resolution: "approved",
      },
      terminal: { outcome: "completed", code: "completed", retryable: false, recoveryAction: null },
    });

    expect(resumed.events.map((event) => event.kind)).toEqual([
      "run_accepted", "context_receipt", "status", "tool_request", "tool_result",
      "approval_requested", "approval_resolved", "terminal",
    ]);
    expect(resumed.events.map((event) => event.sequence)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(resumed.events[2]?.createdAt).toBeGreaterThan(resumed.events[1]!.createdAt);
    expect(resumed.replayEvents).toEqual(resumed.events);
    expect(resumed.timeline?.events.at(-1)?.kind).toBe("terminal");
    expect(scanAgentRunRedactions(resumed.timeline)).toEqual([]);
    expect(() => runAgentRunScenario({
      initialSnapshot: seeded.snapshot(),
      terminal: scenario.terminal,
    }, createInMemoryAgentRunEventStore())).toThrow("two durable state authorities");
  });

  test("current-minus-one is accepted while unknown versions fail closed", () => {
    const first = runAgentRunScenario({ terminal: scenario.terminal });
    const event = first.events[0]!;
    expect(event.schemaVersion).toBe(CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION);
    const previous = first.events.map((item) => parseAgentRunEvent({ ...item, schemaVersion: 0 }));
    expect(previous.every((item) => item.ok)).toBe(true);
    expect(previous.every((item) => item.ok && item.event.schemaVersion === CURRENT_AGENT_RUN_EVENT_SCHEMA_VERSION)).toBe(true);
    expect(parseAgentRunEvent({ ...event, schemaVersion: 99 }).ok).toBe(false);
  });

  test("missing, extra, wrong-visibility, and wrong-terminal fields are rejected", () => {
    const first = runAgentRunScenario({ terminal: scenario.terminal });
    const accepted = first.events[0]!;
    expect(parseAgentRunEvent(({ ...accepted, eventId: undefined } as unknown))).toEqual({
      ok: false, reason: "invalid_payload",
    });
    expect(parseAgentRunEvent({ ...accepted, prompt: "raw prompt" })).toEqual({
      ok: false, reason: "extra_or_missing_field",
    });
    expect(parseAgentRunEvent({ ...accepted, visibility: "secret" })).toEqual({
      ok: false, reason: "invalid_payload",
    });
    const terminal = first.events.at(-1)!;
    expect(parseAgentRunEvent({ ...terminal, terminalOutcome: "completed", terminalCode: "tool_failed" })).toEqual({
      ok: false, reason: "invalid_payload",
    });
    let getterCalls = 0;
    const accessor = Object.defineProperty({ ...accepted }, "safeSummary", {
      get: (): string => { getterCalls += 1; return "forged"; },
      enumerable: true,
    });
    expect(parseAgentRunEvent(accessor)).toEqual({ ok: false, reason: "accessor_or_proxy" });
    expect(getterCalls).toBe(0);
  });

  test("append-only store rejects malformed/unknown events without creating a stranded run", () => {
    const store = createInMemoryAgentRunEventStore();
    const first = runAgentRunScenario({ terminal: scenario.terminal });
    const accepted = first.events[0]!;
    expect(store.append({ ...accepted, eventId: "bad", unknown: true })).toEqual({
      kind: "rejected", reason: "extra_or_missing_field",
    });
    expect(store.list(accepted.runId)).toEqual([]);
    expect(store.append(accepted).kind).toBe("appended");
    expect(store.append(accepted).kind).toBe("replay");
    expect(store.append({ ...first.events[1]!, sequence: 3 }).kind).toBe("rejected");
    const resultWithoutRequest = first.events.find((event) => event.kind === "tool_result")!;
    expect(store.append({ ...resultWithoutRequest, sequence: 2, eventId: "run-alpha:2:tool_result" }).kind)
      .toBe("rejected");
  });

  test("restore rejects duplicate event IDs instead of silently overwriting replay identity", () => {
    const first = runAgentRunScenario({ terminal: scenario.terminal });
    const store = createInMemoryAgentRunEventStore();
    const accepted = first.events[0]!;
    const duplicate = { ...first.events[1]!, eventId: accepted.eventId, sequence: 3 };
    expect(() => store.restore({
      runs: [{ runId: accepted.runId, events: [accepted, first.events[1]!, duplicate] }],
    })).toThrow("invalid agent run snapshot event");
    expect(store.list(accepted.runId)).toEqual([]);
  });

  test("append and restore reject duplicate tool and approval terminal transitions", () => {
    const first = runAgentRunScenario(scenario);
    const accepted = first.events.find((event) => event.kind === "run_accepted")!;
    const request = first.events.find((event) => event.kind === "tool_request")!;
    const result = first.events.find((event) => event.kind === "tool_result")!;
    const store = createInMemoryAgentRunEventStore();
    expect(store.append({ ...accepted, eventId: "run-alpha:1:accepted", sequence: 1 }).kind).toBe("appended");
    expect(store.append({ ...request, eventId: "run-alpha:2:request", sequence: 2 }).kind).toBe("appended");
    expect(store.append({ ...result, eventId: "run-alpha:3:result", sequence: 3 }).kind).toBe("appended");
    expect(store.append({ ...result, eventId: "run-alpha:4:duplicate-result", sequence: 4 }).kind)
      .toBe("rejected");

    const approvalRequested = first.events.find((event) => event.kind === "approval_requested")!;
    const approvalResolved = first.events.find((event) => event.kind === "approval_resolved")!;
    expect(store.append({ ...approvalRequested, eventId: "run-alpha:4:approval-request", sequence: 4 }).kind)
      .toBe("appended");
    expect(store.append({ ...approvalResolved, eventId: "run-alpha:5:approval-resolution", sequence: 5 }).kind)
      .toBe("appended");
    expect(store.append({ ...approvalResolved, eventId: "run-alpha:6:duplicate-resolution", sequence: 6 }).kind)
      .toBe("rejected");

    const snapshot = store.snapshot();
    const duplicateSnapshot = {
      runs: [{
        runId: accepted.runId,
        events: [...snapshot.runs[0]!.events,
          { ...approvalResolved, eventId: "run-alpha:6:duplicate-resolution", sequence: 6 }],
      }],
    };
    expect(() => store.restore(duplicateSnapshot)).toThrow("invalid agent run snapshot approval ordering");

    const errorStore = createInMemoryAgentRunEventStore();
    const errorRequest = { ...request, eventId: "run-error:2:request", runId: "run-error", sequence: 2 };
    const errorAccepted = { ...accepted, eventId: "run-error:1:accepted", runId: "run-error", sequence: 1 };
    const toolError = first.events.find((event) => event.kind === "tool_result")!;
    const errorEvent = {
      schemaVersion: toolError.schemaVersion,
      runId: "run-error",
      attemptId: toolError.attemptId,
      eventId: "run-error:3:error",
      sequence: 3,
      visibility: toolError.visibility,
      createdAt: toolError.createdAt,
      safeSummary: "tool error",
      kind: "tool_error" as const,
      callId: toolError.callId,
      toolName: toolError.toolName,
      errorCode: "tool_failed",
      errorSummary: "safe failure",
      retryable: false,
    };
    expect(errorStore.append(errorAccepted).kind).toBe("appended");
    expect(errorStore.append(errorRequest).kind).toBe("appended");
    expect(errorStore.append(errorEvent).kind).toBe("appended");
    expect(errorStore.append({ ...errorEvent, eventId: "run-error:4:duplicate-error", sequence: 4 }).kind)
      .toBe("rejected");

    const mismatchStore = createInMemoryAgentRunEventStore();
    expect(mismatchStore.append({ ...accepted, eventId: "run-mismatch:1:accepted",
      runId: "run-mismatch", sequence: 1 }).kind).toBe("appended");
    expect(mismatchStore.append({ ...request, eventId: "run-mismatch:2:request",
      runId: "run-mismatch", sequence: 2 }).kind).toBe("appended");
    const mismatchedResult = { ...result, eventId: "run-mismatch:3:result",
      runId: "run-mismatch", sequence: 3, toolName: "safe.different" };
    expect(mismatchStore.append(mismatchedResult).kind).toBe("rejected");
    expect(() => mismatchStore.restore({
      runs: [{ runId: "run-mismatch", events: [
        { ...accepted, eventId: "run-mismatch:1:accepted", runId: "run-mismatch", sequence: 1 },
        { ...request, eventId: "run-mismatch:2:request", runId: "run-mismatch", sequence: 2 },
        mismatchedResult,
      ] }],
    })).toThrow("invalid agent run snapshot tool ordering");
  });

  test("UI projection drops internal events and redaction scanner catches forbidden fields", () => {
    const first = runAgentRunScenario({ terminal: scenario.terminal });
    const internal = { ...first.events[1]!, visibility: "internal" as const };
    const projected = projectAgentRunTimeline([first.events[0]!, internal, ...first.events.slice(2)]);
    expect(projected?.events.some((event) => event.kind === "capability_receipt")).toBe(false);
    expect(scanAgentRunRedactions({ prompt: "do not retain", nested: { credentials: "token" } })).toEqual([
      "prompt", "nested.credentials",
    ]);
    for (const field of ["safeSummary", "resultSummary", "errorSummary", "reason",
      "redactedPreview", "inclusionReason"]) {
      expect(scanAgentRunRedactions({ [field]: "attachmentId=opaque-123 api_key=secret-value" }).length)
        .toBeGreaterThan(0);
    }
    expect(scanAgentRunRedactions({
      nested: {
        api_key: "secret-value",
        access_token: "opaque-token",
        attachment_id: "opaque-attachment",
        file_id: "opaque-file",
        safeSummary: "authorization: Basic abc token=opaque",
      },
    })).toEqual([
      "nested.api_key",
      "nested.access_token",
      "nested.attachment_id",
      "nested.file_id",
      "nested.safeSummary",
    ]);
    expect(scanAgentRunRedactions({
      safeSummary: "api.key=secret attachment.id=opaque-a opaque.id=opaque-b reference.id=opaque-c",
      opaque_id: "opaque-d",
      reference_id: "opaque-e",
      opaqueReference: "opaque-f",
    })).toEqual([
      "safeSummary",
      "opaque_id",
      "reference_id",
      "opaqueReference",
    ]);
    expect(scanAgentRunRedactions({
      nested: {
        opaque: "opaque-a",
        opaque_ref: "opaque-b",
        "opaque-ref": "opaque-c",
        file_ref: "opaque-d",
        "file-ref": "opaque-e",
        attachment_ref: "opaque-f",
        "attachment-ref": "opaque-g",
        safeSummary: "opaque=opaque-h file_ref=opaque-i attachment-ref:opaque-j",
      },
    })).toEqual([
      "nested.opaque",
      "nested.opaque_ref",
      "nested.opaque-ref",
      "nested.file_ref",
      "nested.file-ref",
      "nested.attachment_ref",
      "nested.attachment-ref",
      "nested.safeSummary",
    ]);
    expect(scanAgentRunRedactions({
      nested: {
        attachment_ids: ["opaque-a"],
        fileIds: ["opaque-b"],
        opaque_ids: ["opaque-c"],
        opaque_refs: ["opaque-d"],
        opaqueReferences: ["opaque-e"],
        reference_ids: ["opaque-f"],
        referenceRefs: ["opaque-g"],
        attachmentRefs: ["opaque-h"],
        file_refs: ["opaque-i"],
        safeSummary: "attachment_ids=opaque-j file-ids:opaque-k opaque_refs=opaque-l opaque-references=opaque-m reference_ids=opaque-n reference-refs=opaque-o attachment-refs=opaque-p file_refs=opaque-q",
      },
    })).toEqual([
      "nested.attachment_ids",
      "nested.fileIds",
      "nested.opaque_ids",
      "nested.opaque_refs",
      "nested.opaqueReferences",
      "nested.reference_ids",
      "nested.referenceRefs",
      "nested.attachmentRefs",
      "nested.file_refs",
      "nested.safeSummary",
    ]);
    expect(projectAgentRunTimeline(first.events.slice(1))).toBeNull();
    expect(projectAgentRunTimeline([
      first.events[0]!,
      { ...first.events[1]!, eventId: first.events[0]!.eventId, sequence: 2 },
    ])).toBeNull();
  });
});
