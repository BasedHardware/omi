import { describe, expect, test } from "bun:test";

import { createChatGenerationContextPacket } from "./generation-context";
import {
  createGatewayChatGenerationSource,
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

describe("gateway chat generation source", () => {
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
      "x-omi-tenant-id": "account-1",
      "x-omi-llm-feature": "rewrite_chat",
    });
    const body = JSON.parse(String(requests[0]?.init.body)) as Record<string, unknown>;
    expect(body.model).toBe("omi:auto:chat-agent");
    expect(JSON.stringify(body)).not.toContain("glm");
    expect(JSON.stringify(body)).not.toContain("deepseek");
    expect(body.stream).toBe(true);
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
