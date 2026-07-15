import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { afterEach, describe, expect, it } from "vitest";
import { migrateSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { probeNodeSqliteRuntime, SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("SqliteAgentStore", () => {
  it("runs runtime and desktop coordinator migrations idempotently", () => {
    const store = newStore({ reconcileOnOpen: false });

    store.migrate();
    store.migrate();

    expect(store.getRow("SELECT COUNT(*) AS count FROM schema_migrations").count).toBe(30);
    expect(store.allRows("SELECT version FROM schema_migrations ORDER BY version")).toEqual(
      Array.from({ length: 30 }, (_, index) => ({ version: index + 1 })),
    );
    expect(tableNames(store)).toEqual([
      "adapter_bindings",
      "artifacts",
      "backend_conversation_delete_outbox",
      "backend_reconcile_state",
      "backend_turn_outbox",
      "chat_first_cold_start_sequence_receipts",
      "chat_first_deferral_outbox",
      "chat_first_materialization_receipts",
      "cleared_backend_turn_claims",
      "completion_delta_checkpoints",
      "context_owner_snapshot_state",
      "context_snapshot_state",
      "context_source_state",
      "conversation_journal_state",
      "conversation_turn_revisions",
      "conversation_turns",
      "default_execution_profile_preferences",
      "delegations",
      "desktop_artifact_deliveries",
      "desktop_attention_overrides",
      "desktop_context_access_log",
      "desktop_context_packets",
      "desktop_dispatches",
      "desktop_memory_candidates",
      "desktop_task_candidates",
      "events",
      "grants",
      "run_attempts",
      "runs",
      "schema_migrations",
      "session_execution_profiles",
      "sessions",
      "surface_conversations",
      "tool_invocation_ledger",
      "workstream_artifact_heads",
      "workstream_artifact_versions",
      "workstream_continuation_checkpoints",
    ]);
    expect(tableNames(store)).not.toContain("desktop_action_queue");

    store.close();
  });

  it("enforces one active execution-authority attempt per run in SQLite", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "act",
    });

    store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "worker-1",
    });
    expect(() => store.insertAttempt({
      runId: run.runId,
      attemptNo: 2,
      status: "queued",
      adapterId: "acp",
      adapterInstanceId: "worker-2",
    })).toThrow();

    expect(() => store.insertAttempt({
      runId: run.runId,
      attemptNo: 3,
      status: "failed",
      adapterId: "acp",
      adapterInstanceId: "worker-3",
    })).not.toThrow();
    expect(store.allRows("SELECT attempt_no, status FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "running" }),
      expect.objectContaining({ attempt_no: 3, status: "failed" }),
    ]);
    store.close();
  });

  it("persists execution role and provider boundary on sessions", () => {
    const store = newStore({ reconcileOnOpen: false });
    const managedLeaf = store.insertSession({
      ownerId: "owner",
      surfaceKind: "background_agent",
      executionRole: "leaf",
      providerBoundary: "managed_cloud",
      defaultAdapterId: "pi-mono",
    });

    expect(managedLeaf).toMatchObject({
      executionRole: "leaf",
      providerBoundary: "managed_cloud",
    });
    expect(store.getRow(
      "SELECT execution_role, provider_boundary FROM sessions WHERE session_id = ?",
      [managedLeaf.sessionId],
    )).toMatchObject({
      execution_role: "leaf",
      provider_boundary: "managed_cloud",
    });
    store.close();
  });

  it("repairs legacy duplicate active attempts before installing the authority index", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "act",
    });

    store.execute("DROP INDEX run_attempts_one_active_per_run_uq");
    store.execute("DELETE FROM schema_migrations WHERE version = 9");
    store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "acp",
      adapterInstanceId: "worker-1",
    });
    store.insertAttempt({
      runId: run.runId,
      attemptNo: 2,
      status: "queued",
      adapterId: "acp",
      adapterInstanceId: "worker-2",
    });
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 900 });

    expect(store.allRows("SELECT attempt_no, status, completed_at_ms FROM run_attempts ORDER BY attempt_no")).toEqual([
      expect.objectContaining({ attempt_no: 1, status: "orphaned", completed_at_ms: 900 }),
      expect.objectContaining({ attempt_no: 2, status: "queued" }),
    ]);
    expect(store.getRow("SELECT type, payload_json FROM events WHERE attempt_id = (SELECT attempt_id FROM run_attempts WHERE attempt_no = 1)")).toMatchObject({
      type: "attempt.orphaned",
      payload_json: expect.stringContaining("\"attemptId\":\"att_"),
    });
    expect(JSON.parse(String(store.getRow("SELECT payload_json FROM events").payload_json))).toMatchObject({
      reason: "active_attempt_authority_migration",
    });
    expect(() => store.insertAttempt({
      runId: run.runId,
      attemptNo: 3,
      status: "starting",
      adapterId: "acp",
      adapterInstanceId: "worker-3",
    })).toThrow();
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

  it("persists desktop coordinator records and rejects invalid JSON", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "succeeded",
      mode: "ask",
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "worker",
    });
    const artifact = store.insertArtifact({
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://result",
    });

    expect(() => store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      runId: run.runId,
      surfaceKind: "main_chat",
      objective: "bad packet",
      packetJson: "{",
      redactedPreviewJson: "{}",
      contextHash: "sha256:bad",
      retentionClass: "debug",
      expiresAtMs: Date.now() + 60_000,
    })).toThrow();
    expect(() => store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      runId: run.runId,
      surfaceKind: "main_chat",
      objective: "missing ttl",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:no-ttl",
      retentionClass: "debug",
    } as any)).toThrow("expiresAtMs must be in the future");
    expect(() => store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      runId: run.runId,
      surfaceKind: "main_chat",
      objective: "expired ttl",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:expired",
      retentionClass: "debug",
      createdAtMs: 100,
      expiresAtMs: 100,
    })).toThrow("expiresAtMs must be in the future");

    const packet = store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      runId: run.runId,
      surfaceKind: "main_chat",
      objective: "summarize current work",
      packetJson: JSON.stringify({ snippets: [] }),
      redactedPreviewJson: JSON.stringify({ preview: [] }),
      contextHash: "sha256:packet",
      retentionClass: "debug",
      tokenEstimate: 12,
      expiresAtMs: Date.now() + 60_000,
    });
    const dispatch = store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "approval",
      priority: 90,
      title: "Approve screenshot",
      decisionPrompt: "Allow screenshot image bytes?",
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      payloadJson: "{}",
    });
    const delivery = store.insertDesktopArtifactDelivery({
      artifactId: artifact.artifactId,
      ownerId: "owner",
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      sourceAttemptId: attempt.attemptId,
      intendedSurface: "main_chat",
      targetKind: "ask_omi",
      contentHash: "sha256:artifact",
    });
    const memory = store.insertDesktopMemoryCandidate({
      ownerId: "owner",
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      proposedFact: "User prefers local verification",
      evidenceRefsJson: "[]",
      confidence: 0.8,
      sensitivityTier: "low",
    });
    const task = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      sourceSessionId: session.sessionId,
      sourceRunId: run.runId,
      action: "create",
      proposedChangeJson: "{}",
      evidenceRefsJson: "[]",
      confidence: 0.7,
      requiresApproval: 1,
    });
    const access = store.insertDesktopContextAccessLog({
      ownerId: "owner",
      packetId: packet.packetId,
      runId: run.runId,
      sourceKind: "chat_surface",
      operation: "include_snippet",
      scopeJson: "{}",
      sensitivityTier: "low",
      policyDecision: "allowed",
      dispatchId: dispatch.dispatchId,
    });
    const override = store.upsertDesktopAttentionOverride({
      ownerId: "owner",
      subjectKind: "dispatch",
      subjectId: dispatch.dispatchId,
      hiddenUntilMs: 600,
      reason: "snoozed",
      createdAtMs: 200,
    });
    const updatedOverride = store.upsertDesktopAttentionOverride({
      ownerId: "owner",
      subjectKind: "dispatch",
      subjectId: dispatch.dispatchId,
      hiddenUntilMs: 700,
      reason: "still snoozed",
      createdAtMs: 900,
    });

    expect(store.getRow("SELECT objective FROM desktop_context_packets WHERE packet_id = ?", [packet.packetId]).objective).toBe("summarize current work");
    expect(store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [dispatch.dispatchId]).status).toBe("pending");
    expect(() => store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "other",
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: "{}",
      resolvedAtMs: 299,
    })).toThrow("not pending for owner");
    const resolvedDispatch = store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: "{}",
      resolvedAtMs: 300,
    });
    expect(resolvedDispatch.status).toBe("resolved");
    expect(() => store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner",
      status: "cancelled",
      resolvedBy: "user",
      resolvedAtMs: 301,
    })).toThrow("not pending for owner");
    expect(() => store.updateDesktopArtifactDelivery(delivery.deliveryId, {
      ownerId: "other",
      deliveryStatus: "delivered",
    })).toThrow();
    expect(store.updateDesktopArtifactDelivery(delivery.deliveryId, {
      ownerId: "owner",
      deliveryStatus: "delivered",
      deliveredAtMs: 400,
    })).toMatchObject({
      deliveryStatus: "delivered",
      deliveredAtMs: 400,
    });
    expect(store.getRow("SELECT delivery_status FROM desktop_artifact_deliveries WHERE delivery_id = ?", [delivery.deliveryId]).delivery_status).toBe("delivered");
    expect(store.getRow("SELECT status FROM desktop_memory_candidates WHERE candidate_id = ?", [memory.candidateId]).status).toBe("pending");
    expect(store.getRow("SELECT requires_approval FROM desktop_task_candidates WHERE candidate_id = ?", [task.candidateId]).requires_approval).toBe(1);
    expect(store.getRow("SELECT policy_decision FROM desktop_context_access_log WHERE access_id = ?", [access.accessId]).policy_decision).toBe("allowed");
    expect(store.getRow("SELECT hidden_until_ms FROM desktop_attention_overrides WHERE owner_id = ? AND subject_kind = ? AND subject_id = ?", [
      override.ownerId,
      override.subjectKind,
      override.subjectId,
    ]).hidden_until_ms).toBe(700);
    expect(updatedOverride.createdAtMs).toBe(override.createdAtMs);
    expect(store.getRow("SELECT hidden_until_ms, reason, created_at_ms FROM desktop_attention_overrides WHERE owner_id = ? AND subject_kind = ? AND subject_id = ?", [
      override.ownerId,
      override.subjectKind,
      override.subjectId,
    ])).toMatchObject({
      hidden_until_ms: 700,
      reason: "still snoozed",
      created_at_ms: override.createdAtMs,
    });

    store.close();
  });

  it("rejects coordinator records with mismatched owner or source scope", () => {
    const store = newStore({ reconcileOnOpen: false });
    const ownerSession = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });
    const otherSession = store.insertSession({
      ownerId: "other",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });
    const ownerRun = store.insertRun({
      sessionId: ownerSession.sessionId,
      clientId: "client",
      requestId: "owner",
      status: "succeeded",
      mode: "ask",
    });
    const otherRun = store.insertRun({
      sessionId: otherSession.sessionId,
      clientId: "client",
      requestId: "other",
      status: "succeeded",
      mode: "ask",
    });
    const otherArtifact = store.insertArtifact({
      sessionId: otherSession.sessionId,
      runId: otherRun.runId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://other",
    });

    expect(() => store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: ownerSession.sessionId,
      runId: otherRun.runId,
      surfaceKind: "main_chat",
      objective: "bad scope",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:bad-scope",
      retentionClass: "debug",
      expiresAtMs: Date.now() + 60_000,
    })).toThrow("outside owner scope");
    expect(() => store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "artifact_review",
      priority: 10,
      title: "Bad artifact",
      decisionPrompt: "Review",
      sourceSessionId: ownerSession.sessionId,
      sourceRunId: ownerRun.runId,
      sourceArtifactId: otherArtifact.artifactId,
    })).toThrow("outside owner scope");

    const packet = store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: ownerSession.sessionId,
      runId: ownerRun.runId,
      surfaceKind: "main_chat",
      objective: "good packet",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:good",
      retentionClass: "debug",
      expiresAtMs: Date.now() + 60_000,
    });
    const otherDispatch = store.insertDesktopDispatch({
      ownerId: "other",
      kind: "approval",
      priority: 10,
      title: "Other dispatch",
      decisionPrompt: "Other",
      sourceSessionId: otherSession.sessionId,
      sourceRunId: otherRun.runId,
    });

    expect(() => store.insertDesktopContextAccessLog({
      ownerId: "owner",
      packetId: packet.packetId,
      runId: ownerRun.runId,
      dispatchId: otherDispatch.dispatchId,
      sourceKind: "chat_surface",
      operation: "include_snippet",
      scopeJson: "{}",
      sensitivityTier: "low",
      policyDecision: "dispatch_created",
    })).toThrow("dispatch reference is outside owner scope");
    store.close();
  });

  it("persists sessions, runs, attempts, bindings, artifacts, and events across reopen", () => {
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
    const artifact = store.insertArtifact({
      sessionId: session.sessionId,
      runId: run.runId,
      attemptId: attempt.attemptId,
      kind: "json",
      role: "result",
      uri: "adapter://fake/native-artifact",
      displayName: "result.json",
      mimeType: "application/json",
      contentHash: "sha256:test",
      sizeBytes: 42,
      metadataJson: "{\"adapterArtifactId\":\"native-artifact\"}",
    });
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    expect(store.getRow("SELECT owner_id FROM sessions WHERE session_id = ?", [session.sessionId]).owner_id).toBe("owner");
    expect(store.getRow("SELECT status FROM runs WHERE run_id = ?", [run.runId]).status).toBe("succeeded");
    expect(store.getRow("SELECT status FROM run_attempts WHERE attempt_id = ?", [attempt.attemptId]).status).toBe("succeeded");
    expect(store.getRow("SELECT adapter_native_session_id FROM adapter_bindings WHERE binding_id = ?", [binding.bindingId]).adapter_native_session_id).toBe("native-session");
    expect(store.getRow("SELECT uri, metadata_json FROM artifacts WHERE artifact_id = ?", [artifact.artifactId])).toMatchObject({
      uri: "adapter://fake/native-artifact",
      metadata_json: "{\"adapterArtifactId\":\"native-artifact\"}",
    });
    expect(store.getRow("SELECT lifecycle_state, lifecycle_updated_at_ms FROM artifacts WHERE artifact_id = ?", [artifact.artifactId])).toMatchObject({
      lifecycle_state: "retained",
      lifecycle_updated_at_ms: null,
    });
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
    const replacementBinding = store.insertAdapterBinding({
      sessionId: secondSession.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-1",
      resumeFidelity: "native",
      status: "stale",
    });
    expect(replacementBinding.sessionId).toBe(secondSession.sessionId);
    const nativeRows = store.allRows(
      "SELECT session_id, status FROM adapter_bindings WHERE adapter_id = ? AND adapter_native_session_id = ? ORDER BY created_at_ms ASC",
      ["acp", "native-1"],
    );
    expect(nativeRows.map((row) => row.status)).toEqual(["closed", "stale"]);

    store.close();
  });

  it("keeps native binding replacement atomic when insert fails", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const existingBinding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-1",
      adapterInstanceId: "worker-1",
      resumeFidelity: "native",
      status: "active",
    });
    const secondSession = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });

    expect(() => store.insertAdapterBinding({
      bindingId: existingBinding.bindingId,
      sessionId: secondSession.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-1",
      resumeFidelity: "native",
      status: "stale",
    })).toThrow();

    expect(store.getRow("SELECT status, adapter_instance_id FROM adapter_bindings WHERE binding_id = ?", [existingBinding.bindingId])).toMatchObject({
      status: "active",
      adapter_instance_id: "worker-1",
    });
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

  it("nests withTransaction safely when the runtime never reports isTransaction", () => {
    // Reproduces the production failure: in the bundled agent runtime,
    // DatabaseSync.isTransaction does not flip to true inside an open
    // transaction, so a guard that trusts it cannot detect nesting. A real
    // SQLite connection throws "cannot start a transaction within a
    // transaction" on a nested BEGIN, so a nested withTransaction must reuse
    // the outer transaction rather than issue a second BEGIN.
    const execLog: string[] = [];
    let open = false;
    class NoIsTransactionDatabase {
      readonly isTransaction = false; // never flips, like the bundled runtime
      constructor(_path: string) {}
      exec(sql: string): void {
        const head = sql.trimStart().toUpperCase();
        if (head.startsWith("BEGIN")) {
          if (open) {
            throw new Error("cannot start a transaction within a transaction");
          }
          open = true;
          execLog.push("BEGIN");
        } else if (head.startsWith("COMMIT")) {
          open = false;
          execLog.push("COMMIT");
        } else if (head.startsWith("ROLLBACK")) {
          open = false;
          execLog.push("ROLLBACK");
        }
      }
      prepare(_sql: string) {
        return { run: () => {}, get: () => undefined, all: () => [] };
      }
      close(): void {}
    }

    const store = new SqliteAgentStore({
      databasePath: ":memory:",
      reconcileOnOpen: false,
      databaseFactory: NoIsTransactionDatabase,
    });

    execLog.length = 0; // ignore BEGIN/COMMIT from constructor migrations

    const result = store.withTransaction(() => store.withTransaction(() => "inner-result"));

    expect(result).toBe("inner-result");
    // Exactly one real transaction was opened — the nested call reused it.
    expect(execLog).toEqual(["BEGIN", "COMMIT"]);
    store.close();
  });

  it("rolls back artifact and lifecycle event writes atomically", () => {
    const store = newStore({ reconcileOnOpen: false });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main",
      defaultAdapterId: "acp",
    });
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "act",
    });

    expect(() => store.withTransaction(() => {
      const artifact = store.insertArtifact({
        sessionId: session.sessionId,
        runId: run.runId,
        kind: "log",
        role: "log",
        uri: "omi-artifact://rollback",
      });
      store.appendEvent({
        sessionId: session.sessionId,
        runId: run.runId,
        type: "artifact.created",
        payloadJson: JSON.stringify({ artifactId: artifact.artifactId }),
      });
      throw new Error("force rollback");
    })).toThrow("force rollback");

    expect(store.getRow("SELECT COUNT(*) AS count FROM artifacts").count).toBe(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM events WHERE type = ?", ["artifact.created"]).count).toBe(0);
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
      "attempt.orphaned",
      "run.orphaned",
      "binding.stale",
    ]);
    store.close();
  });

  it("reconciles desktop coordinator state on startup", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => now });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "delegated_agent",
      defaultAdapterId: "acp",
    });
    const parentRun = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "parent",
      status: "succeeded",
      mode: "act",
    });
    const childRun = store.insertRun({
      sessionId: session.sessionId,
      parentRunId: parentRun.runId,
      clientId: "client",
      requestId: "child",
      status: "orphaned",
      mode: "act",
    });
    const artifact = store.insertArtifact({
      sessionId: session.sessionId,
      runId: childRun.runId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://retrying",
    });
    const packet = store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      runId: childRun.runId,
      surfaceKind: "delegated_agent",
      objective: "expired work",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:expired",
      retentionClass: "ephemeral",
      expiresAtMs: 150,
    });
    const delivery = store.insertDesktopArtifactDelivery({
      artifactId: artifact.artifactId,
      ownerId: "owner",
      sourceSessionId: session.sessionId,
      sourceRunId: childRun.runId,
      intendedSurface: "main_chat",
      targetKind: "ask_omi",
      deliveryStatus: "retrying",
      errorJson: "{}",
    });
    const staleRecoveryDispatch = store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "failure_recovery",
      priority: 80,
      title: "Stale recovery",
      decisionPrompt: "This recovery dispatch expired before startup reconciliation.",
      sourceSessionId: session.sessionId,
      sourceRunId: childRun.runId,
      expiresAtMs: 150,
    });
    store.execute(
      `INSERT INTO delegations (
        delegation_id, parent_session_id, parent_run_id, child_session_id, child_run_id,
        mode, status, objective, request_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        "del_reconcile",
        session.sessionId,
        parentRun.runId,
        session.sessionId,
        childRun.runId,
        "spawn",
        "running",
        "child work",
        "{}",
        100,
      ],
    );

    now = 250;
    const reconciliation = store.reconcileStartup();

    expect(reconciliation.expiredContextPacketIds).toEqual([packet.packetId]);
    expect(store.getOptionalRow("SELECT packet_id FROM desktop_context_packets WHERE packet_id = ?", [packet.packetId])).toBeUndefined();
    expect(reconciliation.failedArtifactDeliveryIds).toEqual([delivery.deliveryId]);
    expect(reconciliation.recoveryDispatchIds).toHaveLength(1);
    expect(reconciliation.recoveryDispatchIds[0]).not.toBe(staleRecoveryDispatch.dispatchId);
    expect(store.getRow("SELECT status, resolved_at_ms, resolved_by FROM desktop_dispatches WHERE dispatch_id = ?", [staleRecoveryDispatch.dispatchId])).toMatchObject({
      status: "expired",
      resolved_at_ms: 250,
      resolved_by: "daemon_startup_reconciliation",
    });
    expect(store.getRow("SELECT delivery_status, error_json FROM desktop_artifact_deliveries WHERE delivery_id = ?", [delivery.deliveryId])).toMatchObject({
      delivery_status: "failed",
      error_json: "{\"reason\":\"daemon_startup_reconciliation\"}",
    });
    expect(store.getRow("SELECT kind, status, source_run_id FROM desktop_dispatches WHERE dispatch_id = ?", [reconciliation.recoveryDispatchIds[0]])).toMatchObject({
      kind: "failure_recovery",
      status: "pending",
      source_run_id: childRun.runId,
    });
    expect(store.getRow("SELECT status, completed_at_ms FROM delegations WHERE delegation_id = ?", ["del_reconcile"])).toMatchObject({
      status: "failed",
      completed_at_ms: 250,
    });
    expect(store.getRow("SELECT type FROM events WHERE type = ?", ["delegation.recovery_required"]).type).toBe("delegation.recovery_required");
    store.resolveDesktopDispatch(reconciliation.recoveryDispatchIds[0], {
      ownerId: "owner",
      status: "resolved",
      resolvedAtMs: 260,
    });
    expect(store.reconcileStartup().recoveryDispatchIds).toHaveLength(0);
    store.close();
  });

  it("expires stale pending recovery dispatches and creates one fresh recovery action", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => now });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "delegated_agent",
      defaultAdapterId: "acp",
    });
    const parentRun = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "parent",
      status: "succeeded",
      mode: "act",
    });
    const childRun = store.insertRun({
      sessionId: session.sessionId,
      parentRunId: parentRun.runId,
      clientId: "client",
      requestId: "child",
      status: "orphaned",
      mode: "act",
    });
    const staleDispatch = store.insertDesktopDispatch({
      dispatchId: "dispatch_stale_recovery",
      ownerId: "owner",
      kind: "failure_recovery",
      priority: 80,
      title: "Old recovery",
      decisionPrompt: "Old recovery",
      sourceSessionId: session.sessionId,
      sourceRunId: childRun.runId,
      expiresAtMs: 150,
    });

    now = 250;
    const reconciliation = store.reconcileStartup();

    expect(store.getRow("SELECT status, resolved_at_ms FROM desktop_dispatches WHERE dispatch_id = ?", [staleDispatch.dispatchId])).toMatchObject({
      status: "expired",
      resolved_at_ms: 250,
    });
    expect(reconciliation.recoveryDispatchIds).toHaveLength(1);
    expect(reconciliation.recoveryDispatchIds[0]).not.toBe(staleDispatch.dispatchId);
    expect(store.allRows("SELECT status FROM desktop_dispatches WHERE kind = ? AND source_run_id = ? ORDER BY created_at_ms", [
      "failure_recovery",
      childRun.runId,
    ]).map((row) => row.status)).toEqual(["expired", "pending"]);
    store.close();
  });

  it("does not recreate recovery dispatches after resolved or cancelled recovery decisions", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false, nowMs: () => 250 });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "delegated_agent",
      defaultAdapterId: "acp",
    });
    const parentRun = store.insertRun({
      sessionId: session.sessionId,
      clientId: "client",
      requestId: "parent",
      status: "succeeded",
      mode: "act",
    });
    const resolvedRun = store.insertRun({
      sessionId: session.sessionId,
      parentRunId: parentRun.runId,
      clientId: "client",
      requestId: "resolved-child",
      status: "orphaned",
      mode: "act",
    });
    const cancelledRun = store.insertRun({
      sessionId: session.sessionId,
      parentRunId: parentRun.runId,
      clientId: "client",
      requestId: "cancelled-child",
      status: "orphaned",
      mode: "act",
    });
    store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "failure_recovery",
      priority: 80,
      status: "resolved",
      title: "Resolved recovery",
      decisionPrompt: "Resolved recovery",
      sourceSessionId: session.sessionId,
      sourceRunId: resolvedRun.runId,
      resolvedAtMs: 200,
      resolvedBy: "user",
      resolutionJson: "{}",
    });
    store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "failure_recovery",
      priority: 80,
      status: "cancelled",
      title: "Cancelled recovery",
      decisionPrompt: "Cancelled recovery",
      sourceSessionId: session.sessionId,
      sourceRunId: cancelledRun.runId,
      resolvedAtMs: 200,
      resolvedBy: "user",
      resolutionJson: "{}",
    });

    const reconciliation = store.reconcileStartup();

    expect(reconciliation.recoveryDispatchIds).toEqual([]);
    expect(store.getRow("SELECT COUNT(*) AS count FROM desktop_dispatches WHERE kind = ?", ["failure_recovery"]).count).toBe(2);
    store.close();
  });

  it("rejects context packets that are expired against the store clock even with old createdAtMs", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false, nowMs: () => 1_000 });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });

    expect(() => store.insertDesktopContextPacket({
      ownerId: "owner",
      sessionId: session.sessionId,
      surfaceKind: "main_chat",
      objective: "old packet",
      packetJson: "{}",
      redactedPreviewJson: "{}",
      contextHash: "sha256:old",
      retentionClass: "debug",
      createdAtMs: 100,
      expiresAtMs: 500,
    })).toThrow("expiresAtMs must be in the future");
    store.close();
  });

  it("rejects expired pending dispatch resolution", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false, nowMs: () => 100 });
    const dispatch = store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "approval",
      priority: 10,
      title: "Expired",
      decisionPrompt: "Expired dispatch",
      expiresAtMs: 150,
    });

    expect(() => store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolvedAtMs: 200,
    })).toThrow("has expired");
    store.close();
  });

  it("does not fail artifact lifecycle migration when columns already exist but the migration row is missing", () => {
    const store = newStore({ reconcileOnOpen: false });
    store.execute("DELETE FROM schema_migrations WHERE version = ?", [2]);

    expect(() => store.migrate()).not.toThrow();
    expect(store.getRow("SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?", [2]).count).toBe(1);
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

  it("includes coordinator migrations in the runtime probe", () => {
    const execStatements: string[] = [];
    class ProbeDatabase {
      readonly isTransaction = false;
      constructor(_path: string) {}
      exec(sql: string): void {
        execStatements.push(sql);
      }
      prepare(_sql: string): { run: (..._args: unknown[]) => void; all: () => unknown[] } {
        return { run: () => {}, all: () => [] };
      }
      close(): void {}
    }

    probeNodeSqliteRuntime({ databaseFactory: ProbeDatabase });

    expect(execStatements.some((statement) => statement.includes("ADD COLUMN lifecycle_state"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("ADD COLUMN lifecycle_updated_at_ms"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_context_packets"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_dispatches"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_artifact_deliveries"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_memory_candidates"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_context_access_log"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE IF NOT EXISTS desktop_attention_overrides"))).toBe(true);
    expect(execStatements.some((statement) => statement.includes("CREATE TABLE chat_first_deferral_outbox"))).toBe(
      true,
    );
    expect(
      execStatements.some((statement) => statement.includes("CREATE TABLE chat_first_materialization_receipts")),
    ).toBe(true);
    expect(
      execStatements.some((statement) => statement.includes("CREATE TABLE chat_first_cold_start_sequence_receipts")),
    ).toBe(true);
  });

  it("stores no legacy_default grant rows in a fresh database", () => {
    const store = newStore({ reconcileOnOpen: false });
    const count = Number(
      store.getRow("SELECT COUNT(*) AS count FROM grants WHERE source = 'legacy_default'").count,
    );
    expect(count).toBe(0);
    store.close();
  });

  it("repairs downgrade-window profile and legacy journal inserts on every daemon open idempotently", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 100 });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "acp",
    });
    store.insertSurfaceConversation({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId: "conv_downgrade",
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    store.execute("DELETE FROM session_execution_profiles WHERE session_id = ?", [session.sessionId]);
    store.execute(
      `INSERT INTO conversation_turns(
         conversation_id, turn_id, role, surface_kind, content, created_at_ms,
         metadata_json, origin, status, content_blocks_json, resources_json, updated_at_ms
       ) VALUES (?, ?, 'user', 'main_chat', ?, ?, '{}', 'typed_chat', 'completed', '[]', '[]', ?)`,
      ["conv_downgrade", "turn_old_writer", "Old writer row", 2, 2],
    );

    const repaired = store.reconcileStartup();
    expect(repaired.repairedSessionProfileIds).toEqual([session.sessionId]);
    expect(repaired.repairedLegacyJournalTurnIds).toEqual(["turn_old_writer"]);
    const profile = store.getRow(
      "SELECT source, audit_json FROM session_execution_profiles WHERE session_id = ?",
      [session.sessionId],
    );
    expect(profile.source).toBe("legacy_backfill");
    expect(JSON.parse(String(profile.audit_json))).toMatchObject({
      legacyProjection: {
        owner: "desktop-kernel",
        removalCondition: expect.any(String),
        removeBy: "2026-10-01",
      },
    });
    const turn = store.getRow(
      `SELECT turn_seq, producer_id, payload_hash, metadata_json
       FROM conversation_turns WHERE turn_id = 'turn_old_writer'`,
    );
    expect(turn).toMatchObject({
      producer_id: "legacy:turn_old_writer",
      payload_hash: expect.stringMatching(/^sha256:[a-f0-9]{64}$/),
    });
    expect(Number(turn.turn_seq)).toBeGreaterThan(0);
    expect(JSON.parse(String(turn.metadata_json))).toMatchObject({
      startupRepair: {
        code: "downgrade_window_journal_repair",
        owner: "desktop-kernel",
        removalCondition: expect.any(String),
        removeBy: "2026-10-01",
      },
    });
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE turn_id = 'turn_old_writer'",
    ).count).toBe(1);
    const stable = JSON.stringify({ profile, turn, revisions: store.allRows("SELECT * FROM conversation_turn_revisions") });
    expect(store.reconcileStartup()).toMatchObject({
      repairedSessionProfileIds: [],
      repairedLegacyJournalTurnIds: [],
    });
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: true, nowMs: () => 300 });
    expect(JSON.stringify({
      profile: store.getRow(
        "SELECT source, audit_json FROM session_execution_profiles WHERE session_id = ?",
        [session.sessionId],
      ),
      turn: store.getRow(
        `SELECT turn_seq, producer_id, payload_hash, metadata_json
         FROM conversation_turns WHERE turn_id = 'turn_old_writer'`,
      ),
      revisions: store.allRows("SELECT * FROM conversation_turn_revisions"),
    })).toBe(stable);
    store.close();
  });

  it("repairs old-writer profile references by the immutable profile active at each row timestamp", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 100 });
    const session = store.insertSession({
      sessionId: "ses_profile_downgrade",
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
      providerBoundary: "local_user:acp",
      createdAtMs: 100,
      updatedAtMs: 100,
      lastActivityAtMs: 100,
    });
    store.insertRun({
      runId: "run_genuine_gen1",
      sessionId: session.sessionId,
      clientId: "legacy",
      requestId: "genuine-gen1",
      status: "succeeded",
      mode: "ask",
      profileGeneration: 1,
      createdAtMs: 150,
      completedAtMs: 150,
      updatedAtMs: 150,
    });
    store.insertAttempt({
      attemptId: "att_genuine_gen1",
      runId: "run_genuine_gen1",
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "",
      profileGeneration: 1,
      createdAtMs: 151,
      completedAtMs: 151,
      updatedAtMs: 151,
    });
    store.insertAdapterBinding({
      bindingId: "bind_genuine_gen1",
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      profileGeneration: 1,
      resumeFidelity: "none",
      status: "closed",
      createdAtMs: 152,
      updatedAtMs: 152,
    });
    migrateSessionExecutionProfile(store, {
      sessionId: session.sessionId,
      ownerId: "owner",
      expectedProfileGeneration: 1,
      adapterId: "pi-mono",
      reason: "generation_two",
    }, 200);
    store.close();

    insertRowsAsDowngradedWriter(databasePath, {
      sessionId: session.sessionId,
      suffix: "gen2",
      adapterId: "pi-mono",
      bindingGeneration: 2,
      createdAtMs: 250,
    });
    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 275 });
    expect(store.reconcileStartup()).toMatchObject({
      repairedRunProfileReferenceIds: ["run_gen2"],
      repairedAttemptProfileReferenceIds: ["att_gen2"],
      repairedBindingProfileReferenceIds: ["bind_gen2"],
    });
    expect(profileReferences(store)).toMatchObject({
      run_genuine_gen1: 1,
      att_genuine_gen1: 1,
      bind_genuine_gen1: 1,
      run_gen2: 2,
      att_gen2: 2,
      bind_gen2: 2,
    });
    migrateSessionExecutionProfile(store, {
      sessionId: session.sessionId,
      ownerId: "owner",
      expectedProfileGeneration: 2,
      adapterId: "acp",
      reason: "generation_three",
    }, 300);
    store.close();

    insertRowsAsDowngradedWriter(databasePath, {
      sessionId: session.sessionId,
      suffix: "gen3",
      adapterId: "acp",
      bindingGeneration: 3,
      createdAtMs: 300,
    });
    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 400 });
    expect(store.reconcileStartup()).toMatchObject({
      repairedRunProfileReferenceIds: ["run_gen3"],
      repairedAttemptProfileReferenceIds: ["att_gen3"],
      repairedBindingProfileReferenceIds: ["bind_gen3"],
    });
    const repaired = profileReferences(store);
    expect(repaired).toEqual({
      att_gen2: 2,
      att_gen3: 3,
      att_genuine_gen1: 1,
      bind_gen2: 2,
      bind_gen3: 3,
      bind_genuine_gen1: 1,
      run_gen2: 2,
      run_gen3: 3,
      run_genuine_gen1: 1,
    });
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 500 });
    expect(store.reconcileStartup()).toMatchObject({
      repairedRunProfileReferenceIds: [],
      repairedAttemptProfileReferenceIds: [],
      repairedBindingProfileReferenceIds: [],
    });
    expect(profileReferences(store)).toEqual(repaired);
    store.close();
  });

  it("terminalizes orphaned nonterminal journal rows once without a backend empty placeholder", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false, nowMs: () => 500 });
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "acp",
    });
    store.insertSurfaceConversation({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId: "conv_pending_restart",
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    store.execute(
      `INSERT INTO conversation_turns(
         conversation_id, turn_id, role, surface_kind, content, created_at_ms,
         metadata_json, origin, status, content_blocks_json, resources_json, updated_at_ms
       ) VALUES (?, ?, 'assistant', 'main_chat', '', ?, '{}', 'agent_runtime', 'streaming', '[]', '[]', ?)`,
      ["conv_pending_restart", "turn_orphan_stream", 2, 2],
    );

    const result = store.reconcileStartup();
    expect(result.reconciledJournalTurnIds).toEqual(["turn_orphan_stream"]);
    const repaired = store.getRow(
      "SELECT status, completed_at_ms, metadata_json FROM conversation_turns WHERE turn_id = ?",
      ["turn_orphan_stream"],
    );
    expect(repaired).toMatchObject({ status: "failed", completed_at_ms: 500 });
    expect(JSON.parse(String(repaired.metadata_json))).toMatchObject({
      startupRepair: { code: "daemon_restart_orphaned_turn", owner: "desktop-kernel" },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    const revisionCount = store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE turn_id = ?",
      ["turn_orphan_stream"],
    ).count;
    expect(store.reconcileStartup().reconciledJournalTurnIds).toEqual([]);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE turn_id = ?",
      ["turn_orphan_stream"],
    ).count).toBe(revisionCount);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM events WHERE type = 'journal.turn_reconciled'",
    ).count).toBe(1);
    store.close();
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

function insertRowsAsDowngradedWriter(
  databasePath: string,
  input: {
    sessionId: string;
    suffix: string;
    adapterId: string;
    bindingGeneration: number;
    createdAtMs: number;
  },
): void {
  const db = new DatabaseSync(databasePath);
  db.exec("PRAGMA foreign_keys = ON");
  db.prepare(
    `INSERT INTO runs(
       run_id, session_id, client_id, request_id, status, mode, input_json,
       created_at_ms, completed_at_ms, updated_at_ms
     ) VALUES (?, ?, 'old-writer', ?, 'succeeded', 'ask', '{}', ?, ?, ?)`,
  ).run(
    `run_${input.suffix}`,
    input.sessionId,
    input.suffix,
    input.createdAtMs,
    input.createdAtMs,
    input.createdAtMs,
  );
  db.prepare(
    `INSERT INTO run_attempts(
       attempt_id, run_id, attempt_no, status, adapter_id, adapter_instance_id,
       created_at_ms, completed_at_ms, updated_at_ms
     ) VALUES (?, ?, 1, 'succeeded', ?, '', ?, ?, ?)`,
  ).run(
    `att_${input.suffix}`,
    `run_${input.suffix}`,
    input.adapterId,
    input.createdAtMs,
    input.createdAtMs,
    input.createdAtMs,
  );
  db.prepare(
    `INSERT INTO adapter_bindings(
       binding_id, session_id, adapter_id, binding_generation, resume_fidelity,
       status, created_at_ms, updated_at_ms
     ) VALUES (?, ?, ?, ?, 'none', 'closed', ?, ?)`,
  ).run(
    `bind_${input.suffix}`,
    input.sessionId,
    input.adapterId,
    input.bindingGeneration,
    input.createdAtMs,
    input.createdAtMs,
  );
  db.close();
}

function profileReferences(store: SqliteAgentStore): Record<string, number> {
  const references: Record<string, number> = {};
  for (const row of store.allRows(
    `SELECT run_id AS id, profile_generation FROM runs
     UNION ALL SELECT attempt_id AS id, profile_generation FROM run_attempts
     UNION ALL SELECT binding_id AS id, profile_generation FROM adapter_bindings
     ORDER BY id ASC`,
  )) {
    references[String(row.id)] = Number(row.profile_generation);
  }
  return references;
}

function tableNames(store: SqliteAgentStore): string[] {
  return store.allRows("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    .map((row) => String(row.name));
}
