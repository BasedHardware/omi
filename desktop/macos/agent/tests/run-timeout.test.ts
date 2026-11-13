import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, FakeRuntimeAdapter, waitUntil } from "./kernel-fakes.js";
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
