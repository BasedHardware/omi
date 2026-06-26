import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { readFileSync } from "node:fs";
import { spawn } from "child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HermesRuntimeAdapter } from "../src/adapters/hermes.js";
import { OpenClawRuntimeAdapter } from "../src/adapters/openclaw.js";
import type { AdapterAttemptContext, AdapterBindingHandle } from "../src/adapters/interface.js";
import type { OutboundMessage } from "../src/protocol.js";

vi.mock("child_process", async () => {
  const actual = await vi.importActual<typeof import("child_process")>("child_process");
  return {
    ...actual,
    spawn: vi.fn(),
  };
});

function createMockProcess() {
  const proc = Object.assign(new EventEmitter(), {
    stdin: new PassThrough(),
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: vi.fn(() => {
      proc.emit("exit", 0);
    }),
    pid: 23456,
  });
  return proc;
}

function writeResponse(proc: ReturnType<typeof createMockProcess>, requestId: string, message: Record<string, unknown>): void {
  proc.stdout.write(`${JSON.stringify({ requestId, ...message })}\n`);
}

function collectRequests(proc: ReturnType<typeof createMockProcess>, handler: (request: Record<string, unknown>) => void): void {
  proc.stdin.on("data", (chunk) => {
    for (const line of chunk.toString().split("\n")) {
      if (!line.trim()) continue;
      handler(JSON.parse(line) as Record<string, unknown>);
    }
  });
}

function makeBinding(adapterId: "hermes" | "openclaw", adapterNativeSessionId: string): AdapterBindingHandle {
  return {
    sessionId: "omi-session",
    adapterId,
    adapterNativeSessionId,
    resumeFidelity: adapterId === "hermes" ? "native" : "none",
    cwd: "/tmp/work",
    model: "model-a",
  };
}

function makeAttemptContext(binding: AdapterBindingHandle): AdapterAttemptContext {
  return {
    sessionId: "omi-session",
    ownerId: "owner-runtime",
    requestId: "omi-request",
    clientId: "desktop",
    runId: "omi-run",
    attemptId: "omi-attempt",
    binding,
    prompt: [{ type: "text", text: "hello" }],
    mode: "act",
    tools: [{ name: "omi_tool", description: "tool", inputSchema: { type: "object" } }],
    model: "model-b",
    metadata: { protocolVersion: 2 },
  };
}

describe("env-command local subprocess adapters", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset();
    delete process.env.OMI_HERMES_ADAPTER_COMMAND;
    delete process.env.OMI_OPENCLAW_ADAPTER_COMMAND;
  });

  it("activates Hermes only from OMI_HERMES_ADAPTER_COMMAND or explicit command", async () => {
    const adapter = new HermesRuntimeAdapter();
    await expect(adapter.start()).rejects.toThrow("hermes adapter requires OMI_HERMES_ADAPTER_COMMAND");

    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    process.env.OMI_HERMES_ADAPTER_COMMAND = "/usr/local/bin/hermes-adapter --jsonl";

    await adapter.start();

    expect(spawn).toHaveBeenCalledWith(
      "/usr/local/bin/hermes-adapter --jsonl",
      expect.objectContaining({
        shell: true,
        stdio: ["pipe", "pipe", "pipe"],
        env: expect.objectContaining({
          OMI_ADAPTER_ID: "hermes",
        }),
      })
    );
    await adapter.stop();
  });

  it("maps Hermes open, resume, events, result fields, and artifacts without native id leakage", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new HermesRuntimeAdapter({ command: "hermes-adapter" });
    const requests: Record<string, unknown>[] = [];

    collectRequests(proc, (request) => {
      requests.push(request);
      if (request.type === "open") {
        expect(request).toMatchObject({
          type: "open",
          adapterId: "hermes",
          omiSessionId: "omi-session",
          cwd: "/tmp/work",
          model: "model-a",
        });
        expect(request).not.toHaveProperty("sessionId");
        writeResponse(proc, request.requestId as string, {
          type: "opened",
          adapterNativeSessionId: "hermes-native-1",
        });
      }
      if (request.type === "resume") {
        expect(request).toMatchObject({
          type: "resume",
          adapterNativeSessionId: "hermes-native-1",
          omiSessionId: "omi-session",
        });
        expect(request).not.toHaveProperty("sessionId");
        writeResponse(proc, request.requestId as string, {
          type: "resumed",
          adapterNativeSessionId: "hermes-native-1",
        });
      }
      if (request.type === "execute") {
        expect(request).toMatchObject({
          type: "execute",
          adapterNativeSessionId: "hermes-native-1",
          omiSessionId: "omi-session",
          ownerId: "owner-runtime",
          runId: "omi-run",
          attemptId: "omi-attempt",
          mode: "act",
          model: "model-b",
        });
        expect(request).not.toHaveProperty("sessionId");
        writeResponse(proc, request.requestId as string, {
          type: "event",
          event: { type: "text_delta", text: "hello " },
        });
        writeResponse(proc, request.requestId as string, {
          type: "event",
          event: { type: "thinking_delta", text: "thinking" },
        });
        writeResponse(proc, request.requestId as string, {
          type: "event",
          event: {
            type: "tool_activity",
            name: "omi_tool",
            status: "started",
            toolUseId: "tool-1",
            input: { q: "memory" },
          },
        });
        writeResponse(proc, request.requestId as string, {
          type: "event",
          event: {
            type: "tool_result_display",
            name: "omi_tool",
            toolUseId: "tool-1",
            output: "tool output",
          },
        });
        writeResponse(proc, request.requestId as string, {
          type: "event",
          event: {
            type: "artifact",
            artifact: {
              kind: "markdown",
              role: "result",
              uri: "adapter://hermes/artifact-1",
              displayName: "summary.md",
              mimeType: "text/markdown",
              contentHash: "sha256:abc",
              sizeBytes: 42,
              metadata: { nativeArtifactId: "artifact-1" },
            },
          },
        });
        writeResponse(proc, request.requestId as string, {
          type: "result",
          text: "hello world",
          adapterSessionId: "hermes-native-1",
          terminalStatus: "succeeded",
          costUsd: 0.12,
          inputTokens: 10,
          outputTokens: 20,
          cacheReadTokens: 3,
          cacheWriteTokens: 4,
          artifacts: [{
            kind: "json",
            role: "checkpoint",
            uri: "adapter://hermes/checkpoint-1",
          }],
        });
      }
    });

    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "model-a",
    });
    const resumed = await adapter.resumeBinding({
      ...opened,
      adapterNativeSessionId: opened.adapterNativeSessionId,
    });
    const events: OutboundMessage[] = [];
    const result = await adapter.executeAttempt(
      makeAttemptContext(resumed),
      (event) => events.push(event),
      new AbortController().signal
    );

    expect(opened).toMatchObject({
      sessionId: "omi-session",
      adapterNativeSessionId: "hermes-native-1",
      resumeFidelity: "native",
    });
    expect(result).toMatchObject({
      text: "hello world",
      adapterSessionId: "hermes-native-1",
      terminalStatus: "succeeded",
      costUsd: 0.12,
      inputTokens: 10,
      outputTokens: 20,
      cacheReadTokens: 3,
      cacheWriteTokens: 4,
    });
    expect("sessionId" in result).toBe(false);
    expect(result.artifacts).toEqual([
      expect.objectContaining({
        role: "result",
        uri: "adapter://hermes/artifact-1",
        metadata: { nativeArtifactId: "artifact-1" },
      }),
      expect.objectContaining({
        role: "checkpoint",
        uri: "adapter://hermes/checkpoint-1",
      }),
    ]);
    expect(events.map((event) => event.type)).toEqual([
      "text_delta",
      "thinking_delta",
      "tool_activity",
      "tool_result_display",
    ]);
    expect(requests.map((request) => request.type)).toEqual(["open", "resume", "execute"]);
    await adapter.stop();
  });

  it("maps OpenClaw tool events and reports cancellation ack only when the adapter says so", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new OpenClawRuntimeAdapter({ command: "openclaw-adapter" });
    let cancelCount = 0;

    collectRequests(proc, (request) => {
      if (request.type === "open") {
        writeResponse(proc, request.requestId as string, {
          type: "opened",
          adapterNativeSessionId: "openclaw-native-1",
        });
      }
      if (request.type === "execute") {
        expect(request).toMatchObject({
          adapterId: "openclaw",
          adapterNativeSessionId: "openclaw-native-1",
          omiSessionId: "omi-session",
          ownerId: "owner-runtime",
        });
        writeResponse(proc, request.requestId as string, {
          type: "tool_use",
          callId: "tool-1",
          name: "omi_tool",
          input: { q: "memory" },
        });
        writeResponse(proc, request.requestId as string, {
          type: "result",
          text: "done",
          adapterSessionId: "openclaw-native-1",
          terminalStatus: "succeeded",
        });
      }
      if (request.type === "cancel") {
        cancelCount += 1;
        expect(request).toMatchObject({
          adapterNativeSessionId: "openclaw-native-1",
          omiSessionId: "omi-session",
        });
        writeResponse(proc, request.requestId as string, {
          type: "cancelled",
          accepted: true,
          dispatchAttempted: true,
          adapterAcknowledged: cancelCount === 2,
        });
      }
    });

    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
    });
    expect(opened).toMatchObject({
      adapterId: "openclaw",
      adapterNativeSessionId: "openclaw-native-1",
      resumeFidelity: "none",
    });

    const events: OutboundMessage[] = [];
    const result = await adapter.executeAttempt(
      makeAttemptContext(opened),
      (event) => events.push(event),
      new AbortController().signal
    );
    expect(events).toEqual([
      expect.objectContaining({
        type: "tool_use",
        callId: "tool-1",
        name: "omi_tool",
        input: { q: "memory" },
      }),
    ]);
    expect(result).toMatchObject({
      text: "done",
      adapterSessionId: "openclaw-native-1",
    });

    await expect(adapter.cancelAttempt({ sessionId: "omi-session" })).resolves.toMatchObject({
      accepted: true,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });
    await expect(adapter.cancelAttempt({
      sessionId: "omi-session",
      runId: "omi-run",
      attemptId: "omi-attempt",
      binding: opened,
    })).resolves.toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    });
    await expect(adapter.cancelAttempt({
      sessionId: "omi-session",
      runId: "omi-run",
      attemptId: "omi-attempt",
      binding: opened,
    })).resolves.toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: true,
    });
    await adapter.stop();
  });

  it("does not import legacy permission policy from new adapter modules", () => {
    for (const file of [
      "src/adapters/local-subprocess.ts",
      "src/adapters/hermes.ts",
      "src/adapters/openclaw.ts",
    ]) {
      const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
      expect(source).not.toContain("legacyPermissionPolicy");
      expect(source).not.toContain("legacy-permission-policy");
    }
  });
});
