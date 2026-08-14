import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, FakeRuntimeAdapter } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("AgentRuntimeKernel adapter binding resolution", () => {
  it("resumes an active binding on a second run for the same surface", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({ ...baseRunInput, requestId: "request-1" });
    const result = await kernel.executeRun({ ...baseRunInput, requestId: "request-2" });

    expect(result.adapterSessionId).toBe("native-1");
    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    expect(store.getRow("SELECT adapter_native_session_id, binding_generation, status FROM adapter_bindings")).toMatchObject({
      adapter_native_session_id: "native-1",
      binding_generation: 1,
      status: "active",
    });
    store.close();
  });

  it("keeps a warm binding when only the dynamic context identity advances", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-cache-1",
      systemPromptCacheIdentity: "sha256:stable-policy",
      dynamicContextIdentity: "sha256:turn-1",
      contextPlanId: "sha256:plan-1",
    });
    await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-cache-2",
      systemPromptCacheIdentity: "sha256:stable-policy",
      dynamicContextIdentity: "sha256:turn-2",
      contextPlanId: "sha256:plan-2",
    });

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    expect(store.allRows("SELECT payload_json FROM events WHERE type = 'binding.resumed'")[0]?.payload_json)
      .toContain("dynamicContextIdentity");
    store.close();
  });

  it("treats null cwd bindings as compatible with the default cwd", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    const runInput = {
      ...baseRunInput,
      cwd: undefined,
    };

    await kernel.executeRun(runInput);
    store.execute("UPDATE adapter_bindings SET cwd = NULL");

    const result = await kernel.executeRun({
      ...runInput,
      requestId: "request-2",
    });

    expect(result.adapterSessionId).toBe("native-1");
    expect(adapter.opened).toHaveLength(1);
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.resumed[0]?.cwd).toBe(process.cwd());
    expect(store.allRows("SELECT binding_generation, adapter_native_session_id, status FROM adapter_bindings ORDER BY binding_generation")).toEqual([
      expect.objectContaining({ binding_generation: 1, adapter_native_session_id: "native-1", status: "active" }),
    ]);
    store.close();
  });

  it("marks stale native bindings and retries under the same run with a new generation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({ ...baseRunInput, requestId: "request-1" });
    adapter.failNextResume = true;

    const result = await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-2",
      maxAttempts: 2,
    });

    expect(result.terminalStatus).toBe("succeeded");
    expect(result.run.runId).toBe(store.getRow("SELECT run_id FROM runs ORDER BY created_at_ms DESC LIMIT 1").run_id);
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.opened).toHaveLength(2);
    expect(store.allRows(
      "SELECT attempt_no, status, retry_reason FROM run_attempts WHERE run_id = ? ORDER BY attempt_no",
      [result.run.runId],
    )).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "failed" }),
      expect.objectContaining({ attempt_no: 2, status: "succeeded", retry_reason: "stale_binding" }),
    ]);
    expect(store.allRows("SELECT binding_generation, adapter_native_session_id, status FROM adapter_bindings ORDER BY binding_generation")).toEqual([
      expect.objectContaining({ binding_generation: 1, adapter_native_session_id: "native-1", status: "stale" }),
      expect.objectContaining({ binding_generation: 2, adapter_native_session_id: "native-2", status: "active" }),
    ]);
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toContain("binding.stale");
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toContain("binding.replaced");
    store.close();
  });

  it("recycles a poisoned pi-mono worker so the next send succeeds in the same daemon", async () => {
    const adapters: FakeRuntimeAdapter[] = [];
    let genericRecoveryCalls = 0;
    const makeAdapter = () => {
      const adapter = new FakeRuntimeAdapter("pi-mono");
      Object.assign(adapter.capabilities, {
        resumeFidelity: "none",
        supportsNativeResume: false,
        requiresPinnedWorker: true,
        restartBehavior: "process_local_bindings_stale",
      });
      adapters.push(adapter);
      return adapter;
    };
    const { store, adapter, kernel } = createKernelHarness(
      newDatabasePath(),
      "pi-mono",
      1,
      undefined,
      () => ({
        maxAttempts: 2,
        recoverAfterError: async () => {
          genericRecoveryCalls += 1;
          return true;
        },
      }),
      makeAdapter,
    );
    adapter.failNextExecutionError = new Error("poisoned local adapter state");

    const failed = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-poisoned",
    });
    expect(failed.terminalStatus).toBe("failed");
    expect(adapters).toHaveLength(1);
    expect(adapter.executed).toHaveLength(1);
    expect(genericRecoveryCalls).toBe(0);
    expect(adapter.stopped).toBe(1);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("stale");
    expect(JSON.parse(failed.run.resultJson!)).toMatchObject({
      failure: {
        code: "adapter_execution_failed",
        recoveryAction: "worker_recycled",
        recoveryOutcome: "recovered",
        retryDisposition: "next_send",
        retryable: true,
      },
    });

    const recovered = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-after-recycle",
    });
    expect(recovered.terminalStatus).toBe("succeeded");
    expect(adapters).toHaveLength(2);
    expect(adapters[1]?.executed).toHaveLength(1);
    expect(store.allRows("SELECT status FROM adapter_bindings ORDER BY binding_generation"))
      .toEqual([
        expect.objectContaining({ status: "closed" }),
        expect.objectContaining({ status: "active" }),
      ]);
    expect(store.allRows("SELECT type FROM events WHERE type = 'worker.recycled'")).toHaveLength(1);
    expect(JSON.parse(store.getRow(
      "SELECT payload_json FROM events WHERE type = 'worker.recycled'",
    ).payload_json)).toMatchObject({
      recoveryOutcome: "recovered",
      bindingStalePersisted: true,
    });
    store.close();
  });

  it("recycles the pi-mono worker after HTTP 402 without inviting a retry", async () => {
    const makeAdapter = () => {
      const adapter = new FakeRuntimeAdapter("pi-mono");
      Object.assign(adapter.capabilities, {
        resumeFidelity: "none",
        supportsNativeResume: false,
        requiresPinnedWorker: true,
        restartBehavior: "process_local_bindings_stale",
      });
      return adapter;
    };
    const { store, adapter, kernel } = createKernelHarness(
      newDatabasePath(),
      "pi-mono",
      1,
      undefined,
      undefined,
      makeAdapter,
    );
    adapter.failNextExecutionError = new Error("HTTP 402 status code (no body)");

    const failed = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-billing",
    });
    expect(failed.terminalStatus).toBe("failed");
    expect(adapter.stopped).toBe(1);
    expect(JSON.parse(failed.run.resultJson!)).toMatchObject({
      failure: {
        code: "adapter_execution_failed",
        failureCode: "quota_exceeded",
        retryable: false,
        recoveryAction: "worker_recycled",
        technicalMessage: "HTTP 402 status code (no body)",
      },
    });
    expect(JSON.parse(failed.run.resultJson!).failure.userMessage).not.toContain("Send your message again");
    store.close();
  });

  it("unwraps a stale-binding execution failure and retries on a fresh pi-mono worker", async () => {
    const adapters: FakeRuntimeAdapter[] = [];
    const makeAdapter = () => {
      const adapter = new FakeRuntimeAdapter("pi-mono");
      Object.assign(adapter.capabilities, {
        resumeFidelity: "none",
        supportsNativeResume: false,
        requiresPinnedWorker: true,
        restartBehavior: "process_local_bindings_stale",
      });
      adapters.push(adapter);
      return adapter;
    };
    const { store, adapter, kernel } = createKernelHarness(
      newDatabasePath(), "pi-mono", 1, undefined, undefined, makeAdapter,
    );
    adapter.failNextExecutionAsStale = true;

    const result = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-stale-during-execution",
      maxAttempts: 2,
    });

    expect(result.terminalStatus).toBe("succeeded");
    expect(adapters).toHaveLength(2);
    expect(adapter.stopped).toBe(1);
    expect(store.allRows("SELECT payload_json FROM events WHERE type = 'binding.stale'")
      .map((row) => JSON.parse(row.payload_json as string))
      .filter((payload) => payload.reason === "pinned_worker_recycled_after_execution_error"))
      .toHaveLength(1);
    expect(store.allRows(
      "SELECT status FROM adapter_bindings ORDER BY binding_generation",
    )).toEqual([
      expect.objectContaining({ status: "closed" }),
      expect.objectContaining({ status: "active" }),
    ]);
    store.close();
  });

  it("does not recycle a pi-mono worker when cancellation rejects in-flight execution", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });
    adapter.deferResult();

    const execution = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-cancelled-in-flight",
    });
    while (adapter.executed.length === 0) {
      await new Promise<void>((resolve) => setImmediate(resolve));
    }
    const runId = store.getRow("SELECT run_id FROM runs ORDER BY created_at_ms DESC LIMIT 1").run_id as string;
    await kernel.cancelRun(runId);
    adapter.rejectDeferred(new Error("adapter abort rejection"));

    const result = await execution;
    expect(result.terminalStatus).toBe("cancelled");
    expect(adapter.stopped).toBe(0);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("active");
    expect(store.allRows("SELECT type FROM events WHERE type = 'worker.recycled'")).toHaveLength(0);
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
