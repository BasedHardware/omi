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
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
