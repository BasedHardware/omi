import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import {
  buildWorkstreamOpenLoopSnapshot,
  deliverDesktopTaskCandidate,
  exportWorkstreamContinuationCheckpoint,
  importWorkstreamContinuationCheckpoint,
  migrateTaskSessionsToWorkstreams,
  persistWorkstreamArtifactVersion,
  persistWorkstreamContextPacket,
  projectCanonicalCandidateResolution,
  projectWorkstreamContinuity,
  readWorkstreamContinuationCheckpoint,
  reconcileLegacyTaskCandidateOutbox,
  resolveWorkstreamSession,
  type CanonicalCandidatePayload,
  type WorkstreamProductContext,
} from "../src/runtime/workstream-continuity.js";

const dirs: string[] = [];

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("workstream continuity", () => {
  it("resolves one session and conversation per owner/workstream across store instances", () => {
    const path = newDatabasePath();
    const firstStore = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    const first = resolveWorkstreamSession(firstStore, { ownerId: "owner", workstreamId: "ws-1" }, () => 1);
    firstStore.close();

    const secondStore = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    const second = resolveWorkstreamSession(secondStore, { ownerId: "owner", workstreamId: "ws-1" }, () => 2);

    expect(second).toEqual(first);
    expect(secondStore.allRows("SELECT * FROM sessions WHERE external_ref_kind = 'workstream'")).toHaveLength(1);
    expect(secondStore.allRows("SELECT * FROM surface_conversations WHERE surface_kind = 'workstream'")).toHaveLength(1);
    secondStore.close();
  });

  it("upgrades pre-workstream Candidate rows into retryable canonical outbox records", () => {
    const path = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    const legacy = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      action: "create",
      proposedChangeJson: JSON.stringify({ description: "Send the update", owner: "user" }),
      evidenceRefsJson: JSON.stringify([{ kind: "conversation", id: "conv-1", scope: "canonical" }]),
      confidence: 0.75,
      requiresApproval: 1,
    });
    const terminalLegacy = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      action: "create",
      proposedChangeJson: JSON.stringify({ description: "Old rejected task", owner: "user" }),
      evidenceRefsJson: JSON.stringify([{ kind: "conversation", id: "conv-2", scope: "canonical" }]),
      confidence: 0.5,
      requiresApproval: 1,
      status: "rejected",
    });
    store.execute("DROP TABLE workstream_artifact_heads");
    store.execute("DROP TABLE workstream_artifact_versions");
    store.execute("DROP TABLE workstream_continuation_checkpoints");
    store.execute("DROP INDEX desktop_task_candidates_owner_status_idx");
    store.execute("DROP INDEX desktop_task_candidates_delivery_idx");
    store.execute("DROP INDEX desktop_task_candidates_task_idx");
    store.execute("ALTER TABLE desktop_task_candidates RENAME TO desktop_task_candidates_future");
    store.execute(`CREATE TABLE desktop_task_candidates(
      candidate_id TEXT PRIMARY KEY,
      owner_id TEXT NOT NULL,
      source_session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
      source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
      action TEXT NOT NULL CHECK (action IN ('create','update','complete','delete')),
      task_ref TEXT,
      proposed_change_json TEXT NOT NULL CHECK (json_valid(proposed_change_json)),
      evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
      confidence REAL NOT NULL,
      requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0,1)),
      status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected','expired')),
      created_at_ms INTEGER NOT NULL,
      resolved_at_ms INTEGER
    ) STRICT`);
    store.execute(`INSERT INTO desktop_task_candidates (
      candidate_id, owner_id, source_session_id, source_run_id, action, task_ref,
      proposed_change_json, evidence_refs_json, confidence, requires_approval,
      status, created_at_ms, resolved_at_ms
    ) SELECT candidate_id, owner_id, source_session_id, source_run_id, action, task_ref,
             proposed_change_json, evidence_refs_json, confidence, requires_approval,
             status, created_at_ms, resolved_at_ms
      FROM desktop_task_candidates_future`);
    store.execute("DROP TABLE desktop_task_candidates_future");
    store.execute("DELETE FROM schema_migrations WHERE version = 13");
    store.close();

    store = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    expect(store.getRow("SELECT delivery_status, delivery_key, ownership_confidence, source_surface, account_generation FROM desktop_task_candidates WHERE candidate_id = ?", [legacy.candidateId])).toEqual({
      delivery_status: "blocked",
      delivery_key: legacy.candidateId,
      ownership_confidence: 0.75,
      source_surface: "desktop_agent",
      account_generation: 0,
    });
    const reconciled = reconcileLegacyTaskCandidateOutbox(store, { ownerId: "owner", accountGeneration: 7, nowMs: 100 });
    expect(reconciled).toEqual({ eligibleCandidateIds: [legacy.candidateId], terminalCandidateIds: [terminalLegacy.candidateId] });
    expect(store.getRow("SELECT delivery_status, account_generation, generation_reconciled FROM desktop_task_candidates WHERE candidate_id = ?", [legacy.candidateId])).toEqual({
      delivery_status: "pending",
      account_generation: 7,
      generation_reconciled: 1,
    });
    expect(store.getRow("SELECT delivery_status, status FROM desktop_task_candidates WHERE candidate_id = ?", [terminalLegacy.candidateId])).toEqual({
      delivery_status: "blocked",
      status: "rejected",
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM schema_migrations").count).toBe(13);
    store.close();
  });

  it("persists a bounded product-context packet with provenance and no transcript or run truth", () => {
    const store = newStore();
    const context = productContext({
      canonicalSummary: "s".repeat(9_000),
      selectedEvents: Array.from({ length: 25 }, (_, index) => ({
        eventId: `evt-${index}`,
        type: "task.changed",
        summary: `event ${index}`,
        occurredAtMs: index,
        evidenceRefs: [{ kind: "workstream_event", id: `evidence-${index}`, scope: "canonical" }],
      })),
    });

    const now = Date.now();
    const built = persistWorkstreamContextPacket(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      objective: "Continue the workstream",
      context,
      ttlMs: 60_000,
      nowMs: now,
    });
    const serialized = JSON.stringify(built.packet.packetJson);

    expect(serialized).toContain("snapshot-v1");
    expect(serialized).toContain("evt-24");
    expect(serialized).not.toContain("evt-0");
    expect(serialized).not.toMatch(/adapterNative|runStatus|full_transcript/);
    expect(JSON.stringify(built.packet.redactedPreviewJson)).not.toContain("Draft launch email");
    expect(JSON.stringify(built.packet.redactedPreviewJson)).toContain("[private workstream summary]");
    expect(built.accessLogs).toHaveLength(23);
    expect(store.allRows("SELECT * FROM desktop_context_packets")).toHaveLength(1);
    store.close();
  });

  it("enforces typed device-local provenance and verified sensitive-context approval", () => {
    const store = newStore();
    expect(() => persistWorkstreamContextPacket(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      objective: "Invalid local screen provenance",
      context: productContext({
        selectedEvents: [{
          eventId: "screen-1",
          type: "screen",
          summary: "Visible private content",
          occurredAtMs: 10,
          evidenceRefs: [{ kind: "local_screen", id: "screen-1", scope: "canonical" }],
        }],
      }),
      ttlMs: 60_000,
    })).toThrow(/local_screen EvidenceRef must be device_local/);

    const dispatch = store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "screen_context",
      priority: 50,
      title: "Allow sensitive context",
      decisionPrompt: "Use minimized screen evidence?",
      operation: "selected_workstream_event",
    });
    store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });
    const sensitiveContext = productContext({
      selectedEvents: [{
        eventId: "screen-2",
        type: "screen",
        summary: "Visible private content",
        redactedSummary: "Approved private screen summary",
        occurredAtMs: 11,
        sensitivityTier: "sensitive",
        policyDecision: "dispatch_created",
        dispatchId: dispatch.dispatchId,
        evidenceRefs: [{ kind: "local_screen", id: "screen-2", scope: "device_local", device_id: "mac-a" }],
      }],
    });
    expect(() => exportWorkstreamContinuationCheckpoint(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      sourceRuntimeId: "mac-a",
      context: sensitiveContext,
      ttlMs: 60_000,
    })).toThrow(/requires a dispatch id/);
    expect(() => persistWorkstreamContextPacket(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      objective: "Approved sensitive summary",
      context: sensitiveContext,
      ttlMs: 60_000,
    })).not.toThrow();
    const exportDispatch = store.insertDesktopDispatch({
      ownerId: "owner",
      kind: "screen_context",
      priority: 50,
      title: "Allow continuation export",
      decisionPrompt: "Export the redacted checkpoint?",
      operation: "export_workstream_continuation",
    });
    store.resolveDesktopDispatch(exportDispatch.dispatchId, {
      ownerId: "owner",
      status: "resolved",
      resolutionJson: JSON.stringify({ decision: "allow" }),
    });
    const exported = exportWorkstreamContinuationCheckpoint(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      sourceRuntimeId: "mac-a",
      context: sensitiveContext,
      ttlMs: 60_000,
      exportDispatchId: exportDispatch.dispatchId,
    });
    expect(exported.selectedEvents[0]).toMatchObject({
      summary: "Approved private screen summary",
      sensitivityTier: "private",
    });
    expect(exported.selectedEvents[0].dispatchId).toBeUndefined();
    store.close();
  });

  it("adds cited logical artifact versions atomically without overwriting history", () => {
    const store = newStore();
    const v1 = persistWorkstreamArtifactVersion(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      logicalKey: "email-draft",
      evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }],
      artifact: { kind: "markdown", role: "result", uri: "omi-artifact://draft-v1", contentHash: "sha256:v1" },
      nowMs: 10,
    });
    const v2 = persistWorkstreamArtifactVersion(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      logicalKey: "email-draft",
      evidenceRefs: [{ kind: "conversation", id: "conversation-2", scope: "canonical" }],
      artifact: { kind: "markdown", role: "result", uri: "omi-artifact://draft-v2", contentHash: "sha256:v2" },
      nowMs: 20,
    });

    expect(v1.version).toBe(1);
    expect(v2).toMatchObject({ version: 2, supersedesArtifactId: v1.artifact.artifactId });
    expect(store.allRows("SELECT artifact_id FROM artifacts ORDER BY created_at_ms")).toHaveLength(2);
    expect(store.getRow("SELECT artifact_id, version FROM workstream_artifact_heads")).toEqual({
      artifact_id: v2.artifact.artifactId,
      version: 2,
    });
    expect(JSON.parse(String(store.getRow("SELECT evidence_refs_json FROM workstream_artifact_versions WHERE version = 2").evidence_refs_json))).toEqual([
      { kind: "conversation", id: "conversation-2", scope: "canonical" },
    ]);
    store.close();
  });

  it("rejects uncited artifact versions and execution IDs owned by another session", () => {
    const store = newStore();
    const other = store.insertSession({ ownerId: "owner", surfaceKind: "other", defaultAdapterId: "acp" });
    const otherRun = store.insertRun({
      sessionId: other.sessionId,
      clientId: "client",
      requestId: "request",
      status: "succeeded",
      mode: "act",
    });
    expect(() => persistWorkstreamArtifactVersion(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      logicalKey: "draft",
      evidenceRefs: [],
      artifact: { kind: "markdown", role: "result", uri: "omi-artifact://uncited" },
    })).toThrow(/cited evidence/);
    expect(() => persistWorkstreamArtifactVersion(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      logicalKey: "draft",
      evidenceRefs: [{ kind: "conversation", id: "conv-1", scope: "canonical" }],
      artifact: { kind: "markdown", role: "result", uri: "omi-artifact://foreign", runId: otherRun.runId },
    })).toThrow(/does not belong/);
    const workstream = resolveWorkstreamSession(store, { ownerId: "owner", workstreamId: "ws-1" });
    const workstreamRun = store.insertRun({
      sessionId: workstream.agentSessionId,
      clientId: "client",
      requestId: "workstream-request",
      status: "succeeded",
      mode: "act",
    });
    const workstreamAttempt = store.insertAttempt({
      runId: workstreamRun.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "worker",
    });
    const attemptArtifact = persistWorkstreamArtifactVersion(store, {
      ownerId: "owner",
      workstreamId: "ws-1",
      logicalKey: "attempt-draft",
      evidenceRefs: [{ kind: "conversation", id: "conv-1", scope: "canonical" }],
      artifact: {
        kind: "markdown",
        role: "result",
        uri: "omi-artifact://attempt-result",
        attemptId: workstreamAttempt.attemptId,
      },
    });
    expect(attemptArtifact.artifact).toMatchObject({
      runId: workstreamRun.runId,
      attemptId: workstreamAttempt.attemptId,
    });
    store.close();
  });

  it("delivers an idempotent canonical Candidate, persists its receipt, and removes local review authority", async () => {
    const store = newStore();
    const session = resolveWorkstreamSession(store, { ownerId: "owner", workstreamId: "ws-1" }, () => 1);
    const local = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      sourceSessionId: session.agentSessionId,
      action: "delete",
      taskRef: "task-1",
      proposedChangeJson: JSON.stringify({ status: "cancelled" }),
      evidenceRefsJson: JSON.stringify([{ kind: "workstream_event", id: "event-1", scope: "canonical" }]),
      confidence: 0.8,
      ownershipConfidence: 0.9,
      requiresApproval: 1,
      workstreamRef: "ws-1",
      sourceSurface: "desktop_screen",
      accountGeneration: 7,
    });
    const payloads: CanonicalCandidatePayload[] = [];
    let fail = true;
    const transport = {
      createCandidate: async (payload: CanonicalCandidatePayload) => {
        payloads.push(payload);
        if (fail) {
          fail = false;
          throw new Error("offline");
        }
        return { candidateId: "backend-candidate-1", status: "pending" as const, receipt: { requestId: "req-1" } };
      },
    };

    await expect(deliverDesktopTaskCandidate(store, { ownerId: "owner", candidateId: local.candidateId, transport })).rejects.toThrow("offline");
    const delivered = await deliverDesktopTaskCandidate(store, { ownerId: "owner", candidateId: local.candidateId, transport });
    const replay = await deliverDesktopTaskCandidate(store, { ownerId: "owner", candidateId: local.candidateId, transport });

    expect(payloads).toHaveLength(2);
    expect(payloads[0]).toMatchObject({
      idempotencyKey: local.candidateId,
      accountGeneration: 7,
      proposal: {
        subject_kind: "task",
        proposed_action: "cancel",
        task_id: "task-1",
        task_change: { status: "cancelled" },
        capture_confidence: 0.8,
        ownership_confidence: 0.9,
        workstream_id: "ws-1",
        source_surface: "desktop_screen",
      },
    });
    expect(payloads[1].idempotencyKey).toBe(payloads[0].idempotencyKey);
    expect(delivered).toMatchObject({ status: "forwarded", deliveryStatus: "delivered", backendCandidateId: "backend-candidate-1" });
    expect(replay).toMatchObject({ backendCandidateId: "backend-candidate-1", deliveryAttemptCount: 2 });
    const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
    const queue = kernel.listDesktopActionQueue({ ownerId: "owner" });
    expect(queue).toEqual([]);

    const resolved = projectCanonicalCandidateResolution(store, {
      ownerId: "owner",
      backendCandidateId: "backend-candidate-1",
      status: "accepted",
      receipt: { resolutionId: "resolution-1" },
      nowMs: 500,
    });
    expect(resolved).toMatchObject({ status: "accepted", resolvedAtMs: 500 });
    expect(JSON.parse(resolved.backendReceiptJson!)).toEqual({ requestId: "req-1" });
    expect(JSON.parse(resolved.backendResolutionReceiptJson!)).toEqual({ resolutionId: "resolution-1" });

    const supersedePayloads: CanonicalCandidatePayload[] = [];
    const supersede = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      sourceSessionId: session.agentSessionId,
      action: "supersede",
      taskRef: "task-1",
      proposedChangeJson: JSON.stringify({ status: "superseded", superseded_by: "task-2" }),
      evidenceRefsJson: JSON.stringify([{ kind: "workstream_event", id: "event-2", scope: "canonical" }]),
      confidence: 0.9,
      requiresApproval: 1,
      accountGeneration: 7,
    });
    await deliverDesktopTaskCandidate(store, {
      ownerId: "owner",
      candidateId: supersede.candidateId,
      transport: {
        createCandidate: async (payload) => {
          supersedePayloads.push(payload);
          return { candidateId: "backend-candidate-2", status: "pending", receipt: { requestId: "req-2" } };
        },
      },
    });
    expect(supersedePayloads[0].proposal).toMatchObject({
      proposed_action: "supersede",
      task_id: "task-1",
      task_change: { status: "superseded", superseded_by: "task-2" },
    });
    store.close();
  });

  it("marks interrupted Candidate deliveries retryable during startup reconciliation", () => {
    const path = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    const candidate = store.insertDesktopTaskCandidate({
      ownerId: "owner",
      action: "create",
      proposedChangeJson: "{}",
      evidenceRefsJson: "[]",
      confidence: 0.7,
      requiresApproval: 1,
      deliveryStatus: "delivering",
    });
    store.execute(
      `INSERT INTO workstream_continuation_checkpoints (
         owner_id, workstream_id, source_runtime_id, checkpoint_id, checkpoint_json,
         last_event_sequence, expires_at_ms, created_at_ms, updated_at_ms
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ["owner", "ws-1", "mac-a", "checkpoint-expired", "{}", 0, 600, 500, 500],
    );
    store.close();

    store = new SqliteAgentStore({ databasePath: path, nowMs: () => 700 });
    expect(store.getRow("SELECT delivery_status, last_delivery_error_json FROM desktop_task_candidates WHERE candidate_id = ?", [candidate.candidateId])).toMatchObject({
      delivery_status: "failed",
      last_delivery_error_json: JSON.stringify({ reason: "daemon_startup_reconciliation" }),
    });
    expect(store.allRows("SELECT * FROM workstream_continuation_checkpoints")).toEqual([]);
    store.close();
  });

  it("exports product continuity to another runtime without copying transcript or local run status", () => {
    const source = newStore();
    const target = newStore();
    const now = Date.now();
    const checkpoint = exportWorkstreamContinuationCheckpoint(source, {
      ownerId: "owner",
      workstreamId: "ws-1",
      sourceRuntimeId: "mac-a",
      context: productContext(),
      ttlMs: 60_000,
      nowMs: now,
    });
    exportWorkstreamContinuationCheckpoint(source, {
      ownerId: "owner",
      workstreamId: "ws-1",
      sourceRuntimeId: "mac-a",
      context: productContext({ latestEventSequence: 5 }),
      ttlMs: 60_000,
      nowMs: now + 100,
    });
    expect(readWorkstreamContinuationCheckpoint(source, { ownerId: "owner", workstreamId: "ws-1", nowMs: now + 200 })?.lastEventSequence).toBe(11);
    const imported = importWorkstreamContinuationCheckpoint(target, checkpoint, { targetRuntimeId: "mac-b", nowMs: now + 1_000 });
    const serialized = JSON.stringify(checkpoint);

    expect(imported.agentSessionId).toMatch(/^ses_/);
    expect(serialized).not.toMatch(/conversationTurn|adapterNative|runStatus|attemptStatus/);
    expect(target.allRows("SELECT * FROM runs")).toEqual([]);
    expect(target.allRows("SELECT * FROM desktop_context_packets")).toHaveLength(1);
    expect(target.getRow("SELECT source_runtime_id FROM workstream_continuation_checkpoints").source_runtime_id).toBe("mac-a");
    expect(readWorkstreamContinuationCheckpoint(target, { ownerId: "owner", workstreamId: "ws-1", nowMs: now + 1_000 })?.lastEventSequence).toBe(11);
    expect(target.getRow("SELECT type FROM events").type).toBe("workstream.continuation_imported");
    source.close();
    target.close();
  });

  it("builds an expiring device-scoped open-loop snapshot without queue ranks or priorities", () => {
    const snapshot = buildWorkstreamOpenLoopSnapshot({
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      nowMs: 1_000,
      ttlMs: 30_000,
      actionQueue: [{
        itemId: "failed_run:run:1",
        kind: "failed_run",
        subjectKind: "run",
        subjectId: "1",
        ownerId: "owner",
        title: "Recover draft",
        priority: 99,
        rank: 1,
        createdAtMs: 500,
        sourceSessionId: "session-1",
        sourceRunId: "run-1",
        reason: "Interrupted",
      }],
      sessionWorkstreamIds: new Map([["session-1", "ws-1"]]),
    });

    expect(snapshot).toMatchObject({ deviceScoped: true, generatedAtMs: 1_000, expiresAtMs: 31_000 });
    expect(snapshot.loops[0]).toMatchObject({ workstreamId: "ws-1", subjectId: "1" });
    expect(JSON.stringify(snapshot)).not.toMatch(/"rank"|"priority"/);
  });

  it("migrates task chat compatibility mappings and turns into one canonical workstream conversation", () => {
    const store = newStore();
    const task = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "task_chat", externalRefKind: "task", externalRefId: "task-1" },
    }, () => 1);
    store.insertConversationTurn({
      conversationId: task.conversationId,
      role: "user",
      surfaceKind: "task_chat",
      content: "Draft the email",
      createdAtMs: 2,
    });
    const legacyArtifact = store.insertArtifact({
      sessionId: task.agentSessionId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://legacy-draft",
      contentHash: "a".repeat(64),
    });
    const legacyBinding = store.insertAdapterBinding({
      sessionId: task.agentSessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-task-1",
      resumeFidelity: "native",
      status: "active",
    });
    const taskTwo = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "task_chat", externalRefKind: "task", externalRefId: "task-2" },
    }, () => 2);
    store.insertConversationTurn({
      conversationId: taskTwo.conversationId,
      role: "assistant",
      surfaceKind: "task_chat",
      content: "Initial research",
      createdAtMs: 2,
    });

    const report = migrateTaskSessionsToWorkstreams(store, {
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      mappings: [
        { taskId: "task-1", workstreamId: "ws-1" },
        { taskId: "task-2", workstreamId: "ws-1" },
      ],
      nowMs: 3,
    });
    const canonical = resolveWorkstreamSession(store, { ownerId: "owner", workstreamId: "ws-1" }, () => 4);
    const taskMappings = store.allRows("SELECT conversation_id, agent_session_id FROM surface_conversations WHERE external_ref_kind = 'task'");

    expect(report).toMatchObject({
      migratedTaskMappings: 2,
      copiedTurns: 2,
      migratedArtifacts: 1,
      indexedArtifactVersions: 1,
      repairedArtifactHeads: 1,
      skippedMappings: 0,
      invalidatedBindingIds: [legacyBinding.bindingId],
    });
    expect(taskMappings).toEqual([
      { conversation_id: canonical.conversationId, agent_session_id: canonical.agentSessionId },
      { conversation_id: canonical.conversationId, agent_session_id: canonical.agentSessionId },
    ]);
    expect(store.getRow("SELECT content FROM conversation_turns WHERE conversation_id = ?", [canonical.conversationId]).content).toBe("Draft the email");
    expect(store.getRow("SELECT status FROM adapter_bindings WHERE binding_id = ?", [legacyBinding.bindingId]).status).toBe("stale");
    expect(store.getRow("SELECT metadata_json FROM artifacts WHERE session_id = ? AND artifact_id != ?", [canonical.agentSessionId, legacyArtifact.artifactId]).metadata_json).toContain(legacyArtifact.artifactId);
    const version = store.getRow(
      "SELECT * FROM workstream_artifact_versions WHERE session_id = ?",
      [canonical.agentSessionId],
    );
    expect(version).toMatchObject({ version: 1 });
    expect(store.getRow(
      "SELECT artifact_id, version FROM workstream_artifact_heads WHERE session_id = ?",
      [canonical.agentSessionId],
    )).toMatchObject({ artifact_id: version.artifact_id, version: 1 });
    expect(projectWorkstreamContinuity(store, { ownerId: "owner", workstreamId: "ws-1" }).artifactVersions)
      .toHaveLength(1);
    expect(store.getRow(
      "SELECT delivery_status, receipt_json FROM desktop_artifact_deliveries WHERE artifact_id = ?",
      [version.artifact_id],
    )).toMatchObject({ delivery_status: "pending" });
    const rerun = migrateTaskSessionsToWorkstreams(store, {
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      mappings: [
        { taskId: "task-1", workstreamId: "ws-1" },
        { taskId: "task-2", workstreamId: "ws-1" },
      ],
      nowMs: 4,
    });
    expect(rerun).toMatchObject({
      migratedTaskMappings: 0,
      migratedArtifacts: 0,
      indexedArtifactVersions: 0,
      repairedArtifactHeads: 0,
      skippedMappings: 2,
    });
    store.close();
  });

  it("repairs legacy artifacts copied before version indexing without duplicating history", () => {
    const store = newStore();
    const canonical = resolveWorkstreamSession(store, { ownerId: "owner", workstreamId: "ws-1" }, () => 1);
    const copied = store.insertArtifact({
      artifactId: "artifact-copied-by-old-migration",
      sessionId: canonical.agentSessionId,
      kind: "markdown",
      role: "result",
      uri: "omi-artifact://legacy-draft",
      contentHash: "sha256:legacy",
      metadataJson: JSON.stringify({
        migratedFromArtifactId: "legacy-artifact-1",
        migratedFromSessionId: "legacy-session-1",
      }),
      createdAtMs: 2,
    });

    const repaired = migrateTaskSessionsToWorkstreams(store, {
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      mappings: [{ taskId: "missing-task", workstreamId: "ws-1" }],
      nowMs: 3,
    });
    expect(repaired).toMatchObject({ indexedArtifactVersions: 1, repairedArtifactHeads: 1 });
    expect(store.allRows(
      "SELECT * FROM events WHERE session_id = ? AND type = 'workstream.artifact_version_migrated'",
      [canonical.agentSessionId],
    )).toHaveLength(1);

    store.execute("DELETE FROM workstream_artifact_heads WHERE artifact_id = ?", [copied.artifactId]);
    const headRepair = migrateTaskSessionsToWorkstreams(store, {
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      mappings: [{ taskId: "missing-task", workstreamId: "ws-1" }],
      nowMs: 4,
    });
    expect(headRepair).toMatchObject({ indexedArtifactVersions: 0, repairedArtifactHeads: 1 });
    const replay = migrateTaskSessionsToWorkstreams(store, {
      ownerId: "owner",
      sourceRuntimeId: "mac-a",
      mappings: [{ taskId: "missing-task", workstreamId: "ws-1" }],
      nowMs: 5,
    });
    expect(replay).toMatchObject({ indexedArtifactVersions: 0, repairedArtifactHeads: 0 });
    expect(store.allRows("SELECT * FROM workstream_artifact_versions WHERE artifact_id = ?", [copied.artifactId]))
      .toHaveLength(1);
    expect(store.allRows("SELECT * FROM desktop_artifact_deliveries WHERE artifact_id = ?", [copied.artifactId]))
      .toHaveLength(1);
    expect(store.getRow(
      "SELECT delivery_status FROM desktop_artifact_deliveries WHERE artifact_id = ?",
      [copied.artifactId],
    )).toMatchObject({ delivery_status: "cancelled" });
    expect(store.allRows(
      "SELECT * FROM events WHERE session_id = ? AND type = 'workstream.artifact_version_migrated'",
      [canonical.agentSessionId],
    )).toHaveLength(1);
    store.close();
  });

  it("publishes the continuity APIs through AgentRuntimeKernel", () => {
    const store = newStore();
    const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry(), runtimeNodeId: "mac-a" });
    const resolved = kernel.resolveWorkstreamSession({ ownerId: "owner", workstreamId: "ws-1" });
    store.insertRun({
      sessionId: resolved.agentSessionId,
      clientId: "client",
      requestId: "request",
      status: "failed",
      mode: "act",
      inputJson: JSON.stringify({ prompt: "Prepare draft" }),
    });
    const snapshot = kernel.buildWorkstreamOpenLoopSnapshot({ ownerId: "owner", nowMs: 10 });
    const publicOpenLoops = kernel.getDesktopOpenLoops({ ownerId: "owner" });
    expect(resolved.agentSessionId).toMatch(/^ses_/);
    expect(snapshot).toMatchObject({ sourceRuntimeId: "mac-a", generatedAtMs: 10 });
    expect(publicOpenLoops.loops).toHaveLength(1);
    expect(JSON.stringify(publicOpenLoops)).not.toMatch(/"rank"|"priority"/);
    store.close();
  });
});

function productContext(overrides: Partial<WorkstreamProductContext> = {}): WorkstreamProductContext {
  return {
    canonicalSummary: "Prepare the launch email",
    latestEventSequence: 11,
    selectedEvents: [{ eventId: "evt-1", type: "conversation", summary: "Launch moved to Friday", redactedSummary: "Schedule changed", occurredAtMs: 10, evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }] }],
    currentTask: { taskId: "task-1", title: "Draft launch email", status: "open", summary: "Use Friday" },
    artifactHeads: [{ logicalKey: "email-draft", artifactId: "art-1", version: 2, evidenceRefs: [{ kind: "conversation", id: "conversation-1", scope: "canonical" }] }],
    provenance: { snapshotVersion: "snapshot-v1", fetchedAtMs: 20, source: "omi-backend" },
    ...overrides,
  };
}

function newStore(): SqliteAgentStore {
  return new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
}

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-workstream-continuity-"));
  dirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}
