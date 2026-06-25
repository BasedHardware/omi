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

describe("AgentRuntimeKernel event stream", () => {
  it("persists and publishes ordered canonical events", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());
    const published: string[] = [];
    kernel.subscribe((event) => {
      published.push(`${event.eventSeq}:${event.type}`);
    });

    const result = await kernel.executeRun(baseRunInput);

    const persisted = store.allRows("SELECT event_seq, type FROM events ORDER BY event_seq");
    expect(persisted.map((row) => `${row.event_seq}:${row.type}`)).toEqual(published);
    expect(persisted.map((row) => row.type)).toEqual([
      "run.created",
      "attempt.created",
      "binding.created",
      "attempt.started",
      "run.running",
      "adapter.text_delta",
      "attempt.succeeded",
      "run.succeeded",
    ]);
    expect(store.allRows("SELECT DISTINCT run_id FROM events WHERE run_id IS NOT NULL")).toEqual([
      expect.objectContaining({ run_id: result.run.runId }),
    ]);
    store.close();
  });

  it("ignores late adapter events after a terminal state", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    const result = await kernel.executeRun(baseRunInput);
    adapter.emitLate(result.attempt.attemptId, {
      type: "text_delta",
      text: "late",
      sessionId: result.adapterSessionId ?? "native",
    });

    const textEvents = store.allRows("SELECT payload_json FROM events WHERE type = 'adapter.text_delta' ORDER BY event_seq");
    expect(textEvents).toHaveLength(1);
    expect(JSON.parse(String(textEvents[0].payload_json)).text).not.toBe("late");
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
