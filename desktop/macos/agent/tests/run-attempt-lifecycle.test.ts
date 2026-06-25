import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { baseRunInput, createKernelHarness } from "./kernel-fakes.js";
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
