import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("AgentRuntimeKernel run and attempt lifecycle", () => {
  it("creates one run per accepted query and one attempt per adapter execution", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    const first = await kernel.executeRun(baseRunInput);
    const second = await kernel.executeRun({
      ...baseRunInput,
      requestId: "request-2",
      prompt: "follow up",
    });

    expect(first.session.sessionId).toBe(second.session.sessionId);
    expect(first.run.runId).not.toBe(second.run.runId);
    expect(adapter.executed).toHaveLength(2);
    expect(store.allRows("SELECT run_id, status FROM runs ORDER BY created_at_ms")).toHaveLength(2);
    expect(store.allRows("SELECT attempt_id, run_id, attempt_no, status FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ run_id: first.run.runId, attempt_no: 1, status: "succeeded" }),
      expect.objectContaining({ run_id: second.run.runId, attempt_no: 1, status: "succeeded" }),
    ]);
    expect(store.allRows("SELECT * FROM run_attempts WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')")).toHaveLength(0);
    store.close();
  });

  it("does not allow another non-terminal attempt for the same run", () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "fake",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "ask",
    });
    store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "worker",
    });

    expect(() => (kernel as any).createAttempt({
      runId: run.runId,
      attemptNo: 2,
      adapterId: "fake",
      retryReason: null,
      resumeFromAttemptId: null,
    })).toThrow(/already has active attempt/);
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
