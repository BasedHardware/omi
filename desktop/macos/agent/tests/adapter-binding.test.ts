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
  it("adopts a legacy native session as generation 1", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    const result = await kernel.executeRun({
      ...baseRunInput,
      legacyAdapterSessionId: "legacy-native",
    });

    expect(result.adapterSessionId).toBe("legacy-native");
    expect(adapter.opened).toHaveLength(0);
    expect(adapter.resumed).toHaveLength(1);
    expect(store.getRow("SELECT adapter_native_session_id, binding_generation, status FROM adapter_bindings")).toMatchObject({
      adapter_native_session_id: "legacy-native",
      binding_generation: 1,
      status: "active",
    });
    store.close();
  });

  it("marks stale native bindings and retries under the same run with a new generation", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.failNextResume = true;

    const result = await kernel.executeRun({
      ...baseRunInput,
      legacyAdapterSessionId: "legacy-stale",
      maxAttempts: 2,
    });

    expect(result.terminalStatus).toBe("succeeded");
    expect(result.run.runId).toBe(store.getRow("SELECT run_id FROM runs").run_id);
    expect(adapter.resumed).toHaveLength(1);
    expect(adapter.opened).toHaveLength(1);
    expect(store.allRows("SELECT attempt_no, status, retryable, retry_reason, resume_from_attempt_id FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "failed", retryable: 1 }),
      expect.objectContaining({ attempt_no: 2, status: "succeeded", retry_reason: "stale_binding" }),
    ]);
    expect(store.allRows("SELECT binding_generation, adapter_native_session_id, status FROM adapter_bindings ORDER BY binding_generation")).toEqual([
      expect.objectContaining({ binding_generation: 1, adapter_native_session_id: "legacy-stale", status: "stale" }),
      expect.objectContaining({ binding_generation: 2, adapter_native_session_id: "native-1", status: "active" }),
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
