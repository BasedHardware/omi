import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness, waitUntil } from "./kernel-fakes.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

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
    expect(store.allRows("SELECT attempt_id, run_id, attempt_no, status FROM run_attempts ORDER BY created_at_ms, attempt_id")).toEqual([
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

  it("does not fall back to a legacy alias when an explicit external ref is new", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath());

    const first = await kernel.executeRun({
      ...baseRunInput,
      requestId: "chat-1",
      externalRefKind: "chat",
      externalRefId: "backend-chat-1",
      legacyClientScope: "main-chat",
      legacySessionKey: "main",
    });
    const second = await kernel.executeRun({
      ...baseRunInput,
      requestId: "chat-2",
      externalRefKind: "chat",
      externalRefId: "backend-chat-2",
      legacyClientScope: "main-chat",
      legacySessionKey: "main",
    });

    expect(second.session.sessionId).not.toBe(first.session.sessionId);
    expect(store.allRows("SELECT session_id FROM sessions ORDER BY created_at_ms")).toHaveLength(2);
    store.close();
  });

  it("persists adapter-emitted artifacts under canonical run and attempt ids", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    adapter.nextArtifacts = [{
      kind: "markdown",
      role: "result",
      uri: "adapter://fake/native-report",
      displayName: "report.md",
      mimeType: "text/markdown",
      contentHash: "sha256:def",
      sizeBytes: 42,
      metadata: { adapterArtifactId: "native-report" },
    }];

    const result = await kernel.executeRun(baseRunInput);
    const artifacts = kernel.inspectArtifacts({ runId: result.run.runId });

    expect(artifacts).toEqual([
      expect.objectContaining({
        sessionId: result.session.sessionId,
        runId: result.run.runId,
        attemptId: result.attempt.attemptId,
        uri: "adapter://fake/native-report",
        role: "result",
      }),
    ]);
    expect(JSON.parse(artifacts[0].metadataJson)).toEqual({ adapterArtifactId: "native-report" });
    expect(store.allRows("SELECT type FROM events WHERE type = 'artifact.created'")).toHaveLength(1);
    store.close();
  });

  it("replaces a stale process-local pinned binding through the pinned worker", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id, binding_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? ORDER BY binding_generation DESC LIMIT 1",
      [first.session.sessionId, "pi-mono"],
    );
    const firstBindingId = firstBinding.binding_id;
    store.execute("UPDATE adapter_bindings SET status = 'stale', invalidated_at_ms = ?, updated_at_ms = ? WHERE binding_id = ?", [
      Date.now(),
      Date.now(),
      firstBindingId,
    ]);

    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-replace-stale",
    });

    expect(second.run.status).toBe("succeeded");
    const secondBinding = store.getRow(
      "SELECT binding_id, binding_generation FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [second.session.sessionId, "pi-mono"],
    );
    expect(secondBinding.binding_id).not.toBe(firstBindingId);
    expect(secondBinding.binding_generation).toBe(firstBinding.binding_generation + 1);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBindingId]).status).toBe("stale");
    expect(JSON.parse(store.getRow("SELECT payload_json FROM events WHERE type = 'binding.replaced'").payload_json)).toMatchObject({
      bindingId: secondBinding.binding_id,
      replacesBindingId: firstBindingId,
    });
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });

  it("reassigns an idle pinned pi-mono worker to a different session", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );

    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-other-session",
      externalRefId: "task-other-session",
    });

    expect(second.run.status).toBe("succeeded");
    expect(second.session.sessionId).not.toBe(first.session.sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'", ["pi-mono"]).count).toBe(1);
    const staleEvent = store.getRow("SELECT session_id, run_id, attempt_id, payload_json FROM events WHERE type = 'binding.stale' ORDER BY event_seq DESC LIMIT 1");
    expect(staleEvent).toMatchObject({
      session_id: first.session.sessionId,
      run_id: null,
      attempt_id: null,
    });
    expect(JSON.parse(staleEvent.payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      reason: "pinned_worker_reassigned",
    });
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });

  it("queues a new pi-mono binding while the only pinned worker is busy", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });
    adapter.deferOnlyPromptIncludes = "hold worker";
    adapter.deferResult();

    const firstRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-hold-worker",
      prompt: "hold worker",
    });
    await waitUntil(() => adapter.executed.length === 1);
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'",
      ["pi-mono"],
    );

    const secondRun = kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-queued-saturation",
      externalRefId: "task-queued-saturation",
      prompt: "queued after saturation",
    });
    await Promise.resolve();
    expect(adapter.opened).toHaveLength(1);

    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "first done" });
    const [first, second] = await Promise.all([firstRun, secondRun]);

    expect(first.run.status).toBe("succeeded");
    expect(second.run.status).toBe("succeeded");
    expect(adapter.opened).toHaveLength(2);
    expect(adapter.executed).toHaveLength(2);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    const staleEvent = store.getRow("SELECT payload_json FROM events WHERE type = 'binding.stale' ORDER BY event_seq DESC LIMIT 1");
    expect(JSON.parse(staleEvent.payload_json)).toMatchObject({
      bindingId: firstBinding.binding_id,
      reason: "pinned_worker_reassigned",
    });
    store.close();
  });

  it("releases an idle stale pi-mono pin before replacing an invalid latest binding", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "pi-mono", 1);
    Object.assign(adapter.capabilities, {
      resumeFidelity: "none",
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      restartBehavior: "process_local_bindings_stale",
    });

    const first = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
    });
    const firstBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [first.session.sessionId, "pi-mono"],
    );
    const second = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-invalid-target",
      externalRefId: "task-invalid-target",
    });
    const secondBinding = store.getRow(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND adapter_id = ? AND status = 'active'",
      [second.session.sessionId, "pi-mono"],
    );
    store.execute("UPDATE adapter_bindings SET status = 'invalid', invalidated_at_ms = ?, updated_at_ms = ? WHERE binding_id = ?", [
      Date.now(),
      Date.now(),
      secondBinding.binding_id,
    ]);

    const third = await kernel.executeRun({
      ...baseRunInput,
      adapterId: "pi-mono",
      defaultAdapterId: "pi-mono",
      requestId: "request-invalid-target-retry",
      externalRefId: "task-invalid-target",
    });

    expect(third.run.status).toBe("succeeded");
    expect(third.session.sessionId).toBe(second.session.sessionId);
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [firstBinding.binding_id]).status).toBe("stale");
    expect(store.getRow("SELECT COUNT(*) AS count FROM adapter_bindings WHERE adapter_id = ? AND status = 'active'", ["pi-mono"]).count).toBe(1);
    expect(adapter.opened).toHaveLength(3);
    expect(adapter.executed).toHaveLength(3);
    store.close();
  });

  it("reconciles active attempts as orphaned and keeps restart semantics adapter-scoped", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => now });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "task_chat",
      defaultAdapterId: "acp",
    });
    const nativeBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-session",
      adapterInstanceId: "worker-acp",
      resumeFidelity: "native",
      status: "active",
    });
    const processLocalBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterNativeSessionId: "pi-session",
      adapterInstanceId: "worker-pi",
      resumeFidelity: "none",
      status: "active",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "restart-active",
      status: "running",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "worker-acp",
      bindingId: nativeBinding.bindingId,
    });
    store.close();

    now = 200;
    store = new SqliteAgentStore({ databasePath, nowMs: () => now });

    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [run.runId]).status).toBe("orphaned");
    expect(store.getRow("SELECT status, adapter_instance_id FROM run_attempts WHERE attempt_id = ?", [attempt.attemptId])).toMatchObject({
      status: "orphaned",
      adapter_instance_id: "",
    });
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [nativeBinding.bindingId]).status).toBe("active");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [processLocalBinding.bindingId]).status).toBe("stale");
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toEqual([
      "runtime.attempt_orphaned",
      "runtime.run_orphaned",
      "runtime.binding_stale",
    ]);
    store.close();
  });
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-kernel-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
