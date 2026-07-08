import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { readFileSync } from "node:fs";
import { spawn } from "child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LocalSubprocessRuntimeAdapter } from "../src/adapters/local-subprocess.js";
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

function responseId(request: Record<string, unknown>): string {
  return (request.adapterRequestId ?? request.requestId) as string;
}

function writeResponse(proc: ReturnType<typeof createMockProcess>, request: Record<string, unknown>, message: Record<string, unknown>): void {
  proc.stdout.write(`${JSON.stringify({ adapterRequestId: responseId(request), ...message })}\n`);
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
    resumeFidelity: adapterId === "openclaw" ? "native" : "none",
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
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "hermes", envCommandName: "OMI_HERMES_ADAPTER_COMMAND" });
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
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "hermes", envCommandName: "OMI_HERMES_ADAPTER_COMMAND", command: "hermes-adapter" });
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
        writeResponse(proc, request, {
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
        writeResponse(proc, request, {
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
          requestId: "omi-request",
          clientId: "desktop",
          runId: "omi-run",
          attemptId: "omi-attempt",
          mode: "act",
          model: "model-b",
        });
        expect(request).not.toHaveProperty("sessionId");
        writeResponse(proc, request, {
          type: "event",
          event: { type: "text_delta", text: "hello " },
        });
        writeResponse(proc, request, {
          type: "event",
          event: { type: "thinking_delta", text: "thinking" },
        });
        writeResponse(proc, request, {
          type: "event",
          event: {
            type: "tool_activity",
            name: "omi_tool",
            status: "started",
            toolUseId: "tool-1",
            input: { q: "memory" },
          },
        });
        writeResponse(proc, request, {
          type: "event",
          event: {
            type: "tool_result_display",
            name: "omi_tool",
            toolUseId: "tool-1",
            output: "tool output",
          },
        });
        writeResponse(proc, request, {
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
        writeResponse(proc, request, {
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
      resumeFidelity: "none",
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
    expect(result.artifacts).toBeUndefined();
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
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "openclaw", envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND", command: "openclaw-adapter" });
    let cancelCount = 0;

    collectRequests(proc, (request) => {
      if (request.type === "open") {
        writeResponse(proc, request, {
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
          requestId: "omi-request",
          clientId: "desktop",
        });
        writeResponse(proc, request, {
          type: "tool_use",
          callId: "tool-1",
          name: "omi_tool",
          input: { q: "memory" },
        });
        writeResponse(proc, request, {
          type: "event",
          event: {
            type: "artifact",
            artifact: {
              kind: "markdown",
              role: "result",
              uri: "adapter://openclaw/artifact-unsupported",
            },
          },
        });
        writeResponse(proc, request, {
          type: "result",
          text: "done",
          adapterSessionId: "openclaw-native-1",
          terminalStatus: "succeeded",
          artifacts: [{
            kind: "json",
            role: "result",
            uri: "adapter://openclaw/result-artifact-unsupported",
          }],
        });
      }
      if (request.type === "cancel") {
        cancelCount += 1;
        expect(request).toMatchObject({
          adapterNativeSessionId: "openclaw-native-1",
          omiSessionId: "omi-session",
          ownerId: "owner-runtime",
          requestId: "omi-request",
          clientId: "desktop",
        });
        writeResponse(proc, request, {
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
      resumeFidelity: "native",
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
    expect(result.artifacts).toBeUndefined();

    await expect(adapter.cancelAttempt({ sessionId: "omi-session" })).resolves.toMatchObject({
      accepted: true,
      dispatchAttempted: false,
      adapterAcknowledged: false,
    });
    await expect(adapter.cancelAttempt({
      sessionId: "omi-session",
      ownerId: "owner-runtime",
      requestId: "omi-request",
      clientId: "desktop",
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
      ownerId: "owner-runtime",
      requestId: "omi-request",
      clientId: "desktop",
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

  it("does not dispatch a second native cancel when the attempt signal aborts", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "hermes", envCommandName: "OMI_HERMES_ADAPTER_COMMAND", command: "hermes-adapter" });
    let executeRequest: Record<string, unknown> | undefined;
    let cancelRequests = 0;

    collectRequests(proc, (request) => {
      if (request.type === "open") {
        writeResponse(proc, request, {
          type: "opened",
          adapterNativeSessionId: "hermes-native-1",
        });
      }
      if (request.type === "execute") {
        executeRequest = request;
      }
      if (request.type === "cancel") {
        cancelRequests += 1;
        writeResponse(proc, request, {
          type: "cancelled",
          accepted: true,
          dispatchAttempted: true,
          adapterAcknowledged: true,
        });
      }
    });

    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
    });
    const controller = new AbortController();
    const execution = adapter.executeAttempt(makeAttemptContext(opened), () => {}, controller.signal);
    await vi.waitUntil(() => executeRequest !== undefined);

    controller.abort();
    expect(cancelRequests).toBe(0);
    writeResponse(proc, executeRequest!, {
      type: "result",
      text: "partial",
      adapterSessionId: "hermes-native-1",
      terminalStatus: "succeeded",
    });

    await expect(execution).rejects.toThrow("hermes adapter request aborted");
    expect(cancelRequests).toBe(0);
    await adapter.stop();
  });

  it("rejects missing or unknown terminal statuses instead of assuming success", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "hermes", envCommandName: "OMI_HERMES_ADAPTER_COMMAND", command: "hermes-adapter" });

    collectRequests(proc, (request) => {
      if (request.type === "open") {
        writeResponse(proc, request, {
          type: "opened",
          adapterNativeSessionId: "hermes-native-1",
        });
      }
      if (request.type === "execute") {
        writeResponse(proc, request, {
          type: "result",
          text: "looks done",
          adapterSessionId: "hermes-native-1",
          terminalStatus: "adapter_native_done",
        });
      }
    });

    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
    });

    await expect(
      adapter.executeAttempt(makeAttemptContext(opened), () => {}, new AbortController().signal)
    ).rejects.toThrow("hermes result missing valid terminalStatus");
    await adapter.stop();
  });

  it("preserves structured failed-result payloads", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "openclaw", envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND", command: "openclaw-adapter" });

    collectRequests(proc, (request) => {
      if (request.type === "open") {
        writeResponse(proc, request, {
          type: "opened",
          adapterNativeSessionId: "openclaw-native-1",
        });
      }
      if (request.type === "execute") {
        writeResponse(proc, request, {
          type: "result",
          text: "",
          adapterSessionId: "openclaw-native-1",
          terminalStatus: "failed",
          failure: {
            code: "adapter_process_exited",
            source: "adapter_process",
            adapterId: "openclaw",
            provider: "openai",
            retryable: true,
            userMessage: "OpenClaw failed: OpenAI API error: upstream unavailable",
            technicalMessage: "OpenAI API error: upstream unavailable",
          },
        });
      }
    });

    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
    });

    const result = await adapter.executeAttempt(makeAttemptContext(opened), () => {}, new AbortController().signal);
    expect(result).toMatchObject({
      terminalStatus: "failed",
      failure: {
        code: "adapter_process_exited",
        source: "adapter_process",
        adapterId: "openclaw",
        provider: "openai",
        userMessage: "OpenClaw failed: OpenAI API error: upstream unavailable",
      },
    });
    await adapter.stop();
  });

  it("routes ACP permission handling through desktop tool policy", () => {
    const source = readFileSync(new URL("../src/adapters/acp.ts", import.meta.url), "utf8");
    expect(source).toContain("resolveAcpPermission");
    expect(source).toContain("resolveExternalAcpPermission");
    expect(source).not.toContain("legacy-permission-policy");
  });

  it("tracks local ACP adapters for bridge shutdown", () => {
    const source = readFileSync(new URL("../src/index.ts", import.meta.url), "utf8");
    expect(source).toContain("const localAcpAdapters = new Set<RuntimeAdapter>()");
    expect(source).toContain("localAcpAdapters.add(adapter)");
    expect(source).toContain("await stopLocalAcpAdapters()");
    expect(source).toContain("void stopLocalAcpAdapters()");
  });

  it("uses a minimal allowlist for the external adapter subprocess environment", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new LocalSubprocessRuntimeAdapter({ adapterId: "hermes", envCommandName: "OMI_HERMES_ADAPTER_COMMAND", command: "hermes-adapter" });

    // Simulate Omi injecting credentials and host secrets into process.env.
    const saved: Record<string, string | undefined> = {};
    const secretKeys = [
      "OMI_AUTH_TOKEN", "OMI_BYOK_OPENAI", "OMI_BYOK_ANTHROPIC", "OMI_BYOK_GEMINI", "OMI_BYOK_DEEPGRAM",
      "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "CI_JOB_TOKEN",
    ];
    for (const key of secretKeys) {
      saved[key] = process.env[key];
      process.env[key] = "secret-value";
    }
    // Save proxy var so it is restored even though it is set later.
    saved["HTTPS_PROXY"] = process.env.HTTPS_PROXY;
    delete process.env.HTTPS_PROXY;
    try {
      await adapter.start();

      const callEnv = (vi.mocked(spawn).mock.calls[0] as readonly unknown[])[1] as { env: Record<string, string> };
      // No secrets are forwarded.
      for (const key of secretKeys) {
        expect(callEnv.env).not.toHaveProperty(key);
      }
      // OMI_ADAPTER_ID is always injected.
      expect(callEnv.env).toHaveProperty("OMI_ADAPTER_ID", "hermes");
      // Allowlisted OS vars are forwarded.
      expect(callEnv.env).toHaveProperty("PATH", process.env.PATH);
      // Proxy vars are forwarded (with credentials stripped) when set.
      process.env.HTTPS_PROXY = "http://alice:s3cr3t@proxy:3128";
      await adapter.stop();
      await adapter.start();
      const env2 = (vi.mocked(spawn).mock.calls[vi.mocked(spawn).mock.calls.length - 1] as readonly unknown[])[1] as { env: Record<string, string> };
      expect(env2.env).toHaveProperty("HTTPS_PROXY", "http://proxy:3128/");
      await adapter.stop();
    } finally {
      for (const [key, val] of Object.entries(saved)) {
        if (val === undefined) delete process.env[key];
        else process.env[key] = val;
      }
    }
  });
});
