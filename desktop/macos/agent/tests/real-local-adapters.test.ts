import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { spawn } from "child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HermesRuntimeAdapter } from "../src/adapters/hermes.js";
import { OpenClawRuntimeAdapter } from "../src/adapters/openclaw.js";
import type { AdapterAttemptContext, AdapterBindingHandle } from "../src/adapters/interface.js";

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
    pid: 34567,
  });
  return proc;
}

function collectJsonRpc(proc: ReturnType<typeof createMockProcess>, handler: (request: Record<string, unknown>) => void): void {
  proc.stdin.on("data", (chunk) => {
    for (const line of chunk.toString().split("\n")) {
      if (!line.trim()) continue;
      handler(JSON.parse(line) as Record<string, unknown>);
    }
  });
}

function writeJsonRpcResult(proc: ReturnType<typeof createMockProcess>, request: Record<string, unknown>, result: Record<string, unknown>): void {
  proc.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result })}\n`);
}

function makeOpenClawContext(binding: AdapterBindingHandle): AdapterAttemptContext {
  return {
    sessionId: "omi-session",
    ownerId: "owner-runtime",
    requestId: "omi-request",
    clientId: "desktop",
    runId: "omi-run",
    attemptId: "omi-attempt",
    binding,
    prompt: [{ type: "text" as const, text: "Reply exactly: OMI_OPENCLAW_DOGFOOD_OK" }],
    mode: "act",
    tools: [],
    model: "glm-5",
    metadata: { protocolVersion: 2 },
  };
}

describe("real local Hermes/OpenClaw adapter wrappers", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset();
    delete process.env.OMI_HERMES_ADAPTER_COMMAND;
    delete process.env.OMI_OPENCLAW_ADAPTER_COMMAND;
  });

  it("runs Hermes through its real ACP command", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    process.env.OMI_HERMES_ADAPTER_COMMAND = "/Users/dazheng/.local/bin/hermes acp --accept-hooks";
    const adapter = new HermesRuntimeAdapter();
    const requests: Record<string, unknown>[] = [];

    collectJsonRpc(proc, (request) => {
      requests.push(request);
      if (request.method === "initialize") {
        writeJsonRpcResult(proc, request, { protocolVersion: 1 });
      }
      if (request.method === "session/new") {
        writeJsonRpcResult(proc, request, { sessionId: "hermes-native-session" });
      }
      if (request.method === "session/set_model") {
        writeJsonRpcResult(proc, request, {});
      }
      if (request.method === "session/prompt") {
        proc.stdout.write(`${JSON.stringify({
          jsonrpc: "2.0",
          method: "session/update",
          params: {
            update: {
              sessionUpdate: "agent_message_chunk",
              content: { type: "text", text: "OMI_HERMES_DOGFOOD_OK" },
            },
          },
        })}\n`);
        writeJsonRpcResult(proc, request, {
          usage: { inputTokens: 1, outputTokens: 2 },
          _meta: { costUsd: 0.01 },
        });
      }
    });

    await adapter.start();
    proc.stdout.write(`${JSON.stringify({
      jsonrpc: "2.0",
      id: 99,
      method: "session/request_permission",
      params: { options: [{ kind: "allow_always", optionId: "allow" }] },
    })}\n`);
    // Hermes is an autonomous external adapter (parity with OpenClaw, which
    // self-executes tools), so its permission requests are auto-approved rather
    // than rejected — the response selects the allow option.
    await vi.waitUntil(() => requests.some((request) => request.id === 99 && "result" in request));
    expect(requests.find((request) => request.id === 99)).toMatchObject({
      result: {
        outcome: { outcome: "selected", optionId: "allow" },
      },
    });
    expect(spawn).toHaveBeenCalledWith(
      "/Users/dazheng/.local/bin/hermes acp --accept-hooks",
      expect.objectContaining({ shell: true, stdio: ["pipe", "pipe", "pipe"] })
    );
    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "gpt-5.5",
    });
    const events: unknown[] = [];
    const result = await adapter.executeAttempt({
      ...makeOpenClawContext(binding),
      prompt: "Reply exactly: OMI_HERMES_DOGFOOD_OK",
      model: "gpt-5.5",
    }, (event) => events.push(event), new AbortController().signal);

    expect(binding).toMatchObject({
      adapterId: "hermes",
      adapterNativeSessionId: "hermes-native-session",
      resumeFidelity: "none",
    });
    expect(result).toMatchObject({
      text: "OMI_HERMES_DOGFOOD_OK",
      adapterSessionId: "hermes-native-session",
      terminalStatus: "succeeded",
      costUsd: 0.01,
      inputTokens: 1,
      outputTokens: 2,
    });
    expect(requests.map((request) => request.method).filter(Boolean)).toEqual([
      "initialize",
      "session/new",
      "session/set_model",
      "session/prompt",
    ]);
    await adapter.stop();
  });

  it("runs OpenClaw through its real ACP command", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    process.env.OMI_OPENCLAW_ADAPTER_COMMAND = "openclaw acp";
    const adapter = new OpenClawRuntimeAdapter();
    const requests: Record<string, unknown>[] = [];

    collectJsonRpc(proc, (request) => {
      requests.push(request);
      if (request.method === "initialize") {
        writeJsonRpcResult(proc, request, { protocolVersion: 1 });
      }
      if (request.method === "session/new") {
        writeJsonRpcResult(proc, request, { sessionId: "openclaw-native-session" });
      }
      if (request.method === "session/set_model") {
        writeJsonRpcResult(proc, request, {});
      }
      if (request.method === "session/prompt") {
        proc.stdout.write(`${JSON.stringify({
          jsonrpc: "2.0",
          method: "session/update",
          params: {
            update: {
              sessionUpdate: "agent_message_chunk",
              content: { type: "text", text: "OMI_OPENCLAW_DOGFOOD_OK" },
            },
          },
        })}\n`);
        writeJsonRpcResult(proc, request, {
          usage: { inputTokens: 11, outputTokens: 12 },
          _meta: { cacheReadTokens: 1, cacheWriteTokens: 2 },
        });
      }
    });

    await adapter.start();
    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "glm-5",
    });
    const result = await adapter.executeAttempt(
      makeOpenClawContext(binding),
      () => {},
      new AbortController().signal
    );

    expect(binding).toMatchObject({
      adapterId: "openclaw",
      adapterNativeSessionId: "openclaw-native-session",
      resumeFidelity: "native",
    });
    expect(binding.model).toBeUndefined();
    expect(result).toMatchObject({
      text: "OMI_OPENCLAW_DOGFOOD_OK",
      adapterSessionId: "openclaw-native-session",
      terminalStatus: "succeeded",
      inputTokens: 11,
      outputTokens: 12,
    });
    expect(spawn).toHaveBeenCalledWith(
      "openclaw acp",
      expect.objectContaining({ shell: true, stdio: ["pipe", "pipe", "pipe"] })
    );
    expect(requests.map((request) => request.method).filter(Boolean)).toEqual([
      "initialize",
      "session/new",
      "session/prompt",
    ]);
    expect(requests.find((request) => request.method === "session/new")?.params).toMatchObject({ mcpServers: [] });
    await adapter.stop();
  });

  it("resumes OpenClaw through its native ACP session id", async () => {
    const firstProc = createMockProcess();
    const secondProc = createMockProcess();
    vi.mocked(spawn)
      .mockReturnValueOnce(firstProc as any)
      .mockReturnValueOnce(secondProc as any);
    process.env.OMI_OPENCLAW_ADAPTER_COMMAND = "openclaw acp";
    const adapter = new OpenClawRuntimeAdapter();
    const requests: Record<string, unknown>[] = [];
    let promptCount = 0;

    for (const proc of [firstProc, secondProc]) {
      collectJsonRpc(proc, (request) => {
        requests.push(request);
        if (request.method === "initialize") {
          writeJsonRpcResult(proc, request, { protocolVersion: 1 });
        }
        if (request.method === "session/resume") {
          writeJsonRpcResult(proc, request, {});
        }
        if (request.method === "session/new") {
          writeJsonRpcResult(proc, request, { sessionId: "openclaw-native-session" });
        }
        if (request.method === "session/set_model") {
          writeJsonRpcResult(proc, request, {});
        }
        if (request.method === "session/prompt") {
          promptCount += 1;
          proc.stdout.write(`${JSON.stringify({
            jsonrpc: "2.0",
            method: "session/update",
            params: {
              update: {
                sessionUpdate: "agent_message_chunk",
                content: { type: "text", text: promptCount === 1 ? "remembered" : "BLUEFJORD" },
              },
            },
          })}\n`);
          writeJsonRpcResult(proc, request, {});
        }
      });
    }

    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "openrouter/openai/gpt-4.1-mini",
    });
    const firstExecution = adapter.executeAttempt(
      {
        ...makeOpenClawContext(binding),
        prompt: [{ type: "text" as const, text: "Remember BLUEFJORD." }],
        model: "openrouter/openai/gpt-4.1-mini",
      },
      () => {},
      new AbortController().signal
    );
    const firstResult = await firstExecution;

    expect(firstResult).toMatchObject({
      text: "remembered",
      adapterSessionId: "openclaw-native-session",
      terminalStatus: "succeeded",
    });
    expect(requests.find((request) => request.method === "session/new")?.params).toMatchObject({ mcpServers: [] });

    const resumeStartIndex = requests.length;
    const resumedBinding = await adapter.resumeBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "openrouter/openai/gpt-4.1-mini",
      adapterNativeSessionId: firstResult.adapterSessionId,
    });
    const secondProcessRequests = requests.slice(resumeStartIndex);
    const secondExecution = adapter.executeAttempt(
      {
        ...makeOpenClawContext(resumedBinding),
        prompt: [{ type: "text" as const, text: "What codeword did I ask you to remember?" }],
        model: "openrouter/openai/gpt-4.1-mini",
      },
      () => {},
      new AbortController().signal
    );

    await expect(secondExecution).resolves.toMatchObject({
      text: "BLUEFJORD",
      adapterSessionId: "openclaw-native-session",
      terminalStatus: "succeeded",
    });
    expect(requests.map((request) => request.method)).toContain("session/resume");
    expect(requests.map((request) => request.method)).not.toContain("session/set_model");
    expect(requests.find((request) => request.method === "session/resume")?.params).toMatchObject({ mcpServers: [] });
    expect(secondProcessRequests.map((request) => request.method)).not.toContain("session/new");
    await adapter.stop();
  });
});
