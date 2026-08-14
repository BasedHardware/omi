import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createInMemoryLocalServiceStores, createLocalDevService } from "../app-facing";
import { createAgentApprovalCoordinator } from "./agent-approval-coordinator";
import {
  createAgentRunEventSupervisor,
  createInMemoryAgentRunEventStore,
  type AgentRunEventStore,
} from "./agent-run-events";
import { createAgentToolRegistry } from "./agent-tools";
import { createChatGenerationContextPacket } from "./generation-context";
import {
  createGatewayChatGenerationSource,
  type ChatGenerationSourceInput,
} from "./generation-source";
import {
  createSafeWriteTool,
  createSafeWriteToolLoop,
  SAFE_WRITE_TOOL_NAME,
  SAFE_WRITE_TOOL_SCHEMA,
} from "./safe-write-tool";

const context = createChatGenerationContextPacket({
  accountId: "approval-owner",
  generationId: "generation-approval-live",
  nowEpochMilliseconds: 1,
  candidates: [],
});

const generationInput = (
  overrides: Partial<ChatGenerationSourceInput> = {},
): ChatGenerationSourceInput => ({
  generationId: "generation-approval-live",
  attemptId: "generation-approval-live:attempt:1",
  prompt: "Record the scoped write.",
  context,
  attachments: [],
  onDelta() {},
  onComplete() {},
  onError() {},
  ...overrides,
});

const stream = (...events: readonly string[]): Response => new Response(
  new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(new TextEncoder().encode(`data: ${event}\n\n`));
      controller.close();
    },
  }),
  { status: 200, headers: { "content-type": "text/event-stream" } },
);

const toolCallStream = (
  providerCallId: string,
  name = SAFE_WRITE_TOOL_NAME,
  argumentsJson = "{}",
) => stream(
  JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: providerCallId,
    function: { name, arguments: argumentsJson } }] } }] }),
  "[DONE]",
);

const seedLedger = (): AgentRunEventStore => {
  const store = createInMemoryAgentRunEventStore();
  createAgentRunEventSupervisor({ events: store, nowEpochMilliseconds: () => 1 })
    .accepted({
      runId: "generation-approval-live",
      attemptId: "generation-approval-live:attempt:1",
      admissionId: "message-approval-live",
    });
  return store;
};

const waitFor = async (predicate: () => boolean, timeoutMs = 2_000): Promise<void> => {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("timed out waiting for condition");
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
};

const bootApprovalLoop = () => {
  let now = 10;
  let executions = 0;
  const store = seedLedger();
  const supervisor = createAgentRunEventSupervisor({
    events: store,
    nowEpochMilliseconds: () => now++,
    eventId: (runId, sequence, kind) => `${runId}:${sequence}:${kind}`,
  });
  const tool = createSafeWriteTool();
  const coordinator = createAgentApprovalCoordinator({
    registry: createAgentToolRegistry([{
      ...tool,
      execute: async () => {
        executions += 1;
        return { summary: "Scoped write recorded.", durationMs: 1, retryable: false };
      },
    }]),
    events: supervisor,
    nowEpochMilliseconds: () => now,
  });
  const loop = createSafeWriteToolLoop({
    agentRunEvents: store,
    approvalCoordinator: coordinator,
    nowEpochMilliseconds: () => now,
  });
  return { store, coordinator, loop, executions: () => executions, now: () => now };
};

describe("gateway approval live path", () => {
  test("safe.write pauses the gateway loop until coordinator resolve approves", async () => {
    const ctx = bootApprovalLoop();
    const responses = [
      toolCallStream("provider-write-call"),
      stream(JSON.stringify({ choices: [{ delta: { content: "Write accepted." } }] }), "[DONE]"),
    ];
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:8787",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: ctx.loop,
      fetch: async () => responses.shift()!,
    });
    let answer = "";
    let error: unknown = null;
    source.start(generationInput({
      onDelta: (delta) => { answer += delta; },
      onComplete: () => {},
      onError: (failure) => { error = failure; },
    }));
    await waitFor(() => ctx.store.list("generation-approval-live")
      .some((event) => event.kind === "approval_requested"));
    expect(ctx.executions()).toBe(0);
    const approval = ctx.store.list("generation-approval-live")
      .find((event) => event.kind === "approval_requested");
    expect(approval?.kind).toBe("approval_requested");
    const approvalId = approval?.kind === "approval_requested" ? approval.approvalId : "";
    const resolved = await ctx.coordinator.resolve({
      runId: "generation-approval-live",
      approvalId,
      resolution: "approved",
    });
    expect(resolved).toMatchObject({ kind: "completed", summary: "Scoped write recorded." });
    await waitFor(() => answer.length > 0 || error !== null);
    expect(error).toBeNull();
    expect(answer).toBe("Write accepted.");
    expect(ctx.executions()).toBe(1);
    expect(ctx.store.list("generation-approval-live").some((event) => event.kind === "tool_result")).toBe(true);
  });

  test("deny resolves without executing safe.write and the gateway turn still completes", async () => {
    const ctx = bootApprovalLoop();
    const responses = [
      toolCallStream("provider-write-deny"),
      stream(JSON.stringify({ choices: [{ delta: { content: "Denied safely." } }] }), "[DONE]"),
    ];
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:8787",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: ctx.loop,
      fetch: async () => responses.shift()!,
    });
    let answer = "";
    source.start(generationInput({
      onDelta: (delta) => { answer += delta; },
      onComplete: () => {},
      onError: () => {},
    }));
    await waitFor(() => ctx.store.list("generation-approval-live")
      .some((event) => event.kind === "approval_requested"));
    const approval = ctx.store.list("generation-approval-live")
      .find((event) => event.kind === "approval_requested");
    const approvalId = approval?.kind === "approval_requested" ? approval.approvalId : "";
    await ctx.coordinator.resolve({
      runId: "generation-approval-live",
      approvalId,
      resolution: "denied",
    });
    await waitFor(() => answer.length > 0);
    expect(ctx.executions()).toBe(0);
    expect(answer).toBe("Denied safely.");
    expect(ctx.store.list("generation-approval-live").some((event) => event.kind === "tool_result")).toBe(false);
  });

  test("HTTP resolve unblocks an in-flight gateway generation using the shared coordinator", async () => {
    const db = new Database(":memory:");
    const stores = createInMemoryLocalServiceStores();
    let service!: ReturnType<typeof createLocalDevService>;
    const gatewayResponses = [
      toolCallStream("provider-http-write"),
      stream(JSON.stringify({ choices: [{ delta: { content: "HTTP approved." } }] }), "[DONE]"),
    ];
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:8787",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoopForInput: () => createSafeWriteToolLoop({
        agentRunEvents: service.writePath.agentRunEvents,
        approvalCoordinator: service.writePath.agentApprovalCoordinator,
        nowEpochMilliseconds: () => Date.now(),
      }),
      fetch: async () => gatewayResponses.shift()!,
    });
    service = createLocalDevService({
      db,
      stores,
      ownerAccountId: "approval-owner",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "gateway-approval-http-proof",
      generationSource: source,
    });
    const admitted = await service.app.request("/v1/chat-messages", {
      method: "POST",
      headers: {
        authorization: `Bearer ${service.devToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        op: "create",
        opId: "op-http-approval",
        id: "message-http-approval",
        at: 1,
        text: "approve this write",
        sender: "human",
        journalRevision: 1,
        type: "text",
        appId: null,
        chatSessionId: null,
        messageSource: "desktop_chat",
        metadata: null,
        attachmentIds: [],
      }),
    });
    expect(admitted.status).toBe(201);
    const generationId = ((await admitted.json()) as { generation: { id: string } }).generation.id;
    const agentEvents = service.writePath.agentRunEvents;
    await waitFor(() => agentEvents.list(generationId)
      .some((event) => event.kind === "approval_requested"));
    const approval = agentEvents.list(generationId)
      .find((event) => event.kind === "approval_requested");
    const approvalId = approval?.kind === "approval_requested" ? approval.approvalId : "";
    const resolveResponse = await service.app.request(
      `/v1/chat-generations/${generationId}/agent-approvals`,
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${service.devToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ approvalId, resolution: "approved" }),
      },
    );
    expect(resolveResponse.status).toBe(200);
    expect((await resolveResponse.json()).outcome).toMatchObject({
      kind: "completed",
      summary: "Scoped write recorded.",
    });
    await waitFor(() => agentEvents.list(generationId).some((event) => event.kind === "tool_result"), 5_000);
    db.close();
  });
});
