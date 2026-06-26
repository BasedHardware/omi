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
    prompt: "Reply exactly: OMI_OPENCLAW_DOGFOOD_OK",
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
    await vi.waitUntil(() => requests.some((request) => request.id === 99 && "error" in request));
    expect(requests.find((request) => request.id === 99)).toMatchObject({
      error: {
        code: -32001,
        message: "hermes permission requests require adapter-owned approval policy",
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
      resumeFidelity: "native",
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

  it("runs OpenClaw through its real one-shot message command", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    process.env.OMI_OPENCLAW_ADAPTER_COMMAND = "openclaw agent";
    const adapter = new OpenClawRuntimeAdapter();

    await adapter.start();
    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "glm-5",
    });
    const execution = adapter.executeAttempt(
      makeOpenClawContext(binding),
      () => {},
      new AbortController().signal
    );
    proc.stdout.write("2026-06-26T04:10:23.585417Z  INFO openclaw: Config loaded\n");
    proc.stdout.write(JSON.stringify({
      payloads: [{ text: "OMI_OPENCLAW_DOGFOOD_OK" }],
      meta: {
        agentMeta: {
          usage: { input: 11, output: 12 },
          lastCallUsage: { input: 11, output: 12, cacheRead: 1, cacheWrite: 2 },
        },
      },
    }));
    proc.stdout.write("\n");
    proc.emit("exit", 0);

    await expect(execution).resolves.toMatchObject({
      text: "OMI_OPENCLAW_DOGFOOD_OK",
      adapterSessionId: "openclaw:omi-session",
      terminalStatus: "succeeded",
      inputTokens: 11,
      outputTokens: 12,
      cacheReadTokens: 1,
      cacheWriteTokens: 2,
    });
    expect(spawn).toHaveBeenCalledWith(
      "openclaw agent --local --json --session-key 'openclaw:omi-session' --model 'glm-5' --message 'Reply exactly: OMI_OPENCLAW_DOGFOOD_OK'",
      expect.objectContaining({
        shell: true,
        cwd: "/tmp/work",
        stdio: ["ignore", "pipe", "pipe"],
        env: expect.objectContaining({ OMI_ADAPTER_ID: "openclaw" }),
      })
    );
    await adapter.stop();
  });
});
