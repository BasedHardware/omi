import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, FakeRuntimeAdapter, waitUntil } from "./kernel-fakes.js";
import type { OpenedBinding, OpenBindingInput } from "../src/adapters/interface.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AdapterRuntimeError } from "../src/runtime/failures.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import {
  configuredRunTimeoutMs,
  DEFAULT_RUN_TIMEOUT_MS,
} from "../src/runtime/kernel-support.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const createdDirs: string[] = [];

/**
 * A fake adapter whose binding resolution never settles, modelling an ACP
 * `session/new` request that never responds.
 */
class HangingBindAdapter extends FakeRuntimeAdapter {
  bindAttempts = 0;

  override async openBinding(
    _input: Parameters<FakeRuntimeAdapter["openBinding"]>[0],
  ): ReturnType<FakeRuntimeAdapter["openBinding"]> {
    this.bindAttempts += 1;
    return new Promise(() => {});
  }
}

/**
 * A fake adapter whose `stop()` never returns, modelling an ACP subprocess
 * that ignores SIGTERM.
 */
class HangingStopAdapter extends FakeRuntimeAdapter {
  stopStarted = 0;

  override async stop(): Promise<void> {
    this.stopStarted += 1;
    await new Promise(() => {});
  }
}

/**
 * A fake adapter whose `session/new` answers only when the test releases it,
 * modelling a reply that lands after the run deadline.
 */
class LateBindAdapter extends FakeRuntimeAdapter {
  bindAttempts = 0;
  private resolveBind!: (binding: OpenedBinding) => void;
  private readonly bindGate = new Promise<OpenedBinding>((resolve) => {
    this.resolveBind = resolve;
  });

  override async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    this.bindAttempts += 1;
    this.opened.push(input);
    return this.bindGate;
  }

  completeBind(): void {
    this.resolveBind({
      sessionId: "late-session",
      adapterId: this.adapterId,
      adapterNativeSessionId: "native-late",
      resumeFidelity: "native",
      cwd: "/tmp/work",
    });
  }
}

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("AgentRuntimeKernel run deadline", () => {
  it("marks a hung run timed_out and never reuses its worker for a follow-up", async () => {
    const adapters: FakeRuntimeAdapter[] = [];
    const { store, kernel } = createKernelHarness(
      newDatabasePath(),
      "fake",
      1,
      undefined,
      undefined,
      () => {
        const adapter = new FakeRuntimeAdapter("fake");
        adapters.push(adapter);
        return adapter;
      },
    );
    const abandoned = adapters[0];
    abandoned.deferResult();

    const running = kernel.executeRun({ ...baseRunInput, timeoutMs: 500 });
    await waitUntil(() => abandoned.executed.length === 1);
    const result = await running;

    expect(result.run.status).toBe("timed_out");
    expect(result.attempt.status).toBe("timed_out");
    expect(result.run.errorCode).toBe("run_timed_out");
    expect(result.run.completedAtMs).toEqual(expect.any(Number));
    expect(result.terminalStatus).toBe("failed");

    const eventTypes = store
      .allRows("SELECT type FROM events WHERE run_id = ? ORDER BY event_seq", [result.run.runId])
      .map((row) => String(row.type));
    expect(eventTypes).toContain("run.timed_out");
    expect(eventTypes).toContain("attempt.timed_out");
    expect(eventTypes).toContain("worker.recycled");

    // The abandoned execution is still pending on purpose: the pool must stop
    // and remove that worker, never hand it to a follow-up while the old
    // prompt is still live.
    expect(abandoned.stopped).toBeGreaterThan(0);
    const followUp = await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-after-timeout",
      timeoutMs: 0,
    });
    expect(followUp.run.status).toBe("succeeded");
    expect(adapters.length).toBeGreaterThanOrEqual(2);
    expect(adapters[1].executed).toHaveLength(1);
    expect(abandoned.executed).toHaveLength(1);
    store.close();
  });

  it("applies the run deadline to binding resolution that never settles", async () => {
    const hang = new HangingBindAdapter("fake");
    const { store, kernel } = createKernelHarness(
      newDatabasePath(),
      "fake",
      1,
      undefined,
      undefined,
      () => hang,
    );

    const result = await kernel.executeRun({ ...baseRunInput, timeoutMs: 300 });

    expect(hang.bindAttempts).toBe(1);
    expect(result.run.status).toBe("timed_out");
    expect(result.run.errorCode).toBe("run_timed_out");
    expect(result.attempt.status).toBe("timed_out");
    expect(result.run.completedAtMs).toEqual(expect.any(Number));
    store.close();
  });

  it("terminalizes the run before a hung adapter stop returns, and bounds the stop wait", async () => {
    const previousStopTimeout = process.env.OMI_AGENT_WORKER_STOP_TIMEOUT_MS;
    process.env.OMI_AGENT_WORKER_STOP_TIMEOUT_MS = "150";
    try {
      const adapter = new HangingStopAdapter("fake");
      const { store, kernel } = createKernelHarness(
        newDatabasePath(),
        "fake",
        1,
        undefined,
        undefined,
        () => adapter,
      );
      adapter.deferResult();

      const running = kernel.executeRun({ ...baseRunInput, timeoutMs: 200 });
      await waitUntil(() => adapter.executed.length === 1);
      await waitUntil(() => adapter.stopStarted === 1);

      // `stop()` is still pending here: the run must already be terminal so
      // its tool authority is revoked instead of waiting on subprocess exit.
      expect(store.getRow("SELECT status FROM runs").status).toBe("timed_out");
      expect(store.getRow("SELECT status FROM run_attempts").status).toBe("timed_out");

      // The bounded stop wait lets the caller finish even though the adapter
      // never exits; the worker stays quarantined (removed from the pool).
      const result = await running;
      expect(result.run.status).toBe("timed_out");
      expect(result.run.errorCode).toBe("run_timed_out");
      store.close();
    } finally {
      if (previousStopTimeout === undefined) {
        delete process.env.OMI_AGENT_WORKER_STOP_TIMEOUT_MS;
      } else {
        process.env.OMI_AGENT_WORKER_STOP_TIMEOUT_MS = previousStopTimeout;
      }
    }
  });

  it("discards a binding that resolves after the run deadline", async () => {
    const adapter = new LateBindAdapter("fake");
    const { store, kernel } = createKernelHarness(
      newDatabasePath(),
      "fake",
      1,
      undefined,
      undefined,
      () => adapter,
    );

    const result = await kernel.executeRun({ ...baseRunInput, timeoutMs: 150 });
    expect(result.run.status).toBe("timed_out");
    expect(adapter.bindAttempts).toBe(1);

    // `session/new` answers only now, after the run is already terminal. The
    // late result must not be published as an active binding.
    adapter.completeBind();
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(store.allRows("SELECT binding_id FROM adapter_bindings")).toHaveLength(0);
    store.close();
  });

  it("applies the kernel default deadline when the run does not override it", async () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const adapter = new FakeRuntimeAdapter("fake");
    const registry = new AdapterRegistry();
    registry.register("fake", () => adapter, 1);
    const kernel = new AgentRuntimeKernel({
      store,
      registry,
      runTimeoutMs: 50,
      toolCapabilityProfileForSession: (sessionId) => {
        const profile = readSessionExecutionProfile(store, sessionId);
        const adapterId = ["pi-mono", "acp", "hermes", "openclaw"].includes(profile.adapterId)
          ? profile.adapterId
          : "acp";
        return { ...profile, adapterId };
      },
    });
    adapter.deferResult();

    const result = await kernel.executeRun(baseRunInput);

    expect(result.run.status).toBe("timed_out");
    expect(result.run.errorCode).toBe("run_timed_out");
    store.close();
  });

  it("does not time out a run when the deadline is disabled", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 1);
    adapter.deferResult();

    const running = kernel.executeRun({ ...baseRunInput, timeoutMs: 0 });
    await waitUntil(() => adapter.executed.length === 1);
    await new Promise((resolve) => setTimeout(resolve, 100));

    expect(store.getRow("SELECT status FROM runs").status).toBe("running");

    adapter.resolveDeferred({
      terminalStatus: "succeeded",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
    });
    const result = await running;
    expect(result.run.status).toBe("succeeded");
    store.close();
  });

  it("does not retry a timed-out run even when retries are available", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 1);
    adapter.deferResult();

    const result = await kernel.executeRun({ ...baseRunInput, timeoutMs: 150, maxAttempts: 3 });

    expect(result.run.status).toBe("timed_out");
    // The deadline may expire before dispatch under load; either way the run
    // gets exactly one attempt and is never retried.
    expect(adapter.executed.length).toBeLessThanOrEqual(1);
    expect(store.allRows("SELECT attempt_no FROM run_attempts WHERE run_id = ?", [result.run.runId]))
      .toHaveLength(1);
    store.close();
  });

  it("marks a run timed_out when the adapter reports its own prompt timeout", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "fake", 1);
    adapter.failNextExecutionError = new AdapterRuntimeError({
      code: "adapter_prompt_timeout",
      failureCode: "timeout",
      source: "adapter_execution",
      adapterId: "fake",
      retryable: false,
      userMessage: "The agent prompt exceeded its 600-second deadline and was stopped.",
    });

    const result = await kernel.executeRun({ ...baseRunInput, timeoutMs: 0, maxAttempts: 3 });

    expect(result.run.status).toBe("timed_out");
    expect(result.run.errorCode).toBe("adapter_prompt_timeout");
    expect(store.allRows("SELECT attempt_no FROM run_attempts WHERE run_id = ?", [result.run.runId]))
      .toHaveLength(1);
    store.close();
  });
});

describe("configuredRunTimeoutMs", () => {
  it("defaults, parses, and disables via OMI_AGENT_RUN_TIMEOUT_MS", () => {
    expect(configuredRunTimeoutMs({} as NodeJS.ProcessEnv)).toBe(DEFAULT_RUN_TIMEOUT_MS);
    expect(configuredRunTimeoutMs({ OMI_AGENT_RUN_TIMEOUT_MS: "1500" } as NodeJS.ProcessEnv)).toBe(1500);
    expect(configuredRunTimeoutMs({ OMI_AGENT_RUN_TIMEOUT_MS: "0" } as NodeJS.ProcessEnv)).toBe(0);
    expect(configuredRunTimeoutMs({ OMI_AGENT_RUN_TIMEOUT_MS: "nope" } as NodeJS.ProcessEnv))
      .toBe(DEFAULT_RUN_TIMEOUT_MS);
    expect(configuredRunTimeoutMs({ OMI_AGENT_RUN_TIMEOUT_MS: "-5" } as NodeJS.ProcessEnv))
      .toBe(DEFAULT_RUN_TIMEOUT_MS);
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-run-timeout-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
