import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { probeNodeSqliteRuntime, SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("SqliteAgentStore", () => {
  it("runs Phase 1 migrations idempotently", () => {
    const store = newStore({ reconcileOnOpen: false });

    store.migrate();
    store.migrate();

    expect(store.getRow("SELECT COUNT(*) AS count FROM schema_migrations").count).toBe(1);
    expect(tableNames(store)).toEqual([
      "adapter_bindings",
      "artifacts",
      "delegations",
      "events",
      "grants",
      "run_attempts",
      "runs",
      "schema_migrations",
      "sessions",
    ]);

    store.close();
  });

  it("applies WAL, foreign keys, synchronous NORMAL, and busy timeout", () => {
    const store = newStore({ reconcileOnOpen: false });

    expect(store.getPragma("journal_mode")).toBe("wal");
    expect(store.getPragma("foreign_keys")).toBe(1);
    expect(store.getPragma("synchronous")).toBe(1);
    expect(store.getPragma("busy_timeout")).toBe(5000);

    expect(() => store.insertRun({
      sessionId: "ses_missing",
      clientId: "client",
      requestId: "request",
      status: "queued",
      mode: "ask",
    })).toThrow();

    store.close();
  });

  it("persists sessions, runs, attempts, bindings, and events across reopen", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 100 });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "task_chat",
      defaultAdapterId: "acp",
    });
    const binding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-session",
      adapterInstanceId: "worker-1",
      resumeFidelity: "native",
      status: "active",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "succeeded",
      mode: "ask",
      inputJson: "{\"prompt\":\"hello\"}",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "worker-1",
      bindingId: binding.bindingId,
    });
    const event = store.appendEvent({
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      type: "run.completed",
      payloadJson: "{\"ok\":true}",
    });
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    expect(store.getRow("SELECT owner_id FROM sessions WHERE session_id = ?", [session.sessionId]).owner_id).toBe("owner");
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [run.runId]).status).toBe("succeeded");
    expect(store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [attempt.attemptId]).status).toBe("succeeded");
    expect(store.getRow("SELECT adapter_native_session_id FROM adapter_bindings WHERE binding_id = ?", [binding.bindingId]).adapter_native_session_id).toBe("native-session");
    expect(store.getRow("SELECT type FROM events WHERE event_id = ?", [event.eventId]).type).toBe("run.completed");
    store.close();
  });

  it("enforces external-ref, active-binding, and native-binding uniqueness", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      defaultAdapterId: "acp",
    });

    expect(() => store.insertSession({
      ownerId: "owner",
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "task-1",
      defaultAdapterId: "acp",
    })).toThrow();

    store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-1",
      resumeFidelity: "native",
      status: "active",
    });

    expect(() => store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 2,
      resumeFidelity: "native",
      status: "active",
    })).toThrow();

    const secondSession = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    expect(() => store.insertAdapterBinding({
      sessionId: secondSession.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-1",
      resumeFidelity: "native",
      status: "stale",
    })).toThrow();

    store.close();
  });

  it("rolls back state and event writes atomically", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });

    expect(() => store.withTransaction(() => {
      const run = store.insertRun({
        sessionId: session.sessionId,
        clientId: "client",
        requestId: "request",
        status: "running",
        mode: "act",
      });
      store.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "run.started",
      });
      throw new Error("force rollback");
    })).toThrow("force rollback");

    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM events").count).toBe(0);
    store.close();
  });

  it("reconciles active attempts and non-resumable bindings on startup", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => now });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const nativeBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-session",
      adapterInstanceId: "native-worker",
      resumeFidelity: "native",
      status: "active",
    });
    const nonResumableBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterInstanceId: "pi-worker",
      resumeFidelity: "none",
      status: "active",
    });
    const activeRun = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "active",
      status: "running",
      mode: "act",
    });
    const activeAttempt = store.insertAttempt({
      runId: activeRun.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "attempt-worker",
      bindingId: nativeBinding.bindingId,
    });
    const completedRun = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "done",
      status: "succeeded",
      mode: "ask",
    });
    const completedAttempt = store.insertAttempt({
      runId: completedRun.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "completed-worker",
      bindingId: nativeBinding.bindingId,
    });
    store.close();

    now = 250;
    store = new SqliteAgentStore({ databasePath, nowMs: () => now });

    expect(store.getRow("SELECT status, adapter_instance_id FROM run_attempts WHERE attempt_id = ?", [activeAttempt.attemptId])).toMatchObject({
      status: "orphaned",
      adapter_instance_id: "",
    });
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [activeRun.runId]).status).toBe("orphaned");
    expect(store.getRow("SELECT status, adapter_instance_id FROM adapter_bindings WHERE binding_id = ?", [nonResumableBinding.bindingId])).toMatchObject({
      status: "stale",
      adapter_instance_id: null,
    });
    expect(store.getRow("SELECT status, adapter_instance_id FROM adapter_bindings WHERE binding_id = ?", [nativeBinding.bindingId])).toMatchObject({
      status: "active",
      adapter_instance_id: null,
    });
    expect(store.getRow("SELECT status, adapter_instance_id FROM run_attempts WHERE attempt_id = ?", [completedAttempt.attemptId])).toMatchObject({
      status: "succeeded",
      adapter_instance_id: "",
    });
    expect(store.allRows("SELECT type FROM events ORDER BY event_seq").map((row) => row.type)).toEqual([
      "runtime.attempt_orphaned",
      "runtime.run_orphaned",
      "runtime.binding_stale",
    ]);
    store.close();
  });

  it("fails loudly when the runtime probe cannot use node:sqlite", () => {
    class BrokenDatabase {
      readonly isTransaction = false;
      constructor(_path: string) {}
      exec(_sql: string): void {
        throw new Error("sqlite unavailable");
      }
      prepare(_sql: string): never {
        throw new Error("prepare unavailable");
      }
      close(): void {}
    }

    expect(() => probeNodeSqliteRuntime({ databaseFactory: BrokenDatabase })).toThrow(
      /Bundled Node runtime does not support required node:sqlite AgentStore features: sqlite unavailable/,
    );
  });
});

function newStore(options: { reconcileOnOpen: boolean }): SqliteAgentStore {
  return new SqliteAgentStore({ databasePath: newDatabasePath(), ...options });
}

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-agent-store-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}

function tableNames(store: SqliteAgentStore): string[] {
  return store.allRows("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    .map((row) => String(row.name));
}
