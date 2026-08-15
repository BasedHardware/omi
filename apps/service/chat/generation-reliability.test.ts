import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { createAgentRunEventSupervisor, createInMemoryAgentRunEventStore } from "./agent-run-events";
import { createAgentToolRegistry, type AgentToolDefinition } from "./agent-tools";
import { logLineHasSecret } from "./dev-stack-log";
import { createChatGenerationContextPacket } from "./generation-context";
import {
  createGatewayChatGenerationSource,
  type ChatGenerationSourceInput,
} from "./generation-source";

const SECRET_TOKEN = "service-secret-do-not-log";
const PROMPT = "What should I do next?";

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
  prompt: PROMPT,
  context,
  attachments: [],
  onDelta() {},
  onComplete() {},
  onError() {},
  ...overrides,
});

const encodeSse = (payload: string): Uint8Array =>
  new TextEncoder().encode(`data: ${payload}\n\n`);

const streamFromChunks = (...chunks: readonly Uint8Array[]): Response => new Response(
  new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  }),
  { status: 200, headers: { "content-type": "text/event-stream" } },
);

const sse = (...events: readonly string[]): Response =>
  streamFromChunks(...events.map((event) => encodeSse(event)));

const delayedPreamble = (delayMs: number): Response => new Response(
  new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(encodeSse(JSON.stringify({
        choices: [{ delta: { reasoning_content: "thinking" } }],
      })));
      await Bun.sleep(delayMs);
      controller.enqueue(encodeSse(JSON.stringify({
        choices: [{ delta: { content: "ok" } }],
      })));
      controller.enqueue(encodeSse("[DONE]"));
      controller.close();
    },
  }),
  { status: 200, headers: { "content-type": "text/event-stream" } },
);

const statusResponse = (status: number): Response => new Response("no", { status });

const readOnlyToolSchema = Object.freeze({
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

const safeReadTool = (execute: AgentToolDefinition["execute"]): AgentToolDefinition => ({
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
});

const seedAgentLedger = () => {
  const store = createInMemoryAgentRunEventStore();
  createAgentRunEventSupervisor({ events: store, nowEpochMilliseconds: () => 1 })
    .accepted({ runId: "generation-1", attemptId: "generation-1:attempt:1", admissionId: "admission-1" });
  return store;
};

const runSource = async (
  fetchImpl: typeof fetch,
  extra: Partial<Parameters<typeof createGatewayChatGenerationSource>[0]> = {},
): Promise<{ text: string; error: unknown; usage: unknown[] }> => {
  const source = createGatewayChatGenerationSource({
    gatewayUrl: "http://127.0.0.1:8787",
    laneId: "omi:auto:chat-agent",
    serviceToken: SECRET_TOKEN,
    retrySleep: async () => {},
    fetch: fetchImpl,
    ...extra,
  });
  const usage: unknown[] = [];
  return await new Promise((resolve) => {
    const text: string[] = [];
    source.start(input({
      onDelta: (delta) => { if (delta.length > 0) text.push(delta); },
      onUsage: (entry) => usage.push(entry),
      onComplete: () => resolve({ text: text.join(""), error: null, usage }),
      onError: (error) => resolve({ text: text.join(""), error, usage }),
    }));
  });
};

const readChatLog = (runDir: string): readonly Record<string, unknown>[] => {
  const path = join(runDir, "logs", "chat.jsonl");
  return readFileSync(path, "utf8").trim().split("\n").map((line) => JSON.parse(line) as Record<string, unknown>);
};

describe("chat generation reliability", () => {
  const originalRunDir = process.env.OMI_DEV_STACK_RUNDIR;
  let runDir = "";

  const isolateLogs = (): string => {
    runDir = mkdtempSync(join(tmpdir(), "omi-chat-reliability-"));
    process.env.OMI_DEV_STACK_RUNDIR = runDir;
    return runDir;
  };

  afterEach(() => {
    if (originalRunDir === undefined) delete process.env.OMI_DEV_STACK_RUNDIR;
    else process.env.OMI_DEV_STACK_RUNDIR = originalRunDir;
    if (runDir.length > 0) rmSync(runDir, { recursive: true, force: true });
    runDir = "";
  });

  test("slow reasoning preamble is measured and still completes", async () => {
    isolateLogs();
    const result = await runSource(async () => delayedPreamble(40));
    expect(result.error).toBeNull();
    expect(result.text).toBe("ok");
    const events = readChatLog(runDir).map((row) => row.event);
    expect(events).toContain("generation_admitted");
    expect(events).toContain("provider_request_started");
    expect(events).toContain("reasoning_preamble");
    expect(events).toContain("first_content_delta");
    expect(events).toContain("generation_terminal");
    const firstContent = readChatLog(runDir).find((row) => row.event === "first_content_delta");
    expect(firstContent?.msSinceStart).toBeGreaterThanOrEqual(40);
    expect(firstContent?.reasoningPreambleMs).toBeGreaterThanOrEqual(40);
  });

  test("retries a 429 once, then completes, and logs both attempts", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      if (calls === 1) return statusResponse(429);
      return sse(
        JSON.stringify({ choices: [{ delta: { content: "recovered" } }] }),
        "[DONE]",
      );
    });
    expect(calls).toBe(2);
    expect(result.error).toBeNull();
    expect(result.text).toBe("recovered");
    const started = readChatLog(runDir).filter((row) => row.event === "provider_request_started");
    expect(started).toHaveLength(2);
    expect(started.map((row) => row.attempt)).toEqual([1, 2]);
    expect(readChatLog(runDir).some((row) => row.event === "provider_attempt_failed" && row.reason === "http_429")).toBe(true);
  });

  test("exhausts retries on repeated 5xx and logs every attempt", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      return statusResponse(503);
    });
    expect(calls).toBe(3);
    expect(result.error).toEqual({ code: "generation_provider_failed", retryable: true });
    const started = readChatLog(runDir).filter((row) => row.event === "provider_request_started");
    expect(started).toHaveLength(3);
    expect(readChatLog(runDir).filter((row) => row.event === "provider_attempt_failed")).toHaveLength(3);
    expect(readChatLog(runDir).at(-1)).toMatchObject({ event: "generation_terminal", outcome: "failed" });
  });

  test("does not retry a 4xx that is about the request", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      return statusResponse(400);
    });
    expect(calls).toBe(1);
    expect(result.error).toEqual({ code: "generation_provider_failed", retryable: true });
  });

  test("does not retry after content has been delivered", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      return new Response(new ReadableStream<Uint8Array>({
        async start(controller) {
          controller.enqueue(encodeSse(JSON.stringify({ choices: [{ delta: { content: "partial" } }] })));
          await new Promise((resolve) => setTimeout(resolve, 0));
          controller.error(new Error("reset after content"));
        },
      }), { status: 200 });
    });
    expect(calls).toBe(1);
    expect(result.text).toBe("partial");
    expect(result.error).toEqual({ code: "generation_provider_failed", retryable: true });
  });

  test("a stream that ends without [DONE] after content still completes", async () => {
    isolateLogs();
    const result = await runSource(async () => sse(
      JSON.stringify({ choices: [{ delta: { content: "done-less" } }] }),
    ));
    expect(result.error).toBeNull();
    expect(result.text).toBe("done-less");
    expect(readChatLog(runDir).some((row) => row.event === "stream_ended_without_done")).toBe(true);
  });

  test("SSE frames split across chunk boundaries still parse", async () => {
    isolateLogs();
    const payload = `data: ${JSON.stringify({ choices: [{ delta: { content: "split" } }] })}\n\ndata: [DONE]\n\n`;
    const bytes = new TextEncoder().encode(payload);
    const result = await runSource(async () => streamFromChunks(bytes.slice(0, 17), bytes.slice(17)));
    expect(result.error).toBeNull();
    expect(result.text).toBe("split");
  });

  test("a leftover [DONE] without a trailing blank line still completes", async () => {
    isolateLogs();
    const result = await runSource(async () => new Response(
      `data: ${JSON.stringify({ choices: [{ delta: { content: "tail" } }] })}\n\ndata: [DONE]`,
      { status: 200, headers: { "content-type": "text/event-stream" } },
    ));
    expect(result.error).toBeNull();
    expect(result.text).toBe("tail");
  });

  test("tool-loop retries empty [DONE] then completes when content arrives", async () => {
    isolateLogs();
    const store = seedAgentLedger();
    const responses = [
      sse(JSON.stringify({ choices: [{ delta: { reasoning_content: "thinking" } }] }), "[DONE]"),
      sse(
        JSON.stringify({ choices: [{ delta: { content: "ok" } }] }),
        "[DONE]",
      ),
    ];
    const result = await runSource(async () => responses.shift()!, {
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => ({
          summary: "Fixture is ready.", durationMs: 2, retryable: false,
        }))]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
    });
    expect(result.error).toBeNull();
    expect(result.text).toBe("ok");
    expect(readChatLog(runDir).some((row) => row.event === "provider_attempt_failed" && row.reason === "empty_done")).toBe(true);
    expect(readChatLog(runDir).filter((row) => row.event === "provider_request_started")).toHaveLength(2);
  });

  test("tool-call round trip logs the required events and carries no secrets", async () => {
    isolateLogs();
    const store = seedAgentLedger();
    const responses = [
      sse(JSON.stringify({
        choices: [{ delta: { tool_calls: [{ index: 0, id: "provider-call",
          function: { name: "safe.fixture_status", arguments: "{\"scope\":\"current\"}" } }] } }],
      }), "[DONE]"),
      sse(
        JSON.stringify({ choices: [{ delta: { content: "Canonical answer." } }] }),
        JSON.stringify({ usage: { prompt_tokens: 4, completion_tokens: 2, total_tokens: 6 } }),
        "[DONE]",
      ),
    ];
    const result = await runSource(async () => responses.shift()!, {
      readOnlyToolLoop: {
        registry: createAgentToolRegistry([safeReadTool(async () => ({
          summary: "Fixture is ready.", durationMs: 2, retryable: false,
        }))]),
        tool: readOnlyToolSchema,
        agentRunEvents: store,
        nowEpochMilliseconds: () => 2,
      },
    });
    expect(result.error).toBeNull();
    expect(result.text).toBe("Canonical answer.");
    const raw = readFileSync(join(runDir, "logs", "chat.jsonl"), "utf8");
    expect(logLineHasSecret(raw, [SECRET_TOKEN, PROMPT, "Bearer", "provider-call", "scope"])).toBe(false);
    const events = raw.trim().split("\n").map((line) => JSON.parse(line) as Record<string, unknown>);
    expect(events.some((row) => row.event === "generation_admitted")).toBe(true);
    expect(events.some((row) => row.event === "provider_request_started")).toBe(true);
    expect(events.some((row) => row.event === "first_content_delta")).toBe(true);
    expect(events.some((row) => row.event === "usage")).toBe(true);
    expect(events.at(-1)).toMatchObject({ event: "generation_terminal", outcome: "done" });
  });

  test("retries an empty [DONE] stream once, then completes when content arrives", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      if (calls === 1) {
        return sse(
          JSON.stringify({ choices: [{ delta: { reasoning_content: "thinking" } }] }),
          "[DONE]",
        );
      }
      return sse(
        JSON.stringify({ choices: [{ delta: { content: "ok" } }] }),
        "[DONE]",
      );
    });
    expect(calls).toBe(2);
    expect(result.error).toBeNull();
    expect(result.text).toBe("ok");
    expect(readChatLog(runDir).some((row) => row.event === "provider_attempt_failed" && row.reason === "empty_done")).toBe(true);
  });

  test("exhausts retries when every attempt is [DONE] with no content", async () => {
    isolateLogs();
    let calls = 0;
    const result = await runSource(async () => {
      calls += 1;
      return sse("[DONE]");
    });
    expect(calls).toBe(3);
    expect(result.error).toEqual({ code: "generation_provider_failed", retryable: true });
    expect(readChatLog(runDir).filter((row) => row.event === "provider_attempt_failed" && row.reason === "empty_done")).toHaveLength(3);
  });

  test("reliability log lines never carry secrets", async () => {
    isolateLogs();
    await runSource(async () => sse(
      JSON.stringify({ choices: [{ delta: { content: "safe" } }] }),
      "[DONE]",
    ));
    const raw = readFileSync(join(runDir, "logs", "chat.jsonl"), "utf8");
    expect(logLineHasSecret(raw, [SECRET_TOKEN, PROMPT, "Bearer ", "sk-"])).toBe(false);
    for (const row of readChatLog(runDir)) {
      expect(row.proc).toBe("chat");
      expect(typeof row.ts).toBe("string");
      expect(typeof row.level).toBe("string");
      expect(typeof row.event).toBe("string");
    }
  });
});
