import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { spawn } from "child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HermesRuntimeAdapter } from "../src/adapters/hermes.js";
import { OpenClawRuntimeAdapter } from "../src/adapters/openclaw.js";
import { CodexRuntimeAdapter } from "../src/adapters/codex.js";
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
    delete process.env.OMI_CODEX_ADAPTER_COMMAND;
    delete process.env.OPENAI_API_KEY;
    delete process.env.CODEX_API_KEY;
    delete process.env.NO_BROWSER;
    delete process.env.INITIAL_AGENT_MODE;
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

  it("runs Codex through its real codex-acp command", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    process.env.OMI_CODEX_ADAPTER_COMMAND = "npx -y @agentclientprotocol/codex-acp";
    // Auth + headless + non-blocking permissions are provided via env; the
    // adapter must forward these to the untrusted subprocess.
    process.env.OPENAI_API_KEY = "sk-omi-test-key";
    process.env.NO_BROWSER = "1";
    process.env.INITIAL_AGENT_MODE = "agent-full-access";
    const adapter = new CodexRuntimeAdapter();
    const requests: Record<string, unknown>[] = [];

    collectJsonRpc(proc, (request) => {
      requests.push(request);
      if (request.method === "initialize") {
        // codex-acp returns acp.PROTOCOL_VERSION (1 today).
        writeJsonRpcResult(proc, request, { protocolVersion: 1 });
      }
      if (request.method === "session/new") {
        writeJsonRpcResult(proc, request, { sessionId: "codex-native-session" });
      }
      if (request.method === "session/prompt") {
        proc.stdout.write(`${JSON.stringify({
          jsonrpc: "2.0",
          method: "session/update",
          params: {
            update: {
              sessionUpdate: "agent_message_chunk",
              content: { type: "text", text: "OMI_CODEX_DOGFOOD_OK" },
            },
          },
        })}\n`);
        // codex-acp reports token usage but NOT costUsd.
        writeJsonRpcResult(proc, request, {
          stopReason: "end_turn",
          usage: { inputTokens: 7, outputTokens: 9, cachedReadTokens: 3 },
        });
      }
    });

    await adapter.start();

    // Codex is an external adapter, so the constrained permission policy must
    // still reject a permanent-only auto-approval request.
    proc.stdout.write(`${JSON.stringify({
      jsonrpc: "2.0",
      id: 77,
      method: "session/request_permission",
      params: { options: [{ kind: "allow_always", optionId: "allow" }] },
    })}\n`);
    await vi.waitUntil(() => requests.some((request) => request.id === 77 && "error" in request));
    expect(requests.find((request) => request.id === 77)).toMatchObject({ error: { code: -32001 } });

    // The subprocess env must carry the Codex auth/config vars (allowlist fix),
    // but never leak them for a non-Codex adapter.
    const spawnEnv = vi.mocked(spawn).mock.calls[0][1]?.env as NodeJS.ProcessEnv;
    expect(spawnEnv).toMatchObject({
      OMI_ADAPTER_ID: "codex",
      OPENAI_API_KEY: "sk-omi-test-key",
      NO_BROWSER: "1",
      INITIAL_AGENT_MODE: "agent-full-access",
    });

    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "gpt-5.2[high]",
    });
    const result = await adapter.executeAttempt(
      {
        ...makeOpenClawContext(binding),
        prompt: "Reply exactly: OMI_CODEX_DOGFOOD_OK",
        model: "gpt-5.2[high]",
      },
      () => {},
      new AbortController().signal
    );

    expect(binding).toMatchObject({
      adapterId: "codex",
      adapterNativeSessionId: "codex-native-session",
      resumeFidelity: "none",
    });
    expect(result).toMatchObject({
      text: "OMI_CODEX_DOGFOOD_OK",
      adapterSessionId: "codex-native-session",
      terminalStatus: "succeeded",
      inputTokens: 7,
      outputTokens: 9,
      cacheReadTokens: 3,
      costUsd: 0,
    });
    expect(spawn).toHaveBeenCalledWith(
      "npx -y @agentclientprotocol/codex-acp",
      expect.objectContaining({ shell: true, stdio: ["pipe", "pipe", "pipe"] })
    );
    // codex-acp has no standard session/set_model, so the adapter must not send it,
    // and it must send an empty per-session MCP server list.
    expect(requests.map((request) => request.method).filter(Boolean)).toEqual([
      "initialize",
      "session/new",
      "session/prompt",
    ]);
    expect(requests.find((request) => request.method === "session/new")?.params).toMatchObject({ mcpServers: [] });
    await adapter.stop();
  });
});
