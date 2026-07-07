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
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
