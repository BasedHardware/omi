import { PassThrough } from "node:stream";
import { EventEmitter } from "node:events";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { spawn } from "child_process";
import { AcpRuntimeAdapter } from "../src/adapters/acp.js";
import {
  PiMonoAdapter,
  PiMonoRuntimeAdapter,
} from "../src/adapters/pi-mono.js";
import type {
  AdapterAttemptContext,
  RuntimeAdapter,
} from "../src/adapters/interface.js";
import { AdapterWorkerPool, configuredMaxWorkers } from "../src/runtime/worker-pool.js";

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
      text: "",
      sessionId: context.binding.adapterNativeSessionId,
      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
    }),
    cancelAttempt: async () => ({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    }),
  };
}

describe("AcpRuntimeAdapter bindings", () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset();
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
        if (request.method === "session/new") {
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
      "session/new",
      "session/set_model",
    ]);
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

describe("AdapterWorkerPool", () => {
  it("defaults to eight workers and honors OMI_AGENT_MAX_WORKERS", () => {
    expect(configuredMaxWorkers({} as NodeJS.ProcessEnv)).toBe(8);
    expect(configuredMaxWorkers({ OMI_AGENT_MAX_WORKERS: "3" } as NodeJS.ProcessEnv)).toBe(3);
    expect(configuredMaxWorkers({ OMI_AGENT_MAX_WORKERS: "0" } as NodeJS.ProcessEnv)).toBe(8);
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

  it("reuses idle pi-mono-style workers for later bindings", () => {
    const pinnedAdapter = {
      ...fakeAdapter("pi-mono"),
      capabilities: {
        resumeFidelity: "none" as const,
        supportsNativeResume: false,
        supportsCancellation: true,
        requiresPinnedWorker: true,
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
    expect(second?.workerId).toBe("worker-1");
    expect(pool.size).toBe(1);
  });
});
