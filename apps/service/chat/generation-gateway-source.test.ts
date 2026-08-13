import { describe, expect, test } from "bun:test";

import { createChatGenerationContextPacket } from "./generation-context";
import { createAgentRunEventSupervisor, createInMemoryAgentRunEventStore,
  type AgentRunEventStore } from "./agent-run-events";
import { createAgentToolRegistry, type AgentToolDefinition } from "./agent-tools";
import {
  createGatewayChatGenerationSource,
  createGatewayRequiredChatGenerationSource,
  readChatGenerationSourceCapability,
  type ChatGenerationSourceInput,
} from "./generation-source";

const context = createChatGenerationContextPacket({
  accountId: "account-1",
  generationId: "generation-1",
  nowEpochMilliseconds: 1,
  candidates: [{
    sourceKind: "memory",
    sourceId: "source-1",
    claimId: null,
    evidenceId: "evidence-1",
    ownerAccountId: "account-1",
    sourceHash: `sha256:${"1".repeat(64)}`,
    capturedAt: 1,
    expiresAt: null,
    redactedPreview: "The user prefers concise answers.",
    tokenEstimate: 6,
    inclusionReason: "authorized context",
  }],
});

const input = (
  overrides: Partial<ChatGenerationSourceInput> = {},
): ChatGenerationSourceInput => ({
  generationId: "generation-1",
  attemptId: "generation-1:attempt:1",
  prompt: "What should I do next?",
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

const safeReadTool = (
  execute: AgentToolDefinition["execute"],
  overrides: Partial<AgentToolDefinition> = {},
): AgentToolDefinition => ({
  schemaVersion: 1,
  name: "safe.fixture_status",
  risk: "safe",
  timeoutMs: 100,
  retryable: false,
  displaySummary: "Read fixture status",
  validateInput: (value): boolean => value !== null && typeof value === "object"
    && !Array.isArray(value) && Object.keys(value).length === 1
    && (value as Record<string, unknown>).scope === "current",
  execute,
  ...overrides,
});

const readOnlyToolSchema = Object.freeze({
  name: "safe.fixture_status",
  description: "Read the current fixture status.",
  parameters: Object.freeze({
    type: "object" as const,
    additionalProperties: false as const,
    properties: Object.freeze({ scope: Object.freeze({ type: "string" as const, enum: Object.freeze(["current"]) }) }),
    required: Object.freeze(["scope"]),
  }),
});

const seedAgentLedger = () => {
  const store = createInMemoryAgentRunEventStore();
  createAgentRunEventSupervisor({ events: store, nowEpochMilliseconds: () => 1 })
    .accepted({ runId: "generation-1", attemptId: "generation-1:attempt:1", admissionId: "admission-1" });
  return store;
};

const toolCallStream = (providerCallId: string, name = "safe.fixture_status", argumentsJson = "{\"scope\":\"current\"}") => stream(
  JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: providerCallId,
    function: { name, arguments: argumentsJson } }] } }] }),
  "[DONE]",
);

describe("gateway chat generation source", () => {
  test("executes one injected safe read-only tool exactly once, records a private-safe ledger, and completes a second gateway turn", async () => {
    const store = seedAgentLedger();
    let executions = 0;
    const bodies: Record<string, unknown>[] = [];
    const responses = [
      toolCallStream("provider-private-call-99"),
      stream(JSON.stringify({ choices: [{ delta: { content: "Canonical answer." } }] }), "[DONE]"),
      toolCallStream("different-provider-private-call"),
      stream(JSON.stringify({ choices: [{ delta: { content: "Replayed answer." } }] }), "[DONE]"),
    ];
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:8787",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => {
          executions += 1;
          return { summary: "Fixture is ready.", durationMs: 2, retryable: false };
        })]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async (_url, init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return responses.shift()!;
      },
    });
    const run = async (): Promise<string> => await new Promise((resolve, reject) => {
      const text: string[] = [];
      source.start(input({
        onDelta: (delta) => text.push(delta),
        onComplete: () => resolve(text.join("")),
        onError: reject,
      }));
    });

    expect(await run()).toBe("Canonical answer.");
    expect(await run()).toBe("Replayed answer.");
    expect(executions).toBe(1);
    expect(bodies).toHaveLength(4);
    expect(bodies[0]?.model).toBe("omi:auto:chat-agent");
    expect(bodies[0]?.tools).toEqual([{ type: "function", function: readOnlyToolSchema }]);
    expect(bodies[1]?.tool_choice).toBe("none");
    expect(JSON.stringify(bodies[1]?.messages)).toContain("Fixture is ready.");
    const durable = JSON.stringify(store.snapshot());
    expect(durable).toContain("tool_request");
    expect(durable).toContain("tool_result");
    expect(durable).not.toContain("provider-private");
    expect(durable).not.toContain("\"scope\"");
    expect(durable).not.toContain("service-secret");
  });

  test("unknown tools and malformed arguments fail closed through the durable tool ledger without execution", async () => {
    for (const fixture of [
      { name: "safe.unknown", args: "{\"private_id\":\"person-42\"}", code: "tool_unknown" },
      { name: "safe.fixture_status", args: "{not-json-private-id", code: "tool_invalid_input" },
    ]) {
      const store = seedAgentLedger();
      let executions = 0;
      const responses = [
        toolCallStream("provider-private-id", fixture.name, fixture.args),
        stream(JSON.stringify({ choices: [{ delta: { content: "Recovered safely." } }] }), "[DONE]"),
      ];
      const source = createGatewayChatGenerationSource({
        gatewayUrl: "https://gateway.internal",
        laneId: "omi:auto:chat-agent",
        serviceToken: "service-secret",
        readOnlyToolLoop: {
          registry: createAgentToolRegistry([safeReadTool(async () => {
            executions += 1;
            return { summary: "must not run", durationMs: 1, retryable: false };
          })]),
          tool: readOnlyToolSchema,
          agentRunEvents: store,
          nowEpochMilliseconds: () => 2,
        },
        fetch: async () => responses.shift()!,
      });
      const answer = await new Promise<string>((resolve, reject) => {
        const text: string[] = [];
        source.start(input({ onDelta: (delta) => text.push(delta),
          onComplete: () => resolve(text.join("")), onError: reject }));
      });
      expect(answer).toBe("Recovered safely.");
      expect(executions).toBe(0);
      const durable = JSON.stringify(store.snapshot());
      expect(durable).toContain(fixture.code);
      expect(durable).not.toContain("private_id");
      expect(durable).not.toContain("person-42");
      expect(durable).not.toContain("provider-private-id");
    }
  });

  test("enforces the advertised schema even when the injected registry validator is permissive", async () => {
    const store = seedAgentLedger();
    let executions = 0;
    const responses = [
      toolCallStream("provider-call", "safe.fixture_status", "{\"secret\":\"raw\"}"),
      stream(JSON.stringify({ choices: [{ delta: { content: "Rejected safely." } }] }), "[DONE]"),
    ];
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => {
          executions += 1;
          return { summary: "must not run", durationMs: 1, retryable: false };
        }, { validateInput: () => true })]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => responses.shift()!,
    });
    const answer = await new Promise<string>((resolve, reject) => {
      const text: string[] = [];
      source.start(input({ onDelta: (delta) => text.push(delta),
        onComplete: () => resolve(text.join("")), onError: reject }));
    });
    expect(answer).toBe("Rejected safely.");
    expect(executions).toBe(0);
    expect(JSON.stringify(store.snapshot())).toContain("tool_invalid_input");
    expect(JSON.stringify(store.snapshot())).not.toContain("secret");
  });

  test("does not execute when the durable tool request cannot be recorded", async () => {
    const backing = seedAgentLedger();
    let executions = 0;
    const rejectingStore: AgentRunEventStore = Object.freeze({
      append(raw: unknown) {
        if ((raw as { kind?: unknown })?.kind === "tool_request") {
          return { kind: "rejected" as const, reason: "ordering" as const };
        }
        return backing.append(raw);
      },
      list: (runId) => backing.list(runId),
      snapshot: () => backing.snapshot(),
      restore: (snapshot) => backing.restore(snapshot),
      reset: () => backing.reset(),
    });
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => {
          executions += 1;
          return { summary: "must not run", durationMs: 1, retryable: false };
        })]),
        tool: readOnlyToolSchema,
        agentRunEvents: rejectingStore,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => toolCallStream("provider-call"),
    });
    const failure = await new Promise<unknown>((resolve) => source.start(input({ onError: resolve })));
    expect(failure).toEqual({ code: "generation_provider_failed", retryable: true });
    expect(executions).toBe(0);
    expect(backing.list("generation-1").filter((event) => event.kind === "tool_request")).toHaveLength(0);
  });

  test("rejects gateway data after the terminal SSE marker", async () => {
    let completed = 0;
    const store = seedAgentLedger();
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => ({
          summary: "must not run", durationMs: 1, retryable: false,
        }))]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => stream("[DONE]", JSON.stringify({ choices: [{ delta: { content: "late" } }] })),
    });
    const failure = await new Promise<unknown>((resolve) => source.start(input({
      onComplete: () => { completed += 1; }, onError: resolve,
    })));
    expect(failure).toEqual({ code: "generation_provider_failed", retryable: true });
    expect(completed).toBe(0);
  });

  test("rejects an unterminated gateway fragment after the terminal SSE marker", async () => {
    const store = seedAgentLedger();
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => ({
          summary: "must not run", durationMs: 1, retryable: false,
        }))]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => new Response("data: [DONE]\n\ndata: {\"choices\":[]}"),
    });
    const failure = await new Promise<unknown>((resolve) => source.start(input({ onError: resolve })));
    expect(failure).toEqual({ code: "generation_provider_failed", retryable: true });
  });

  test("cancellation aborts a hanging safe tool and timeout records one terminal error", async () => {
    const cancellationStore = seedAgentLedger();
    let started!: () => void;
    const toolStarted = new Promise<void>((resolve) => { started = resolve; });
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async (_value, control) => {
          started();
          while (!control.cancelled) await Promise.resolve();
          return { summary: "late result", durationMs: 1, retryable: false };
        })]),
        tool: readOnlyToolSchema,
        agentRunEvents: cancellationStore,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => toolCallStream("provider-call"),
    });
    let terminals = 0;
    const run = source.start(input({ onComplete: () => { terminals += 1; }, onError: () => { terminals += 1; } }));
    await toolStarted;
    run.cancel();
    await Promise.resolve();
    expect(terminals).toBe(0);

    const timeoutStore = seedAgentLedger();
    const timeoutResponses = [toolCallStream("provider-timeout"), stream("[DONE]")];
    const timeoutSource = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(() => new Promise(() => {}), { timeoutMs: 5, retryable: true })]),
        tool: readOnlyToolSchema,
        agentRunEvents: timeoutStore,
        nowEpochMilliseconds: () => 2,
      },
      fetch: async () => timeoutResponses.shift()!,
    });
    await new Promise<void>((resolve, reject) => timeoutSource.start(input({ onComplete: resolve, onError: reject })));
    const timeoutEvents = timeoutStore.list("generation-1");
    expect(timeoutEvents.filter((event) => event.kind === "tool_error")).toHaveLength(1);
    expect(JSON.stringify(timeoutEvents)).toContain("tool_timeout");
  });

  test("sends only a semantic lane through the authenticated gateway and consumes SSE", async () => {
    const requests: Array<{ url: string; init: RequestInit }> = [];
    const deltas: string[] = [];
    const usages: unknown[] = [];
    let completed = 0;
    let failed: unknown = null;
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "http://127.0.0.1:8787",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      fetch: async (url, init) => {
        requests.push({ url: String(url), init: init ?? {} });
        return stream(
          JSON.stringify({ choices: [{ delta: { content: "Gateway " } }] }),
          JSON.stringify({
            choices: [{ delta: { content: "answer." } }],
            usage: { prompt_tokens: 9, completion_tokens: 2, total_tokens: 11 },
          }),
          "[DONE]",
        );
      },
    });

    source.start(input({
      onDelta: (text) => deltas.push(text),
      onUsage: (usage) => usages.push(usage),
      onComplete: () => { completed += 1; },
      onError: (error) => { failed = error; },
    }));
    for (let turn = 0; turn < 10 && completed === 0 && failed === null; turn += 1) await Promise.resolve();

    expect(readChatGenerationSourceCapability(source)).toEqual({
      tier: "real-provider",
      adapter: "omi-llm-gateway",
      deterministic: false,
    });
    expect(deltas).toEqual(["Gateway ", "answer."]);
    expect(usages).toEqual([{
      usageId: "generation-1:attempt:1:usage",
      provider: "omi-llm-gateway",
      model: "semantic-lane",
      inputTokens: 9,
      outputTokens: 2,
      totalTokens: 11,
    }]);
    expect(completed).toBe(1);
    expect(failed).toBeNull();
    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe("http://127.0.0.1:8787/v1/chat/completions");
    expect(requests[0]?.init.headers).toEqual({
      authorization: "Bearer service-secret",
      "content-type": "application/json",
      "x-omi-service-caller": "platform",
      "x-omi-user-uid": "account-1",
      "x-omi-llm-feature": "rewrite_chat",
    });
    const body = JSON.parse(String(requests[0]?.init.body)) as Record<string, unknown>;
    expect(body.model).toBe("omi:auto:chat-agent");
    expect(JSON.stringify(body)).not.toContain("glm");
    expect(JSON.stringify(body)).not.toContain("deepseek");
    expect(body.stream).toBe(true);
  });

  test("keeps a networked fake behind the authenticated HTTP gateway contract", async () => {
    let observed: Readonly<{
      authorization: string | null;
      caller: string | null;
      tenant: string | null;
      body: Record<string, unknown>;
    }> | null = null;
    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      async fetch(request) {
        observed = Object.freeze({
          authorization: request.headers.get("authorization"),
          caller: request.headers.get("x-omi-service-caller"),
          tenant: request.headers.get("x-omi-tenant-id"),
          body: await request.json() as Record<string, unknown>,
        });
        return stream(
          JSON.stringify({ choices: [{ delta: { content: "fake-through-gateway" } }] }),
          "[DONE]",
        );
      },
    });

    try {
      const source = createGatewayChatGenerationSource({
        gatewayUrl: `http://127.0.0.1:${server.port}`,
        laneId: "omi:auto:chat-agent",
        serviceToken: "network-test-token",
      });
      const deltas: string[] = [];
      const outcome = new Promise<"done" | "failed">((resolve) => {
        source.start(input({
          onDelta: (text) => deltas.push(text),
          onComplete: () => resolve("done"),
          onError: () => resolve("failed"),
        }));
      });

      expect(await outcome).toBe("done");
      expect(deltas).toEqual(["fake-through-gateway"]);
      expect(observed).toMatchObject({
        authorization: "Bearer network-test-token",
        caller: "platform",
        tenant: null,
      });
      expect(observed?.body.model).toBe("omi:auto:chat-agent");
      expect(observed?.body.stream).toBe(true);
    } finally {
      server.stop(true);
    }
  });

  test("fails closed when the gateway stream ends without its terminal marker", async () => {
    let completed = 0;
    let failed: unknown = null;
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      fetch: async () => stream(JSON.stringify({ choices: [{ delta: { content: "partial" } }] })),
    });

    source.start(input({
      onComplete: () => { completed += 1; },
      onError: (error) => { failed = error; },
    }));
    for (let turn = 0; turn < 10 && failed === null; turn += 1) await Promise.resolve();

    expect(completed).toBe(0);
    expect(failed).toEqual({ code: "generation_provider_failed", retryable: true });
  });

  test("cancellation aborts the gateway request without emitting a false failure", async () => {
    let signal: AbortSignal | undefined;
    let failed = 0;
    const source = createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal/v1/chat/completions",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
      fetch: (_url, init) => {
        signal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        });
      },
    });

    const run = source.start(input({ onError: () => { failed += 1; } }));
    run.cancel();
    await Promise.resolve();

    expect(signal?.aborted).toBe(true);
    expect(failed).toBe(0);
  });

  test("rejects provider model names and malformed gateway configuration", () => {
    expect(() => createGatewayChatGenerationSource({
      gatewayUrl: "https://gateway.internal",
      laneId: "deepseek-v4-flash",
      serviceToken: "service-secret",
    })).toThrow("invalid LLM gateway configuration");
    expect(() => createGatewayChatGenerationSource({
      gatewayUrl: "file:///tmp/gateway",
      laneId: "omi:auto:chat-agent",
      serviceToken: "service-secret",
    })).toThrow("invalid LLM gateway URL");
  });

  test("the app-facing no-gateway source fails instead of emitting a fake answer", async () => {
    const source = createGatewayRequiredChatGenerationSource();
    const deltas: string[] = [];
    let completed = false;
    let failed: unknown = null;

    source.start(input({
      onDelta: (text) => deltas.push(text),
      onComplete: () => { completed = true; },
      onError: (error) => { failed = error; },
    }));
    await Promise.resolve();

    expect(deltas).toEqual([]);
    expect(completed).toBe(false);
    expect(failed).toEqual({ code: "generation_provider_failed", retryable: true });
    expect(readChatGenerationSourceCapability(source)).toEqual({
      tier: "unknown",
      adapter: "llm-gateway-required",
      deterministic: false,
    });
  });

  test("detaches gateway configuration and fails closed before dropping attachment content", async () => {
    let request: RequestInit | undefined;
    let failed: unknown = null;
    const options = {
      gatewayUrl: "https://gateway.internal",
      laneId: "omi:auto:chat-agent",
      serviceToken: "original-token",
      fetch: async (_url, init) => {
        request = init;
        return stream("[DONE]");
      },
    };
    const source = createGatewayChatGenerationSource(options);
    options.laneId = "omi:auto:changed";
    options.serviceToken = "changed-token";

    source.start(input());
    for (let turn = 0; turn < 10 && request === undefined; turn += 1) await Promise.resolve();
    expect(JSON.parse(String(request?.body)).model).toBe("omi:auto:chat-agent");
    expect(request?.headers).toMatchObject({ authorization: "Bearer original-token" });

    source.start(input({
      attachments: [{
        id: "attachment-1",
        displayName: "notes.txt",
        mediaType: "text/plain",
        sizeBytes: 3,
        contentReference: "content-1",
        content: new Uint8Array([1, 2, 3]),
      }],
      onError: (error) => { failed = error; },
    }));
    await Promise.resolve();
    expect(failed).toEqual({ code: "generation_provider_failed", retryable: true });
  });
});
