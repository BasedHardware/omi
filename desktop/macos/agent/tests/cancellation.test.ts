import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, waitUntil } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("AgentRuntimeKernel cancellation", () => {
  it("persists cancellation before dispatch and waits for adapter terminal reconciliation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const running = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);

    const runId = adapter.executed[0].runId;
    const attemptId = adapter.executed[0].attemptId;
    const ack = await kernel.cancelRun(runId);

    expect(ack).toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
      runId,
      attemptId,
    });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [runId]).status).toBe("cancelling");
    expect(store.getRow("SELECT status, cancellation_requested_at_ms, cancellation_dispatched_at_ms FROM run_attempts WHERE attempt_id = ?", [attemptId])).toMatchObject({
      status: "cancelling",
      cancellation_requested_at_ms: expect.any(Number),
      cancellation_dispatched_at_ms: expect.any(Number),
    });
    expect(adapter.cancelled).toHaveLength(1);

    adapter.resolveDeferred({
      text: "partial",
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,      terminalStatus: "cancelled",
    });
    const result = await running;

    expect(result.terminalStatus).toBe("cancelled");
    expect(store.getRow("SELECT status, final_text FROM runs WHERE run_id = ?", [runId])).toMatchObject({
      status: "cancelled",
      final_text: "partial",
    });

    adapter.emitLate(attemptId, {
      type: "text_delta",
      text: "late after cancel",    });
    expect(store.allRows("SELECT payload_json FROM events WHERE type = 'message.delta'")).toHaveLength(1);
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toEqual([
      "session.created",
      "run.queued",
      "session.updated",
      "run.starting",
      "attempt.created",
      "binding.created",
      "attempt.started",
      "run.running",
      "message.delta",
      "run.cancellation_requested",
      "run.cancelling",
      "attempt.cancel_dispatch",
      "attempt.cancelled",
      "run.cancelled",
    ]);
    store.close();
  });

  it("does not mutate terminal runs when cancellation is requested later", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const result = await kernel.executeRun(baseRunInput);

    const ack = await kernel.cancelRun(result.run.runId);

    expect(ack).toMatchObject({
      accepted: false,
      dispatchAttempted: false,
      adapterAcknowledged: false,
      runId: result.run.runId,
    });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [result.run.runId]).status).toBe("succeeded");
    expect(store.allRows("SELECT type FROM events WHERE type = 'run.cancellation_requested'")).toHaveLength(0);
    store.close();
  });

  it("cascades cancellation to in-flight delegated children", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const runningParent = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);
    const parentRunId = adapter.executed[0].runId;

    const spawned = await kernel.delegateAgent({
      mode: "spawn",
      parentRunId,
      objective: "child objective",
      clientId: "client",
      requestId: "request-child",
    });
    await waitUntil(() => adapter.executed.length === 2);
    const childRunId = spawned.childRun.runId;

    const ack = await kernel.cancelRun(parentRunId);

    expect(ack.accepted).toBe(true);
    expect(adapter.cancelled).toHaveLength(2);
    expect(adapter.cancelled.map((context) => context.runId)).toContain(childRunId);
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [childRunId]).status).toBe("cancelling");

    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await runningParent;
    await waitUntil(
      () => store.getRow("SELECT status FROM runs WHERE run_id = ?", [childRunId]).status === "cancelled",
    );
    await waitUntil(
      () =>
        store.getRow("SELECT status FROM delegations WHERE child_run_id = ?", [childRunId]).status === "cancelled",
    );
    // The delegation settles exactly once, via executeDelegationAsync — not the cascade.
    expect(store.allRows("SELECT type FROM events WHERE type = 'delegation.completed'")).toHaveLength(1);
    store.close();
  });

  it("leaves already-terminal delegated children untouched", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferOnlyPromptIncludes = "hello";
    adapter.deferResult();
    const runningParent = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);
    const parentRunId = adapter.executed[0].runId;

    const completed = await kernel.delegateAgent({
      mode: "call",
      parentRunId,
      objective: "finished child objective",
      clientId: "client",
      requestId: "request-child-call",
    });
    const childRunId = completed.childRun.runId;
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [childRunId]).status).toBe("succeeded");

    const ack = await kernel.cancelRun(parentRunId);

    expect(ack.accepted).toBe(true);
    expect(adapter.cancelled).toHaveLength(1);
    expect(adapter.cancelled[0].runId).toBe(parentRunId);
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [childRunId]).status).toBe("succeeded");
    expect(store.allRows("SELECT type FROM events WHERE type = 'delegation.completed'")).toHaveLength(1);

    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await runningParent;
    store.close();
  });

  it("does not cascade to background agents spawned outside a delegation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferResult();
    const runningParent = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);
    const parentRunId = adapter.executed[0].runId;

    const background = await kernel.spawnBackgroundAgent({
      ownerId: "owner",
      clientId: "client",
      requestId: "request-background",
      prompt: "independent background work",
      trustedUserSpawn: true,
      adapterId: "fake",
      defaultAdapterId: "fake",
    });
    await waitUntil(() => adapter.executed.length === 2);
    const backgroundRunId = background.run.runId;

    const ack = await kernel.cancelRun(parentRunId);

    // Background agents are user-visible floating-bar work designed to
    // outlive the parent turn — the cascade must not touch them.
    expect(ack.accepted).toBe(true);
    expect(adapter.cancelled).toHaveLength(1);
    expect(adapter.cancelled[0].runId).toBe(parentRunId);
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [backgroundRunId]).status).toBe("running");

    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await runningParent;
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
