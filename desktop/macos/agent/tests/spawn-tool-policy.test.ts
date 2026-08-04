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

describe("spawn-time tool policy persistence", () => {
  it("persists toolPolicy into background spawn run metadata", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const background = await kernel.spawnBackgroundAgent({
      ownerId: "owner",
      clientId: "client",
      requestId: "request-background-policy",
      prompt: "restricted background work",
      trustedUserSpawn: true,
      adapterId: "fake",
      defaultAdapterId: "fake",
      toolPolicy: { allowedToolNames: ["get_memories"] },
    });

    const inputJson = JSON.parse(
      store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [background.run.runId]).input_json as string,
    );
    expect(inputJson.metadata.toolPolicy).toEqual({ allowedToolNames: ["get_memories"] });
    store.close();
  });

  it("persists toolPolicy into delegated child run metadata", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.deferOnlyPromptIncludes = "hello";
    adapter.deferResult();
    const runningParent = kernel.executeRun(baseRunInput);
    await waitUntil(() => adapter.executed.length === 1);
    const parentRunId = adapter.executed[0].runId;

    const delegated = await kernel.delegateAgent({
      mode: "call",
      parentRunId,
      objective: "restricted delegated work",
      clientId: "client",
      requestId: "request-delegated-policy",
      toolPolicy: { allowedToolNames: ["get_memories"] },
    });

    const inputJson = JSON.parse(
      store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [delegated.childRun.runId]).input_json as string,
    );
    expect(inputJson.metadata.toolPolicy).toEqual({ allowedToolNames: ["get_memories"] });

    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await runningParent;
    store.close();
  });

  it("persists no toolPolicy key when the spawn input omits it", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const background = await kernel.spawnBackgroundAgent({
      ownerId: "owner",
      clientId: "client",
      requestId: "request-background-nopolicy",
      prompt: "unrestricted background work",
      trustedUserSpawn: true,
      adapterId: "fake",
      defaultAdapterId: "fake",
    });

    const inputJson = JSON.parse(
      store.getRow("SELECT input_json FROM runs WHERE run_id = ?", [background.run.runId]).input_json as string,
    );
    expect(inputJson.metadata.toolPolicy).toBeUndefined();
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
