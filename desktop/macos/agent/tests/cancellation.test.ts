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
      adapterSessionId: adapter.executed[0].binding.adapterNativeSessionId,
      sessionId: adapter.executed[0].binding.adapterNativeSessionId,
      terminalStatus: "cancelled",
    });
    const result = await running;

    expect(result.terminalStatus).toBe("cancelled");
    expect(store.getRow("SELECT status, final_text FROM runs WHERE run_id = ?", [runId])).toMatchObject({
      status: "cancelled",
      final_text: "partial",
    });

    adapter.emitLate(attemptId, {
      type: "text_delta",
      text: "late after cancel",
      sessionId: result.adapterSessionId ?? "native",
    });
    expect(store.allRows("SELECT payload_json FROM events WHERE type = 'adapter.text_delta'")).toHaveLength(1);
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toEqual([
      "run.created",
      "attempt.created",
      "binding.created",
      "attempt.started",
      "run.running",
      "adapter.text_delta",
      "run.cancellation_requested",
      "run.cancelling",
      "attempt.cancel_dispatch",
      "run.cancel_ack",
      "attempt.cancelled",
      "run.cancelled",
    ]);
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
