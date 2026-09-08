import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DirectControlExecutionBroker } from "../src/runtime/direct-control-execution.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe("direct desktop control execution authority", () => {
  it("aborts owner A before a suspended spawn effect and returns an owner-scoped failed receipt", async () => {
    const { store, kernel } = createKernelHarness(databasePath(), "acp");
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({ activeOwnerId: () => activeOwnerId });
    const execution = broker.execute({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "spawn-before-switch",
      name: "spawn_agent",
      input: {
        objective: "This child must never start",
        originSurfaceKind: "agent_control",
        requestedAgentCount: 1,
        visible: true,
        adapterId: "acp",
      },
    }, { kernel });

    broker.transitionOwner("owner-a", "owner-b");
    activeOwnerId = "owner-b";
    const receipt = await execution;

    expect(receipt.ownerId).toBe("owner-a");
    expect(JSON.parse(receipt.result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_owner_revoked" },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM sessions").count).toBe(0);
    store.close();
  });

  it("aborts an in-flight owner A continuation and cannot surface its late adapter success", async () => {
    const { store, kernel, adapter } = createKernelHarness(databasePath(), "acp");
    const target = store.insertSession({
      ownerId: "owner-a",
      surfaceKind: "background_agent",
      defaultAdapterId: "acp",
      executionRole: "leaf",
    });
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({
      activeOwnerId: () => activeOwnerId,
      recentRequestLimit: 2,
    });
    adapter.deferResult();
    const continueRequest = {
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "continue-before-switch",
      name: "send_agent_message",
      input: {
        sessionId: target.sessionId,
        originSurfaceKind: "agent_control",
        prompt: "Continue only while owner A is active",
        mode: "act",
      },
    };
    const execution = broker.execute(continueRequest, { kernel });
    await waitUntil(() => adapter.executed.length === 1);

    for (const requestId of ["recent-read-1", "recent-read-2", "recent-read-3"]) {
      const read = await broker.execute({
        ownerId: "owner-a",
        clientId: "desktop-client",
        requestId,
        name: "list_agent_sessions",
        input: {},
      }, { kernel });
      expect(JSON.parse(read.result)).toMatchObject({ ok: true });
    }
    const activeReplay = await broker.execute(continueRequest, { kernel });
    expect(JSON.parse(activeReplay.result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_request_replayed" },
    });

    broker.transitionOwner("owner-a", "owner-b");
    activeOwnerId = "owner-b";
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late owner A success" });
    const receipt = await execution;

    expect(receipt.ownerId).toBe("owner-a");
    expect(JSON.parse(receipt.result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_owner_revoked" },
    });
    expect(store.getRow(
      "SELECT status, final_text FROM runs WHERE session_id = ? ORDER BY created_at_ms DESC LIMIT 1",
      [target.sessionId],
    )).toMatchObject({ status: "cancelled", final_text: null });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(1);
    store.close();
  });

  it("retains an accepted spawn signal until refresh moves away from its owner", async () => {
    const { store, kernel, adapter } = createKernelHarness(databasePath(), "acp");
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({ activeOwnerId: () => activeOwnerId });
    adapter.deferResult();
    const receipt = await broker.execute({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "accepted-spawn-before-switch",
      name: "spawn_agent",
      input: {
        objective: "Stop this child when owner A leaves",
        originSurfaceKind: "agent_control",
        requestedAgentCount: 1,
        visible: true,
        adapterId: "acp",
      },
    }, { kernel });
    expect(JSON.parse(receipt.result)).toMatchObject({ ok: true });
    await waitUntil(() => adapter.executed.length === 1);
    expect(broker.retainedSignalCount("owner-a")).toBe(1);

    expect(broker.transitionOwner("owner-a", "owner-b")).toBe(1);
    activeOwnerId = "owner-b";
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late spawned success" });
    await waitUntil(() => store.getRow("SELECT status FROM runs LIMIT 1").status === "cancelled");

    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    expect(broker.retainedSignalCount("owner-a")).toBe(0);
    store.close();
  });

  it("immediately compensates every admitted sibling when a later sibling spawn fails", async () => {
    const { store, kernel, adapter } = createKernelHarness(databasePath(), "acp");
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({ activeOwnerId: () => activeOwnerId });
    adapter.deferResult();
    const originalSpawn = kernel.spawnBackgroundAgent.bind(kernel);
    let spawnCalls = 0;
    vi.spyOn(kernel, "spawnBackgroundAgent").mockImplementation(async (input) => {
      spawnCalls += 1;
      if (spawnCalls === 2) {
        await waitUntil(() => adapter.executed.length === 1);
        throw new Error("second sibling rejected");
      }
      return originalSpawn(input);
    });

    const receipt = await broker.execute({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "partial-multi-spawn",
      name: "spawn_agent",
      input: {
        objective: "Start two siblings atomically",
        originSurfaceKind: "agent_control",
        requestedAgentCount: 2,
        visible: true,
        adapterId: "acp",
      },
    }, { kernel });

    expect(JSON.parse(receipt.result)).toMatchObject({
      ok: false,
      error: {
        code: "partial_spawn_compensated",
        details: {
          admittedRunIds: [expect.any(String)],
          cancellations: [{ accepted: true, runId: expect.any(String) }],
          cause: "second sibling rejected",
        },
      },
    });
    expect(adapter.cancelled).toHaveLength(1);
    expect(store.getRow("SELECT status FROM runs LIMIT 1").status).toBe("cancelling");
    expect(broker.retainedSignalCount("owner-a")).toBe(1);

    expect(broker.transitionOwner("owner-a", "owner-b")).toBe(1);
    activeOwnerId = "owner-b";
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late compensated success" });
    await waitUntil(() => store.getRow("SELECT status FROM runs LIMIT 1").status === "cancelled");

    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    expect(broker.retainedSignalCount("owner-a")).toBe(0);
    store.close();
  });

  it("returns admitted run identities when partial-spawn compensation itself fails", async () => {
    const { store, kernel, adapter } = createKernelHarness(databasePath(), "acp");
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({ activeOwnerId: () => activeOwnerId });
    adapter.deferResult();
    const originalSpawn = kernel.spawnBackgroundAgent.bind(kernel);
    let spawnCalls = 0;
    vi.spyOn(kernel, "spawnBackgroundAgent").mockImplementation(async (input) => {
      spawnCalls += 1;
      if (spawnCalls === 2) {
        await waitUntil(() => adapter.executed.length === 1);
        throw new Error("second sibling rejected");
      }
      return originalSpawn(input);
    });
    vi.spyOn(kernel, "cancelRun").mockRejectedValue(new Error("cancellation transport unavailable"));

    const receipt = await broker.execute({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "partial-multi-spawn-cleanup-failure",
      name: "spawn_agent",
      input: {
        objective: "Expose admitted identity if cleanup fails",
        originSurfaceKind: "agent_control",
        requestedAgentCount: 2,
        visible: true,
        adapterId: "acp",
      },
    }, { kernel });

    expect(JSON.parse(receipt.result)).toMatchObject({
      ok: false,
      error: {
        code: "partial_spawn_cleanup_failed",
        details: {
          admittedRunIds: [expect.any(String)],
          cancellations: [{
            runId: expect.any(String),
            error: "cancellation transport unavailable",
          }],
          cause: "second sibling rejected",
        },
      },
    });
    expect(broker.retainedSignalCount("owner-a")).toBe(1);

    expect(broker.transitionOwner("owner-a", "owner-b")).toBe(1);
    activeOwnerId = "owner-b";
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late unreported success" });
    await waitUntil(() => store.getRow("SELECT status FROM runs LIMIT 1").status === "cancelled");
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    store.close();
  });

  it("bounds completed request replay history and prunes retained signals at terminal runs", async () => {
    const { store, kernel } = createKernelHarness(databasePath(), "acp");
    const broker = new DirectControlExecutionBroker({
      activeOwnerId: () => "owner-a",
      recentRequestLimit: 2,
    });
    const readRequest = (requestId: string) => ({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId,
      name: "list_agent_sessions",
      input: {},
    });
    for (const requestId of ["bounded-1", "bounded-2", "bounded-3"]) {
      expect(JSON.parse((await broker.execute(readRequest(requestId), { kernel })).result)).toMatchObject({ ok: true });
    }
    expect(JSON.parse((await broker.execute(readRequest("bounded-2"), { kernel })).result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_request_replayed" },
    });
    expect(JSON.parse((await broker.execute(readRequest("bounded-1"), { kernel })).result)).toMatchObject({ ok: true });

    const spawn = await broker.execute({
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "terminal-spawn",
      name: "spawn_agent",
      input: {
        objective: "Finish and release retained authority",
        originSurfaceKind: "agent_control",
        requestedAgentCount: 1,
        visible: true,
        adapterId: "acp",
      },
    }, { kernel });
    expect(JSON.parse(spawn.result)).toMatchObject({ ok: true });
    await waitUntil(() => store.getRow("SELECT status FROM runs LIMIT 1").status === "succeeded");
    await waitUntil(() => broker.retainedSignalCount("owner-a") === 0);
    expect(broker.transitionOwner("owner-a", "owner-b")).toBe(0);
    store.close();
  });

  it("aborts a direct run-and-wait child on owner transition and rejects request replay", async () => {
    const { store, kernel, adapter } = createKernelHarness(databasePath(), "acp");
    const surface = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const parentSession = kernel.resolveSurfaceSession({
      ownerId: "owner-a",
      surfaceRef: surface,
      defaultAdapterId: "acp",
    });
    const admittedContextSnapshot = kernel.contextSnapshotForExactSurface("owner-a", surface);
    const parentRun = store.insertRun({
      sessionId: parentSession.agentSessionId,
      clientId: "desktop-client",
      requestId: "parent-run",
      status: "running",
      mode: "act",
      inputJson: JSON.stringify({ prompt: "parent", admittedContextSnapshot }),
    });
    store.insertAttempt({
      runId: parentRun.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "parent-worker",
    });
    let activeOwnerId = "owner-a";
    const broker = new DirectControlExecutionBroker({ activeOwnerId: () => activeOwnerId });
    adapter.deferResult();
    const request = {
      ownerId: "owner-a",
      clientId: "desktop-client",
      requestId: "run-and-wait-before-switch",
      name: "run_agent_and_wait",
      input: {
        objective: "Bounded child work",
        parentRunId: parentRun.runId,
        originSurfaceKind: "agent_control",
        runMode: "act",
      },
    };
    const execution = broker.execute(request, { kernel });
    await waitUntil(() => adapter.executed.length === 1);

    broker.abortOwner("owner-a", "owner_state_cleared");
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late child success" });
    const receipt = await execution;
    expect(JSON.parse(receipt.result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_owner_revoked" },
    });
    const childRuns = store.allRows("SELECT status, final_text FROM runs WHERE parent_run_id = ?", [parentRun.runId]);
    expect(childRuns).toEqual([{ status: "cancelled", final_text: null }]);

    const replay = await broker.execute(request, { kernel });
    expect(JSON.parse(replay.result)).toMatchObject({
      ok: false,
      error: { code: "direct_control_request_replayed" },
    });
    store.close();
  });
});

function databasePath(): string {
  const root = mkdtempSync(join(tmpdir(), "omi-direct-control-authority-"));
  roots.push(root);
  return join(root, "agent.sqlite3");
}
