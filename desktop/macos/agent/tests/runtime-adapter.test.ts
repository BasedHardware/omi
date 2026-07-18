import { PassThrough } from "node:stream";
import { EventEmitter } from "node:events";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { spawn } from "child_process";
import { AcpError, AcpRuntimeAdapter, isRecoverableAcpAuthError } from "../src/adapters/acp.js";
import {
  PiMonoAdapter,
  PiMonoRuntimeAdapter,
} from "../src/adapters/pi-mono.js";
import {
  ADAPTER_CAPABILITY_MATRIX,
  PLACEHOLDER_RUNTIME_ADAPTERS,
  PLACEHOLDER_ADAPTER_IDS,
  PRODUCTION_ADAPTER_IDS,
  adapterCapabilitiesFor,
} from "../src/adapters/interface.js";
import type {
  AdapterAttemptContext,
  OpenedBinding,
  RuntimeAdapter,
} from "../src/adapters/interface.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AdapterWorkerPool, configuredMaxWorkers, configuredPiMonoMaxWorkers } from "../src/runtime/worker-pool.js";
import { AdapterRuntimeError } from "../src/runtime/failures.js";
import { FakeRuntimeAdapter } from "./kernel-fakes.js";

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
    pid: 12345,
  });
  return proc;
}

function fakeAdapter(adapterId = "fake"): RuntimeAdapter {
  return {
    adapterId,
    capabilities: {
      resumeFidelity: "native",
      supportsNativeResume: true,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: false,
      supportsModelSwitching: true,
      supportsArtifactEmission: true,
      supportsTools: true,
      restartBehavior: "native_bindings_survive",
    },
    start: async () => {},
    stop: async () => {},
    openBinding: async (input) => ({
      sessionId: input.sessionId,
      adapterId,
      adapterNativeSessionId: "native",
      resumeFidelity: "native",
      cwd: input.cwd,
    }),
    resumeBinding: async (input) => ({
      sessionId: input.sessionId,
      adapterId,
      adapterNativeSessionId: input.adapterNativeSessionId,
      resumeFidelity: "native",
      cwd: input.cwd,
    }),
    executeAttempt: async (context: AdapterAttemptContext) => ({
      text: "",      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    }),
    cancelAttempt: async () => ({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    }),
  };
}

describe("ACP authentication recovery classification", () => {
  it("accepts the canonical ACP auth-required error", () => {
    expect(isRecoverableAcpAuthError(new AcpError("Authentication required", -32000))).toBe(true);
  });

  it("accepts the wrapped provider 401 returned during session/prompt", () => {
    const error = new AcpError(
      'Internal error: Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}',
      -32603,
    );

    expect(isRecoverableAcpAuthError(error)).toBe(true);
  });

  it("accepts structured auth failure data when the message is generic", () => {
    const error = new AcpError("Internal error", -32603, {
      error: { type: "authentication_error", message: "token rejected" },
    });

    expect(isRecoverableAcpAuthError(error)).toBe(true);
  });

  it("leaves unrelated internal and non-ACP errors terminal", () => {
    expect(isRecoverableAcpAuthError(new AcpError("Internal error: database unavailable", -32603))).toBe(false);
    expect(isRecoverableAcpAuthError(new Error("Invalid authentication credentials"))).toBe(false);
  });
});

describe("external ACP terminal failures", () => {
  it("does not mark an external HTTP 400 emitted as final text as successful", async () => {
    for (const provider of ["hermes", "openclaw"] as const) {
      const adapter = new AcpRuntimeAdapter({ adapterId: provider });
      vi.spyOn(adapter, "request").mockImplementation(async (method) => {
        if (method !== "session/prompt") {
          throw new Error(`Unexpected ACP method: ${method}`);
        }
        (adapter as any).notificationHandler("session/update", {
          update: {
            sessionUpdate: "agent_message_chunk",
            content: {
              type: "text",
              text: 'HTTP 400: {"detail":"The selected model is not supported."}',
            },
          },
        });
        return { usage: {} };
      });

      const result = await adapter.executeAttempt({
        sessionId: `ses_${provider}`,
        ownerId: "owner",
        requestId: `request-${provider}`,
        clientId: "client",
        runId: `run_${provider}`,
        attemptId: `att_${provider}`,
        toolCapabilityRef: "capability",
        binding: {
          sessionId: `ses_${provider}`,
          adapterId: provider,
          adapterNativeSessionId: `native-${provider}`,
          resumeFidelity: "none",
          cwd: "/tmp",
        },
        prompt: [{ type: "text", text: "Summarize recent activity" }],
        mode: "act",
      }, () => {}, new AbortController().signal);

      expect(result).toMatchObject({
        terminalStatus: "failed",
        text: `${provider === "hermes" ? "Hermes" : "OpenClaw"} could not complete the request. Try again.`,
        failure: {
          code: "adapter_terminal_http_failure",
          adapterId: provider,
          retryable: false,
        },
      });
    }
  });
});

describe("AcpRuntimeAdapter process spawning", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset();
  });

  it("uses argv spawning for the default ACP bridge path", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "acp",
      nodeBin: "/path with space/node",
      acpEntry: "/acp entry.mjs",
    });
    proc.stdin.on("data", () => {});
    await adapter.start();

    expect(vi.mocked(spawn).mock.calls[0]).toMatchObject([
      "/path with space/node",
      ["/acp entry.mjs"],
      expect.objectContaining({ shell: false, stdio: ["pipe", "pipe", "pipe"] }),
    ]);
  });

  it("preserves a configured command override as-is (env command is responsible for its own quoting)", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "hermes",
      command: "/usr/local/bin/hermes-agent",
      envCommandName: "HERMES_COMMAND",
    });
    proc.stdin.on("data", () => {});
    await adapter.start();

    expect(vi.mocked(spawn).mock.calls[0]).toMatchObject([
      "/usr/local/bin/hermes-agent",
      expect.objectContaining({ shell: true, stdio: ["pipe", "pipe", "pipe"] }),
    ]);
  });

  it("uses a minimal allowlist for external ACP adapter subprocess env", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "hermes",
      command: "/usr/local/bin/hermes-agent",
      envCommandName: "OMI_HERMES_ADAPTER_COMMAND",
    });

    const saved: Record<string, string | undefined> = {};
    const secretKeys = [
      "OMI_AUTH_TOKEN", "OMI_BYOK_OPENAI", "OMI_BYOK_ANTHROPIC", "OMI_BYOK_GEMINI", "OMI_BYOK_DEEPGRAM",
      "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "CI_JOB_TOKEN",
    ];
    for (const key of secretKeys) {
      saved[key] = process.env[key];
      process.env[key] = "secret-value";
    }
    // HERMES_HOME is allowlisted, not secret — simulate Swift seeding it.
    saved["HERMES_HOME"] = process.env.HERMES_HOME;
    process.env.HERMES_HOME = "/custom/hermes/home";
    try {
      proc.stdin.on("data", () => {});
      await adapter.start();

      const callEnv = (vi.mocked(spawn).mock.calls[0] as readonly unknown[])[1] as { env: Record<string, string> };
      // No secrets are forwarded under the allowlist model.
      for (const key of secretKeys) {
        expect(callEnv.env).not.toHaveProperty(key);
      }
      // Allowlisted OS vars and OMI_ADAPTER_ID are present.
      expect(callEnv.env).toHaveProperty("OMI_ADAPTER_ID", "hermes");
      expect(callEnv.env).toHaveProperty("PATH", process.env.PATH);
      // Adapter-specific home is forwarded so the external adapter can locate config/state.
      expect(callEnv.env).toHaveProperty("HERMES_HOME", "/custom/hermes/home");
      await adapter.stop();
    } finally {
      for (const [key, val] of Object.entries(saved)) {
        if (val === undefined) delete process.env[key];
        else process.env[key] = val;
      }
    }
  });

  it("does not scrub Omi credentials for the built-in ACP (Claude) subprocess", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    // adapterId "acp" uses the built-in nodeBin + acpEntry path (no external command).
    const adapter = new AcpRuntimeAdapter({
      adapterId: "acp",
      nodeBin: "/node",
      acpEntry: "/acp-entry.mjs",
    });

    const saved: Record<string, string | undefined> = {};
    saved.OMI_AUTH_TOKEN = process.env.OMI_AUTH_TOKEN;
    process.env.OMI_AUTH_TOKEN = "should-be-preserved";
    try {
      proc.stdin.on("data", () => {});
      await adapter.start();

      // Built-in path: spawn(nodeBin, [acpEntry], options) — options at index [2].
      const callArgs = vi.mocked(spawn).mock.calls[0] as readonly unknown[];
      const callEnv = callArgs[2] as { env: Record<string, string> };
      // The built-in ACP subprocess is Omi's own Claude Code process; it may legitimately
      // need OMI_AUTH_TOKEN (e.g. for pi-mono). Credential scrubbing is only for external commands.
      expect(callEnv.env).toHaveProperty("OMI_AUTH_TOKEN", "should-be-preserved");
      await adapter.stop();
    } finally {
      if (saved.OMI_AUTH_TOKEN === undefined) delete process.env.OMI_AUTH_TOKEN;
      else process.env.OMI_AUTH_TOKEN = saved.OMI_AUTH_TOKEN;
    }
  });

  it("includes sanitized OpenAI stderr when the ACP subprocess exits", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "acp",
      nodeBin: "/node",
      acpEntry: "/acp-entry.mjs",
    });
    proc.stdin.on("data", () => {});
    await adapter.start();

    const request = adapter.request("initialize");
    proc.stderr.write("OpenAI API error: Authorization: Bearer secret-token sk-testsecret123456\n");
    await Promise.resolve();
    proc.emit("exit", 1);

    await expect(request).rejects.toThrow(
      /OpenAI failed: OpenAI API error: Authorization: Bearer \[redacted\] sk-\[redacted\]/
    );
    await request.catch((error) => {
      expect(error).toBeInstanceOf(AdapterRuntimeError);
      expect((error as AdapterRuntimeError).failure).toMatchObject({
        code: "adapter_process_exited",
        source: "adapter_process",
        adapterId: "acp",
        provider: "openai",
        retryable: true,
        technicalMessage: "OpenAI API error: Authorization: Bearer [redacted] sk-[redacted]",
      });
    });
  });

  it("labels OpenClaw subprocess exits as OpenClaw failures even when stderr mentions OpenAI", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "openclaw",
      command: "openclaw acp",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
    });
    proc.stdin.on("data", () => {});
    await adapter.start();

    const request = adapter.request("initialize");
    proc.stderr.write("OpenAI API error: upstream unavailable\n");
    await Promise.resolve();
    proc.emit("exit", 1);

    await expect(request).rejects.toThrow("OpenClaw failed: OpenAI API error: upstream unavailable");
    await request.catch((error) => {
      expect(error).toBeInstanceOf(AdapterRuntimeError);
      expect((error as AdapterRuntimeError).failure).toMatchObject({
        code: "adapter_process_exited",
        source: "adapter_process",
        adapterId: "openclaw",
        provider: "openai",
        userMessage: "OpenClaw failed: OpenAI API error: upstream unavailable",
      });
    });
  });

  it("classifies OpenClaw invalid config exits with repair instructions", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "openclaw",
      command: "openclaw acp",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
    });
    proc.stdin.on("data", () => {});
    await adapter.start();

    const request = adapter.request("initialize");
    proc.stderr.write("OpenClaw config is invalid\n");
    proc.stderr.write("File: ~/.openclaw/openclaw.json\n");
    proc.stderr.write("- channels.telegram.streaming: invalid config: must be object\n");
    proc.stderr.write("Fix: openclaw doctor --fix\n");
    proc.stderr.write("Inspect: openclaw config validate\n");
    await Promise.resolve();
    proc.emit("exit", 1);

    await expect(request).rejects.toThrow(
      "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`."
    );
    await request.catch((error) => {
      expect(error).toBeInstanceOf(AdapterRuntimeError);
      expect((error as AdapterRuntimeError).failure).toMatchObject({
        code: "adapter_config_invalid",
        source: "adapter_process",
        adapterId: "openclaw",
        retryable: false,
        userMessage:
          "OpenClaw needs a config migration. Run `openclaw doctor --fix`, then retry. Inspect with `openclaw config validate`.",
        technicalMessage: expect.stringContaining("OpenClaw config is invalid"),
      });
    });
  });

  it("structures OpenClaw subprocess spawn errors", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "openclaw",
      command: "openclaw acp",
      envCommandName: "OMI_OPENCLAW_ADAPTER_COMMAND",
    });
    await adapter.start();

    const wroteInitialize = new Promise<void>((resolve) => {
      proc.stdin.once("data", () => resolve());
    });
    const request = adapter.request("initialize");
    await wroteInitialize;
    proc.emit("error", new Error("spawn failed: OpenAI API key sk-testsecret123456"));

    await expect(request).rejects.toThrow("OpenClaw failed: spawn failed: OpenAI API key sk-[redacted]");
    await request.catch((error) => {
      expect(error).toBeInstanceOf(AdapterRuntimeError);
      expect((error as AdapterRuntimeError).failure).toMatchObject({
        code: "adapter_process_error",
        source: "adapter_process",
        adapterId: "openclaw",
        provider: "openai",
        retryable: true,
      });
    });
  });
});

describe("AcpRuntimeAdapter bindings", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset();
    vi.useRealTimers();
  });

  it("opens ACP bindings with native resume fidelity", async () => {
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      nodeBin: "/node",
      acpEntry: "/acp-entry.mjs",
    });
    const requests: Array<any> = [];
    proc.stdin.on("data", (chunk) => {
      for (const line of chunk.toString().trim().split("\n")) {
        if (!line) continue;
        const request = JSON.parse(line);
        requests.push(request);
        if (request.method === "initialize") {
          proc.stdout.write(JSON.stringify({
            jsonrpc: "2.0",
            id: request.id,
            result: { protocolVersion: 1 },
          }) + "\n");
        } else if (request.method === "session/new") {
          proc.stdout.write(JSON.stringify({
            jsonrpc: "2.0",
            id: request.id,
            result: { sessionId: "acp-native-session" },
          }) + "\n");
        } else if (request.method === "session/set_model") {
          proc.stdout.write(JSON.stringify({
            jsonrpc: "2.0",
            id: request.id,
            result: null,
          }) + "\n");
        }
      }
    });

    await adapter.start();
    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "claude-sonnet-4-6",
    });

    expect(binding).toMatchObject({
      adapterId: "acp",
      adapterNativeSessionId: "acp-native-session",
      resumeFidelity: "native",
      cwd: "/tmp/work",
      model: "claude-sonnet-4-6",
    });
    expect(requests.map((request) => request.method)).toEqual([
      "initialize",
      "session/new",
      "session/set_model",
    ]);
  });

  it("cancels external ACP attempts that produce no recognized progress", async () => {
    vi.useFakeTimers();
    const proc = createMockProcess();
    vi.mocked(spawn).mockReturnValue(proc as any);
    const adapter = new AcpRuntimeAdapter({
      adapterId: "hermes",
      command: "/usr/local/bin/hermes acp",
      envCommandName: "OMI_HERMES_ADAPTER_COMMAND",
      noProgressTimeoutMs: 1_000,
    });
    const requests: Array<any> = [];
    proc.stdin.on("data", (chunk) => {
      for (const line of chunk.toString().trim().split("\n")) {
        if (!line) continue;
        const request = JSON.parse(line);
        requests.push(request);
        if (request.method === "initialize") {
          proc.stdout.write(JSON.stringify({
            jsonrpc: "2.0",
            id: request.id,
            result: { protocolVersion: 1 },
          }) + "\n");
        }
      }
    });

    const execution = adapter.executeAttempt({
      sessionId: "omi-session",
      ownerId: "owner-1",
      requestId: "request-1",
      clientId: "client-1",
      runId: "run-1",
      attemptId: "attempt-1",
      binding: {
        sessionId: "omi-session",
        adapterId: "hermes",
        adapterNativeSessionId: "native-hermes-session",
        resumeFidelity: "native",
        cwd: "/tmp/work",
      },
      prompt: [{ type: "text", text: "hello" }],
      mode: "ask",
      tools: [],
    }, () => {}, new AbortController().signal);

    const rejection = expect(execution).rejects.toThrow("hermes produced no progress for 1 seconds");
    await vi.advanceTimersByTimeAsync(1_200);
    await rejection;
    expect(requests.map((request) => request.method)).toContain("session/prompt");
    expect(requests).toContainEqual(expect.objectContaining({
      method: "session/cancel",
      params: { sessionId: "native-hermes-session" },
    }));
  });
});

describe("PiMonoRuntimeAdapter bindings", () => {
  it("declares no resume fidelity and requires pinned workers", async () => {
    const harness = new PiMonoAdapter({ authToken: "token" });
    vi.spyOn(harness, "createSession").mockResolvedValue("pi-session-1");
    const adapter = new PiMonoRuntimeAdapter(harness);

    const binding = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      metadata: { bindingId: "binding-1" },
    });

    expect(adapter.capabilities).toMatchObject({
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
    });
    expect(binding).toMatchObject({
      adapterId: "pi-mono",
      adapterNativeSessionId: "pi-session-1",
      resumeFidelity: "none",
    });
  });
});

describe("adapter capability matrix", () => {
  it("declares explicit support, skip, and known-limitation expectations for current and future adapters", () => {
    expect(Object.keys(ADAPTER_CAPABILITY_MATRIX).sort()).toEqual(
      [...PRODUCTION_ADAPTER_IDS, ...PLACEHOLDER_ADAPTER_IDS].sort()
    );
    expect(PRODUCTION_ADAPTER_IDS).toEqual(["acp", "pi-mono", "hermes", "openclaw", "codex"]);
    expect(PLACEHOLDER_ADAPTER_IDS).toEqual(["a2a"]);
    expect(Object.fromEntries(PRODUCTION_ADAPTER_IDS.map((adapterId) => [
      adapterId,
      ADAPTER_CAPABILITY_MATRIX[adapterId].credentialScope,
    ]))).toEqual({
      acp: "local_user",
      "pi-mono": "managed_cloud",
      hermes: "local_user",
      openclaw: "local_user",
      codex: "local_user",
    });

    expect(ADAPTER_CAPABILITY_MATRIX.acp.expectations).toMatchObject({
      nativeResume: { status: "required" },
      cancellationDispatch: { status: "required" },
      cancellationAck: { status: "known_limitation", followUpTicket: "TICKET-03-follow-up-cancel-ack" },
      pinnedWorker: { status: "unsupported" },
      modelSwitching: { status: "required" },
      artifactEmission: { status: "unsupported" },
      toolSupport: { status: "required" },
      restartOrphanSemantics: { status: "required" },
    });
    expect(ADAPTER_CAPABILITY_MATRIX["pi-mono"].expectations).toMatchObject({
      nativeResume: { status: "unsupported" },
      cancellationDispatch: { status: "required" },
      cancellationAck: { status: "known_limitation", followUpTicket: "TICKET-03-follow-up-cancel-ack" },
      pinnedWorker: { status: "required" },
      modelSwitching: { status: "required" },
      artifactEmission: { status: "unsupported" },
      toolSupport: { status: "required" },
      restartOrphanSemantics: { status: "required" },
    });
    expect(ADAPTER_CAPABILITY_MATRIX.hermes.expectations).toMatchObject({
      nativeResume: { status: "unsupported" },
      cancellationDispatch: { status: "required" },
      cancellationAck: { status: "known_limitation", followUpTicket: "TICKET-03-follow-up-cancel-ack" },
      pinnedWorker: { status: "required" },
      modelSwitching: { status: "required" },
      artifactEmission: { status: "unsupported" },
      toolSupport: { status: "required" },
      restartOrphanSemantics: { status: "required" },
    });
    expect(ADAPTER_CAPABILITY_MATRIX.openclaw.expectations).toMatchObject({
      nativeResume: { status: "required" },
      cancellationDispatch: { status: "required" },
      cancellationAck: { status: "known_limitation", followUpTicket: "TICKET-03-follow-up-cancel-ack" },
      pinnedWorker: { status: "unsupported" },
      modelSwitching: { status: "unsupported" },
      artifactEmission: { status: "unsupported" },
      toolSupport: { status: "unsupported" },
      restartOrphanSemantics: { status: "required" },
    });

    for (const adapterId of PLACEHOLDER_ADAPTER_IDS) {
      expect(ADAPTER_CAPABILITY_MATRIX[adapterId].productionAdapter).toBe(false);
      expect(PLACEHOLDER_RUNTIME_ADAPTERS[adapterId]).toMatchObject({
        adapterId,
        productionAdapter: false,
        implementationFactory: null,
      });
      expect(Object.values(ADAPTER_CAPABILITY_MATRIX[adapterId].expectations).every(
        (expectation) => expectation.status === "known_limitation" && Boolean(expectation.followUpTicket),
      )).toBe(true);
    }
  });

  it("keeps every production capability expectation documented with explicit status and reason", () => {
    for (const adapterId of PRODUCTION_ADAPTER_IDS) {
      const entry = ADAPTER_CAPABILITY_MATRIX[adapterId];

      expect(entry.productionAdapter).toBe(true);
      expect(["managed_cloud", "local_user"]).toContain(entry.credentialScope);
      expect(entry.adapterId).toBe(adapterId);
      expect(Object.keys(entry.expectations).sort()).toEqual([
        "artifactEmission",
        "cancellationAck",
        "cancellationDispatch",
        "modelSwitching",
        "nativeResume",
        "pinnedWorker",
        "restartOrphanSemantics",
        "toolSupport",
      ]);
      for (const expectation of Object.values(entry.expectations)) {
        expect(["required", "unsupported", "known_limitation"]).toContain(expectation.status);
        expect(expectation.reason.trim().length).toBeGreaterThan(0);
        if (expectation.status === "known_limitation") {
          expect(expectation.followUpTicket?.trim().length).toBeGreaterThan(0);
        } else {
          expect(expectation.followUpTicket).toBeUndefined();
        }
      }
    }
  });

  it("keeps production runtime capability summaries aligned with the matrix", () => {
    const acp = new AcpRuntimeAdapter({
      nodeBin: "/node",
      acpEntry: "/acp-entry.mjs",
    });
    const pi = new PiMonoRuntimeAdapter(new PiMonoAdapter({ authToken: "token" }));

    expect(acp.capabilities).toEqual({
      resumeFidelity: "native",
      supportsNativeResume: true,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: false,
      supportsModelSwitching: true,
      supportsArtifactEmission: false,
      supportsTools: true,
      restartBehavior: "native_bindings_survive",
    });
    expect(pi.capabilities).toEqual({
      resumeFidelity: "none",
      supportsNativeResume: false,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: true,
      supportsModelSwitching: true,
      supportsArtifactEmission: false,
      supportsTools: true,
      restartBehavior: "process_local_bindings_stale",
    });
    expect(adapterCapabilitiesFor("hermes")).toEqual({
      resumeFidelity: "none",
      supportsNativeResume: false,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: true,
      supportsModelSwitching: true,
      supportsArtifactEmission: false,
      supportsTools: true,
      restartBehavior: "process_local_bindings_stale",
    });
    expect(adapterCapabilitiesFor("openclaw")).toEqual({
      resumeFidelity: "native",
      supportsNativeResume: true,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: false,
      supportsModelSwitching: false,
      supportsArtifactEmission: false,
      supportsTools: false,
      restartBehavior: "native_bindings_survive",
    });
  });
});

describe("AdapterRegistry", () => {
  it("rejects only known placeholder adapters on the production registration path", () => {
    const registry = new AdapterRegistry();

    for (const adapterId of PLACEHOLDER_ADAPTER_IDS) {
      expect(() => registry.register(adapterId, () => fakeAdapter(adapterId))).toThrow(
        `Adapter ${adapterId} is a placeholder and cannot be registered as a production adapter without an implementation factory`
      );
      expect(registry.has(adapterId)).toBe(false);
    }

    registry.register("hermes", () => fakeAdapter("hermes"));
    registry.register("openclaw", () => fakeAdapter("openclaw"));
    expect(registry.has("hermes")).toBe(true);
    expect(registry.has("openclaw")).toBe(true);
  });

  it("continues to allow unlisted test adapters", () => {
    const registry = new AdapterRegistry();

    registry.register("fake", () => fakeAdapter("fake"), 1);

    expect(registry.has("fake")).toBe(true);
    expect(registry.capacity("fake")).toBe(1);
  });

  it("rejects fake adapters that conflate Omi sessionId and adapterNativeSessionId", async () => {
    const registry = new AdapterRegistry();
    registry.register("fake", () => fakeAdapter("fake"), 1);
    const worker = registry.get("fake").acquire();
    expect(worker).not.toBeNull();
    const adapter = worker!.adapter;

    await expect(adapter.openBinding({
      sessionId: "same-id",
      cwd: "/tmp/work",
    })).resolves.toMatchObject({
      sessionId: "same-id",
      adapterNativeSessionId: "native",
    });

    const badOpenRegistry = new AdapterRegistry();
    badOpenRegistry.register("bad-open", () => ({
      ...fakeAdapter("bad-open"),
      openBinding: async (input): Promise<OpenedBinding> => ({
        sessionId: input.sessionId,
        adapterId: "bad-open",
        adapterNativeSessionId: input.sessionId,
        resumeFidelity: "native",
        cwd: input.cwd,
      }),
    }), 1);
    await expect(badOpenRegistry.get("bad-open").acquire()!.adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
    })).rejects.toThrow("bad-open.openBinding conflated Omi sessionId omi-session with adapterNativeSessionId");

    const badResumeRegistry = new AdapterRegistry();
    badResumeRegistry.register("bad-resume", () => ({
      ...fakeAdapter("bad-resume"),
      resumeBinding: async (input): Promise<OpenedBinding> => ({
        sessionId: input.sessionId,
        adapterId: "bad-resume",
        adapterNativeSessionId: input.sessionId,
        resumeFidelity: "native",
        cwd: input.cwd,
      }),
    }), 1);
    await expect(badResumeRegistry.get("bad-resume").acquire()!.adapter.resumeBinding({
      sessionId: "omi-session",
      adapterNativeSessionId: "native-session",
      cwd: "/tmp/work",
    })).rejects.toThrow("bad-resume.resumeBinding conflated Omi sessionId omi-session with adapterNativeSessionId");

    const badExecuteRegistry = new AdapterRegistry();
    badExecuteRegistry.register("bad-execute", () => ({
      ...fakeAdapter("bad-execute"),
      executeAttempt: async (context: AdapterAttemptContext) => ({
        text: "",
        sessionId: context.sessionId,
        adapterSessionId: context.sessionId,
        terminalStatus: "succeeded" as const,
      }),
    }), 1);
    await expect(badExecuteRegistry.get("bad-execute").acquire()!.adapter.executeAttempt(
      {
        sessionId: "omi-session",
        ownerId: "owner",
        requestId: "request",
        clientId: "client",
        runId: "run",
        attemptId: "attempt",
        binding: {
          sessionId: "omi-session",
          adapterId: "bad-execute",
          adapterNativeSessionId: "native-session",
          resumeFidelity: "native",
          cwd: "/tmp/work",
        },
        prompt: [{ type: "text", text: "hello" }],
        mode: "ask",
      },
      () => {},
      new AbortController().signal,
    )).rejects.toThrow("bad-execute.executeAttempt conflated Omi sessionId omi-session with adapter native session id");

    const driftExecuteRegistry = new AdapterRegistry();
    driftExecuteRegistry.register("drift-execute", () => ({
      ...fakeAdapter("drift-execute"),
      executeAttempt: async () => ({
        text: "",
        sessionId: "other-native-session",
        adapterSessionId: "other-native-session",
        terminalStatus: "succeeded" as const,
      }),
    }), 1);
    await expect(driftExecuteRegistry.get("drift-execute").acquire()!.adapter.executeAttempt(
      {
        sessionId: "omi-session",
        ownerId: "owner",
        requestId: "request",
        clientId: "client",
        runId: "run",
        attemptId: "attempt",
        binding: {
          sessionId: "omi-session",
          adapterId: "drift-execute",
          adapterNativeSessionId: "native-session",
          resumeFidelity: "native",
          cwd: "/tmp/work",
        },
        prompt: [{ type: "text", text: "hello" }],
        mode: "ask",
      },
      () => {},
      new AbortController().signal,
    )).rejects.toThrow("drift-execute.executeAttempt returned adapterSessionId other-native-session for binding native-session");
  });
});

describe("fake runtime adapter contract fixture", () => {
  it("covers start, open, resume, stream events, terminal status, cancellation, artifacts, tools, and model switching", async () => {
    const adapter = new FakeRuntimeAdapter("contract-fake");
    await adapter.start();
    const opened = await adapter.openBinding({
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "model-a",
      systemPrompt: "system",
      mcpServers: [{ name: "server" }],
    });
    const resumed = await adapter.resumeBinding({
      ...opened,
      sessionId: "omi-session",
      cwd: "/tmp/work",
      model: "model-b",
      adapterNativeSessionId: opened.adapterNativeSessionId,
    });
    const events: string[] = [];
    adapter.nextArtifacts = [{
      kind: "json",
      role: "result",
      uri: "adapter://contract-fake/native-artifact",
      displayName: "native artifact",
      mimeType: "application/json",
      contentHash: "sha256:abc",
      sizeBytes: 12,
      metadata: { nativeArtifactId: "native-artifact" },
    }];

    const result = await adapter.executeAttempt(
      {
        sessionId: "omi-session",
        ownerId: "owner",
        requestId: "request",
        clientId: "client",
        runId: "omi-run",
        attemptId: "omi-attempt",
        binding: resumed,
        prompt: [{ type: "text", text: "hello" }],
        mode: "act",
        model: "model-b",
        tools: [{ name: "omi_tool", description: "tool", inputSchema: { type: "object" } }],
      },
      (event) => events.push(event.type),
      new AbortController().signal,
    );
    const cancel = await adapter.cancelAttempt({
      sessionId: "omi-session",
      runId: "omi-run",
      attemptId: "omi-attempt",
      binding: resumed,
    });
    await adapter.stop();

    expect(adapter.started).toBe(1);
    expect(adapter.stopped).toBe(1);
    expect(opened.sessionId).toBe("omi-session");
    expect(opened.adapterNativeSessionId).toBe("native-1");
    expect(opened.adapterNativeSessionId).not.toBe(opened.sessionId);
    expect(resumed.sessionId).toBe("omi-session");
    expect(resumed.adapterNativeSessionId).toBe("native-1");
    expect(resumed.adapterNativeSessionId).not.toBe(resumed.sessionId);
    expect(adapter.resumed[0].adapterNativeSessionId).toBe("native-1");
    expect(adapter.executed[0]).toMatchObject({
      sessionId: "omi-session",
      runId: "omi-run",
      attemptId: "omi-attempt",
      model: "model-b",
    });
    expect(adapter.executed[0].binding.adapterNativeSessionId).toBe("native-1");
    expect(adapter.executed[0].tools?.map((tool) => tool.name)).toEqual(["omi_tool"]);
    expect(events).toEqual(["text_delta"]);
    expect(result).toMatchObject({
      terminalStatus: "succeeded",
      adapterSessionId: "native-1",
      artifacts: [expect.objectContaining({ uri: "adapter://contract-fake/native-artifact" })],
    });
    expect("sessionId" in result).toBe(false);
    expect(result.adapterSessionId).toBe("native-1");
    expect(result.adapterSessionId).toBe(adapter.executed[0].binding.adapterNativeSessionId);
    expect(cancel).toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    });
  });
});

describe("AdapterWorkerPool", () => {
  it("defaults to eight workers and honors OMI_AGENT_MAX_WORKERS", () => {
    expect(configuredMaxWorkers({} as NodeJS.ProcessEnv)).toBe(8);
    expect(configuredMaxWorkers({ OMI_AGENT_MAX_WORKERS: "3" } as NodeJS.ProcessEnv)).toBe(3);
    expect(configuredMaxWorkers({ OMI_AGENT_MAX_WORKERS: "0" } as NodeJS.ProcessEnv)).toBe(8);
  });

  it("gives pi-mono enough workers for a parent turn to spawn a visible child agent", () => {
    expect(configuredPiMonoMaxWorkers({} as NodeJS.ProcessEnv)).toBe(2);
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: "4" } as NodeJS.ProcessEnv)).toBe(4);
    expect(configuredPiMonoMaxWorkers({ OMI_PI_MONO_MAX_WORKERS: "0" } as NodeJS.ProcessEnv)).toBe(2);
  });

  it("caps worker creation", () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter(), 2);
    const first = pool.acquire();
    const second = pool.acquire();

    expect(first).not.toBeNull();
    expect(second).toBe(first);

    void first?.runExclusive("attempt-1", undefined, async () => new Promise(() => {}));
    const concurrent = pool.acquire();
    expect(concurrent?.workerId).toBe("worker-2");
    void concurrent?.runExclusive("attempt-2", undefined, async () => new Promise(() => {}));

    expect(pool.acquire()).toBeNull();
    expect(pool.size).toBe(2);
  });

  it("enforces one active attempt per worker", async () => {
    const pool = new AdapterWorkerPool(() => fakeAdapter(), 1);
    const worker = pool.acquire();
    expect(worker).not.toBeNull();

    let release!: () => void;
    const active = worker!.runExclusive(
      "attempt-1",
      undefined,
      async () => new Promise<void>((resolve) => {
        release = resolve;
      })
    );

    await expect(worker!.runExclusive("attempt-2", undefined, async () => {})).rejects.toThrow(
      "already has active attempt attempt-1"
    );

    release();
    await active;
  });

  it("keeps idle pi-mono-style workers pinned to their live bindings", () => {
    const pinnedAdapter = {
      ...fakeAdapter("pi-mono"),
      capabilities: {
        resumeFidelity: "none" as const,
        supportsNativeResume: false,
        supportsCancellation: true,
        acknowledgesCancellation: false,
        requiresPinnedWorker: true,
        supportsModelSwitching: true,
        supportsArtifactEmission: false,
        supportsTools: true,
        restartBehavior: "process_local_bindings_stale" as const,
      },
    };
    const pool = new AdapterWorkerPool(() => pinnedAdapter, 2);
    const first = pool.acquire({
      bindingId: "binding-1",
      sessionId: "s1",
      adapterId: "pi-mono",
      adapterNativeSessionId: "pi-1",
      resumeFidelity: "none",
      cwd: "/tmp",
    });
    const second = pool.acquire({
      bindingId: "binding-2",
      sessionId: "s2",
      adapterId: "pi-mono",
      adapterNativeSessionId: "pi-2",
      resumeFidelity: "none",
      cwd: "/tmp",
    });

    expect(first?.workerId).toBe("worker-1");
    expect(second?.workerId).toBe("worker-2");
    expect(pool.size).toBe(2);
  });
});

describe("OneShotCliRuntimeAdapter prompt serialization", () => {
  it("flattens PromptBlock[] to joined text instead of JSON-stringifying", async () => {
    vi.mocked(spawn).mockReset();
    vi.mocked(spawn).mockImplementation((() => {
      const proc = Object.assign(new EventEmitter(), {
        stdin: new PassThrough(),
        stdout: new PassThrough(),
        stderr: new PassThrough(),
        kill: vi.fn(),
        pid: 12345,
      });
      // Resolve the run-prompt promise on next tick
      process.nextTick(() => proc.emit("exit", 0));
      return proc as any;
    }) as any);

    const { OneShotCliRuntimeAdapter } = await import("../src/adapters/one-shot-cli.js");
    const adapter = new OneShotCliRuntimeAdapter({
      adapterId: "openclaw",
      envCommandName: "OPENCLAW_COMMAND",
      promptFlag: "--message",
    });
    process.env.OPENCLAW_COMMAND = "openclaw";

    try {
      await adapter.executeAttempt(
        {
          sessionId: "omi-session",
          ownerId: "owner",
          requestId: "request",
          clientId: "client",
          runId: "run",
          attemptId: "attempt",
          binding: {
            sessionId: "omi-session",
            adapterId: "openclaw",
            adapterNativeSessionId: "openclaw:omi-session",
            resumeFidelity: "none",
            cwd: "/tmp",
          },
          prompt: [
            { type: "text", text: "Hello" },
            { type: "text", text: "world" },
          ],
          mode: "ask",
        } as any,
        () => {},
        new AbortController().signal,
      );

      const spawnArg = vi.mocked(spawn).mock.calls[0][0] as string;
      // The prompt text should be joined text, NOT a JSON array string
      expect(spawnArg).toContain("'Hello\nworld'");
      expect(spawnArg).not.toContain('[{"type":"text"');
    } finally {
      delete process.env.OPENCLAW_COMMAND;
    }
  });
});
