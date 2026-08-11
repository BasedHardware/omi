import assert from "node:assert/strict";
import { test } from "node:test";
import type {
  BridgePayloadStream,
  BridgeStreamOpenRequest,
  BridgeStreamPort,
} from "@omi-core/contracts";
import {
  IncrementalAgentRunParser,
  observeAgentRun,
  type AgentRunObservationEvent,
} from "@omi-core/adapters-platform";
import { ManualEnv } from "../fakes.js";

function visible(
  eventId: string,
  sequence: number,
  kind: string,
  safeSummary: string,
  details: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  return {
    runId: "generation-one",
    attemptId: "attempt-one",
    eventId,
    sequence,
    createdAt: 1_786_442_400_000 + sequence,
    kind,
    safeSummary,
    details,
  };
}

function sse(value: Record<string, unknown>): string {
  return `event: ${String(value["kind"])}\nid: ${String(value["eventId"])}\ndata: ${JSON.stringify(value)}\n\n`;
}

test("agent-run parser survives byte boundaries and strips opaque transport identities", () => {
  const input = sse(visible("opaque-event", 2, "context_receipt", "Context selected", {
    contextReceiptId: "opaque-context",
    sourceKind: "memory",
    redactedPreview: "Saved preference",
    tokenEstimate: 12,
    inclusionReason: "Relevant to this question",
    policyDecision: "included",
  }));
  const parser = new IncrementalAgentRunParser();
  const parsed = [];
  for (const byte of new TextEncoder().encode(input)) parsed.push(...parser.push(Uint8Array.of(byte)));
  parsed.push(...parser.finish());

  assert.equal(parsed.length, 1);
  assert.equal(parsed[0]?.id, "opaque-event", "cursor stays inside the observer envelope");
  assert.deepEqual(parsed[0]?.event, {
    sequence: 2,
    createdAt: 1_786_442_400_002,
    kind: "context_receipt",
    safeSummary: "Context selected",
    details: {
      sourceKind: "memory",
      redactedPreview: "Saved preference",
      tokenEstimate: 12,
      inclusionReason: "Relevant to this question",
      policyDecision: "included",
    },
  });
  assert.doesNotMatch(JSON.stringify(parsed[0]?.event), /opaque-event|opaque-context|attempt-one|generation-one/);
});

test("agent-run parser fails closed on secrets, private markers, and extra raw fields", () => {
  for (const raw of [
    visible("event-secret", 1, "status", "authorization: Bearer private", {
      status: "generating", progressPct: 20,
    }),
    { ...visible("event-args", 1, "status", "Generating", {
      status: "generating", progressPct: 20,
    }), rawArguments: { hidden: true } },
    ...["callId: opaque123", "approvalId=opaque", "eventId: hidden", "runId: hidden", "rawArguments: abc", "opaque", "reference"].map(
      (safeSummary) => visible("event-marker", 1, "run_accepted", safeSummary, { admissionId: "admission-one" }),
    ),
    visible("event-context-marker", 1, "context_receipt", "Context selected", {
      contextReceiptId: "context-one",
      sourceKind: "memory",
      redactedPreview: "rawArguments: foo",
      tokenEstimate: 12,
      inclusionReason: "callId: opaque",
      policyDecision: "included",
    }),
    visible("event-tool-marker", 1, "tool_request", "Tool requested", {
      callId: "call-one",
      toolName: "eventId:foo",
      timeoutMs: 1_000,
    }),
  ]) {
    const parser = new IncrementalAgentRunParser();
    assert.throws(() => parser.push(sse(raw)), /invalid agent-run SSE event/);
  }
});

class ScriptedStream implements BridgePayloadStream {
  cancelled = false;
  constructor(
    readonly id: string,
    readonly channel: string,
    private readonly chunks: readonly string[],
  ) {}
  async *[Symbol.asyncIterator](): AsyncIterator<string> {
    for (const chunk of this.chunks) {
      if (this.cancelled) return;
      yield chunk;
    }
  }
  cancel(): void { this.cancelled = true; }
}

class ScriptedPort implements BridgeStreamPort {
  readonly opens: BridgeStreamOpenRequest[] = [];
  readonly streams: ScriptedStream[] = [];
  constructor(private readonly scripts: readonly (readonly string[])[]) {}
  open(request: BridgeStreamOpenRequest): BridgePayloadStream {
    const chunks = this.scripts[this.opens.length];
    if (chunks === undefined) throw new Error("unexpected stream open");
    this.opens.push(request);
    const stream = new ScriptedStream(`stream-${this.opens.length}`, request.channel, chunks);
    this.streams.push(stream);
    return stream;
  }
}

test("agent-run observer reconnects by exact cursor and stops at one terminal", async () => {
  const accepted = visible("event-accepted", 1, "run_accepted", "Run accepted", {
    admissionId: "admission-one",
  });
  const status = visible("event-status", 2, "status", "Generating", {
    status: "generating", progressPct: 40,
  });
  const terminal = visible("event-terminal", 3, "terminal", "Run complete", {
    terminalOutcome: "completed", terminalCode: "completed", retryable: false, recoveryAction: null,
  });
  const port = new ScriptedPort([
    [sse(accepted) + sse(status)],
    [sse(status) + sse(terminal)],
  ]);
  const env = new ManualEnv();
  const observation = observeAgentRun(port, "generation-one", env);
  const observed: AgentRunObservationEvent[] = [];
  const consume = (async () => {
    for await (const item of observation.events) observed.push(item);
  })();
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
  await env.advance(250);
  await consume;

  assert.deepEqual(port.opens, [
    { channel: "chat-agent-run-events", params: '{"generationId":"generation-one"}', initialCredit: 4 },
    { channel: "chat-agent-run-events", params: '{"generationId":"generation-one","lastEventId":"event-status"}', initialCredit: 4 },
  ]);
  assert.deepEqual(observed.map((item) => item.kind === "event" ? item.event.kind : item.kind), [
    "run_accepted", "status", "terminal",
  ]);
  assert.equal(port.streams[1]?.cancelled, true);
});

test("agent-run observer rejects duplicate and late reconnect cursor echoes", async () => {
  const accepted = visible("event-accepted", 1, "run_accepted", "Run accepted", {
    admissionId: "admission-one",
  });
  const status = visible("event-status", 2, "status", "Generating", {
    status: "generating", progressPct: 40,
  });
  const duplicatePort = new ScriptedPort([
    [sse(accepted) + sse(accepted) + sse(status)],
  ]);
  const duplicate = observeAgentRun(duplicatePort, "generation-one", new ManualEnv(), "event-accepted");
  const duplicateObserved: AgentRunObservationEvent[] = [];
  for await (const item of duplicate.events) duplicateObserved.push(item);
  assert.deepEqual(duplicateObserved.map((item) => item.kind), ["error"]);
  assert.match(
    duplicateObserved[0]?.kind === "error" ? duplicateObserved[0].failure : "",
    /cursor was reused/,
  );

  const latePort = new ScriptedPort([
    [sse(status) + sse(accepted)],
  ]);
  const late = observeAgentRun(latePort, "generation-one", new ManualEnv(), "event-accepted");
  const lateObserved: AgentRunObservationEvent[] = [];
  for await (const item of late.events) lateObserved.push(item);
  assert.deepEqual(
    lateObserved.map((item) => item.kind === "event" ? item.event.kind : item.kind),
    ["status", "error"],
  );
  assert.match(
    lateObserved[1]?.kind === "error" ? lateObserved[1].failure : "",
    /cursor was reused/,
  );
});
