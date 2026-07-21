import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import type { OutboundMessageDraft, QueryMessage } from "../src/protocol.js";
import { JsonlTransport, type McpServerBuilder } from "../src/runtime/jsonl-transport.js";
import { updateContextSource } from "../src/runtime/context-snapshot.js";
import { recordJournalTurn, terminalizeJournalTurn } from "../src/runtime/conversation-journal.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function fixture(buildMcpServers?: McpServerBuilder) {
  const root = mkdtempSync(join(tmpdir(), "omi-jsonl-"));
  roots.push(root);
  const { store, adapter, kernel } = createKernelHarness(join(root, "agent.sqlite"), "fake");
  const session = store.insertSession({
    ownerId: "owner",
    surfaceKind: "main_chat",
    externalRefKind: "chat",
    externalRefId: "default",
    defaultAdapterId: "fake",
    defaultCwd: "/tmp/pinned-workspace",
    modelProfile: "pinned-model",
  });
  const sent: OutboundMessageDraft[] = [];
  let activeOwner = "owner";
  const transport = new JsonlTransport({
    kernel,
    ownerId: "owner",
    defaultAdapterId: "fake",
    activeOwnerId: () => activeOwner,
    send: (message) => sent.push(message),
    buildMcpServers,
  });
  return {
    store,
    adapter,
    kernel,
    session,
    sent,
    transport,
    setActiveOwner: (owner: string) => { activeOwner = owner; },
  };
}

function query(sessionId: string, overrides: Partial<QueryMessage> = {}): QueryMessage {
  return {
    type: "query",
    protocolVersion: 2,
    requestId: "request-1",
    clientId: "client-1",
    ownerId: "owner",
    sessionId,
    prompt: "hello",
    mode: "act",
    ...overrides,
  };
}

describe("JsonlTransport kernel-owned query contract", () => {
  it("accepts the reasoningEffort wire field and threads it into run metadata", async () => {
    const { store, session, transport } = fixture();
    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-effort",
      reasoningEffort: "adaptive",
    }));
    const row = store.getRow(
      "SELECT input_json FROM runs WHERE request_id = ?",
      ["request-effort"],
    );
    const input = JSON.parse(String(row.input_json));
    expect(input.metadata.reasoningEffort).toBe("adaptive");

    // A query without the field keeps legacy metadata (no key at all).
    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-no-effort",
    }));
    const legacy = store.getRow(
      "SELECT input_json FROM runs WHERE request_id = ?",
      ["request-no-effort"],
    );
    expect("reasoningEffort" in JSON.parse(String(legacy.input_json)).metadata).toBe(false);
  });

  it("binds the producing turn to the exact admitted run attempt before execution returns", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    const conversationId = "conv-query-admission";
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId,
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-admitted-r1",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "Working R1",
      contentBlocks: [],
      createdAtMs: 2,
    });
    await transport.handleInterrupt({
      requestId: "request-admitted-r1",
      clientId: "client-1",
      ownerId: session.ownerId,
    });
    expect(sent.at(-1)).toMatchObject({ type: "cancel_ack", accepted: false });
    expect(store.getRow(
      "SELECT producing_run_id, producing_attempt_id FROM conversation_turns WHERE turn_id = ?",
      ["turn-admitted-r1"],
    )).toEqual({ producing_run_id: null, producing_attempt_id: null });
    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-admitted-r1",
      producingTurnId: "turn-admitted-r1",
    }));
    const r1 = store.getRow(
      `SELECT r.run_id, a.attempt_id
       FROM runs r JOIN run_attempts a ON a.run_id = r.run_id
       WHERE r.request_id = ?`,
      ["request-admitted-r1"],
    );
    expect(store.getRow(
      `SELECT producing_run_id, producing_attempt_id, status
       FROM conversation_turns WHERE turn_id = ?`,
      ["turn-admitted-r1"],
    )).toEqual({
      producing_run_id: r1.run_id,
      producing_attempt_id: r1.attempt_id,
      status: "streaming",
    });

    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-admitted-r2",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "Working R2",
      contentBlocks: [],
      createdAtMs: 3,
    });
    adapter.deferResult();
    const r2Pending = transport.handleQuery(query(session.sessionId, {
      requestId: "request-admitted-r2",
      producingTurnId: "turn-admitted-r2",
    }));
    await waitUntil(() => store.getRow(
      "SELECT producing_run_id FROM conversation_turns WHERE turn_id = ?",
      ["turn-admitted-r2"],
    ).producing_run_id != null);
    const r2 = store.getRow(
      `SELECT producing_run_id, producing_attempt_id
       FROM conversation_turns WHERE turn_id = ?`,
      ["turn-admitted-r2"],
    );
    expect(r2.producing_run_id).not.toBe(r1.run_id);
    expect(() => terminalizeJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-admitted-r2",
      producingRunId: String(r1.run_id),
      producingAttemptId: String(r1.attempt_id),
      disposition: "accept",
    })).toThrow(/run does not match the producing turn/i);
    expect(store.getRow(
      "SELECT status, content FROM conversation_turns WHERE turn_id = ?",
      ["turn-admitted-r2"],
    )).toEqual({ status: "streaming", content: "Working R2" });
    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "R2 result" });
    await r2Pending;
    store.close();
  });

  it("rejects a producing turn from a different canonical session before run mutation", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId: "conv-query-owner-session",
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    const otherSession = store.insertSession({
      ownerId: session.ownerId,
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "other-task",
      defaultAdapterId: "fake",
    });
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "other-task",
      conversationId: "conv-query-other-session",
      agentSessionId: otherSession.sessionId,
      createdAtMs: 2,
      lastActiveAtMs: 2,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId: "conv-query-other-session",
      turnId: "turn-forged-other-session",
      role: "assistant",
      surfaceKind: "task_chat",
      origin: "task_chat",
      status: "pending",
      content: "Must remain unbound",
      contentBlocks: [],
      createdAtMs: 3,
    });

    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-forged-other-session",
      producingTurnId: "turn-forged-other-session",
    }));
    expect(sent.at(-1)).toMatchObject({ type: "error", failure: { code: "runtime_query_failed" } });
    expect(adapter.executed).toHaveLength(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(0);
    expect(store.getRow(
      "SELECT producing_run_id, producing_attempt_id FROM conversation_turns WHERE turn_id = ?",
      ["turn-forged-other-session"],
    )).toEqual({ producing_run_id: null, producing_attempt_id: null });
    store.close();
  });

  it("advances producing authority to a recovered second attempt and rejects attempt one", async () => {
    const { store, adapter, session, transport } = fixture();
    const conversationId = "conv-query-retry";
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId,
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-query-retry",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "Retrying",
      contentBlocks: [],
      createdAtMs: 2,
    });
    adapter.failNextExecutionAsStale = true;
    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-query-retry",
      producingTurnId: "turn-query-retry",
    }));
    const run = store.getRow("SELECT run_id FROM runs WHERE request_id = ?", ["request-query-retry"]);
    const attempts = store.allRows(
      "SELECT attempt_id, attempt_no, status FROM run_attempts WHERE run_id = ? ORDER BY attempt_no",
      [run.run_id],
    );
    expect(attempts).toMatchObject([
      { attempt_no: 1, status: "failed" },
      { attempt_no: 2, status: "succeeded" },
    ]);
    expect(store.getRow(
      "SELECT producing_run_id, producing_attempt_id FROM conversation_turns WHERE turn_id = ?",
      ["turn-query-retry"],
    )).toEqual({
      producing_run_id: run.run_id,
      producing_attempt_id: attempts[1]!.attempt_id,
    });
    expect(() => terminalizeJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-query-retry",
      producingRunId: String(run.run_id),
      producingAttemptId: String(attempts[0]!.attempt_id),
      disposition: "accept",
    })).toThrow(/latest canonical run attempt/i);
    expect(terminalizeJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-query-retry",
      producingRunId: String(run.run_id),
      producingAttemptId: String(attempts[1]!.attempt_id),
      disposition: "accept",
    })).toMatchObject({ status: "completed", producingAttemptId: attempts[1]!.attempt_id });
    store.close();
  });

  it("discards an admission-bound producing turn on cancellation and ignores late success", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    const conversationId = "conv-query-cancel";
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId,
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-query-cancel",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "Working before cancel",
      contentBlocks: [{ type: "text", id: "cancel:text", text: "Working before cancel" }],
      createdAtMs: 2,
    });
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId, {
      requestId: "request-query-cancel",
      producingTurnId: "turn-query-cancel",
    }));
    await waitUntil(() => adapter.executed.length === 1);

    await transport.handleInterrupt({
      requestId: "request-query-cancel",
      clientId: "client-1",
      ownerId: session.ownerId,
    });
    expect(store.getRow(
      "SELECT status, content FROM conversation_turns WHERE turn_id = ?",
      ["turn-query-cancel"],
    )).toEqual({ status: "failed", content: "Working before cancel" });
    expect(store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-query-cancel"],
    )).toEqual({ status: "failed", last_error_code: "discarded_terminal_projection" });

    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late result must not resurrect" });
    await running;
    expect(store.getRow(
      "SELECT status, content FROM conversation_turns WHERE turn_id = ?",
      ["turn-query-cancel"],
    )).toEqual({ status: "failed", content: "Working before cancel" });
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toEqual({
      status: "cancelled",
      final_text: null,
    });
    expect(sent.findLast((message) => message.type === "result")).toMatchObject({
      type: "result",
      terminalStatus: "cancelled",
      failure: { code: "run_cancelled" },
    });
    expect(sent.filter((message) => message.type === "error")).toEqual([]);
    store.close();
  });

  it("returns correlated failed results for adapter errors and missing terminal status", async () => {
    for (const outcome of ["throw", "missing_status"] as const) {
      const { store, adapter, session, sent, transport } = fixture();
      if (outcome === "throw") {
        adapter.failNextExecutionError = new Error("adapter exploded");
        await transport.handleQuery(query(session.sessionId, { requestId: `request-${outcome}` }));
      } else {
        adapter.deferResult();
        const pending = transport.handleQuery(query(session.sessionId, { requestId: `request-${outcome}` }));
        await waitUntil(() => adapter.executed.length === 1);
        adapter.resolveDeferred({ terminalStatus: undefined as never });
        await pending;
      }
      const result = sent.findLast((message) => message.type === "result");
      expect(result).toMatchObject({
        type: "result",
        requestId: `request-${outcome}`,
        clientId: "client-1",
        terminalStatus: "failed",
        failure: { code: expect.stringMatching(/^[a-z0-9_.:-]{1,64}$/i) },
      });
      const failure = result && "failure" in result ? result.failure : undefined;
      expect(failure?.userMessage.length).toBeLessThanOrEqual(1_000);
      expect(sent.filter((message) => message.type === "error")).toEqual([]);
      store.close();
    }
  });

  it("fails and discards an admitted producing turn when an unexpected post-bind step throws", async () => {
    const { store, adapter, kernel, session, sent, transport } = fixture();
    const conversationId = "conv-query-post-bind-failure";
    store.insertSurfaceConversation({
      ownerId: session.ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId,
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    recordJournalTurn(store, {
      ownerId: session.ownerId,
      conversationId,
      turnId: "turn-post-bind-failure",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "streaming",
      content: "Bound before failure",
      contentBlocks: [],
      createdAtMs: 2,
    });
    const capabilityBroker = (kernel as unknown as {
      toolCapabilities: { register: (...args: unknown[]) => unknown };
    }).toolCapabilities;
    capabilityBroker.register = () => {
      throw new Error("injected post-bind capability failure");
    };

    await transport.handleQuery(query(session.sessionId, {
      requestId: "request-post-bind-failure",
      producingTurnId: "turn-post-bind-failure",
    }));
    expect(adapter.executed).toHaveLength(0);
    expect(store.getRow("SELECT status, error_code FROM runs LIMIT 1")).toEqual({
      status: "failed",
      error_code: "post_admission_execution_failed",
    });
    expect(store.getRow("SELECT status, error_code FROM run_attempts LIMIT 1")).toEqual({
      status: "failed",
      error_code: "post_admission_execution_failed",
    });
    expect(store.getRow(
      "SELECT status, metadata_json FROM conversation_turns WHERE turn_id = ?",
      ["turn-post-bind-failure"],
    )).toMatchObject({ status: "failed" });
    expect(JSON.parse(String(store.getRow(
      "SELECT metadata_json FROM conversation_turns WHERE turn_id = ?",
      ["turn-post-bind-failure"],
    ).metadata_json))).toMatchObject({ terminalMarker: "discarded_terminal_projection" });
    expect(store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-post-bind-failure"],
    )).toEqual({ status: "failed", last_error_code: "discarded_terminal_projection" });
    expect(sent.findLast((message) => message.type === "error")).toMatchObject({
      type: "error",
      failure: { code: "runtime_query_failed" },
    });
    store.close();
  });
  it("requires a canonical session and uses its pinned adapter/model/cwd", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    await transport.handleQuery(query(session.sessionId));

    expect(adapter.opened).toHaveLength(1);
    expect(adapter.opened[0]).toMatchObject({
      cwd: "/tmp/pinned-workspace",
      model: "pinned-model",
    });
    expect(adapter.opened[0].systemPrompt).toContain("desktop kernel is the authority");
    expect(sent.at(-1)).toMatchObject({
      type: "result",
      requestId: "request-1",
      clientId: "client-1",
      sessionId: session.sessionId,
    });
    store.close();
  });

  it("rejects every removed query authority field before adapter dispatch", async () => {
    const { store, adapter, session, transport } = fixture();
    const legacy = {
      ...query(session.sessionId),
      adapterId: "attacker-adapter",
      model: "attacker-model",
      cwd: "/tmp/attacker",
      systemPrompt: "attacker policy",
      surfaceContextJson: "attacker context",
    } as unknown as QueryMessage;
    await expect(transport.handleQuery(legacy)).rejects.toThrow("query_wire_field_not_allowed:adapterId");
    expect(adapter.opened).toHaveLength(0);
    expect(adapter.executed).toHaveLength(0);

    for (const field of [
      "runId", "attemptId", "eventId", "surfaceKind", "surfaceContextJson", "systemPrompt", "cwd", "model",
    ] as const) {
      await expect(transport.handleQuery({
        ...query(session.sessionId),
        [field]: "forged",
      } as unknown as QueryMessage)).rejects.toThrow(`query_wire_field_not_allowed:${field}`);
    }
    store.close();
  });

  it("rejects a stale expected snapshot pair without dispatching an adapter", async () => {
    const { store, adapter, kernel, session, sent, transport } = fixture();
    const snapshot = kernel.contextSnapshot(session.sessionId, session.ownerId);
    updateContextSource(store, {
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      source: "memories",
      sourceRevision: "1",
      outcome: "available",
      capturedAtMs: 10,
      payload: { items: [{ id: "m1", text: "new" }] },
    }, 10);

    await expect(transport.handleQuery(query(session.sessionId, {
      expectedContextSnapshotVersion: snapshot.version,
      expectedContextSnapshotGeneration: snapshot.snapshotGeneration,
      expectedContextRendererFingerprint: snapshot.rendererFingerprint,
      expectedCapabilityVersion: snapshot.capabilityVersion,
    }))).rejects.toThrow("context_snapshot_projection_mismatch");
    expect(adapter.executed).toHaveLength(0);
    expect(sent).toEqual([]);
    store.close();
  });

  it("pins the validated admission snapshot when MCP construction changes a context source", async () => {
    let storeForBuilder: ReturnType<typeof fixture>["store"];
    let sessionForBuilder: ReturnType<typeof fixture>["session"];
    const buildMcpServers: McpServerBuilder = () => {
      updateContextSource(storeForBuilder, {
        ownerId: sessionForBuilder.ownerId,
        sessionId: sessionForBuilder.sessionId,
        source: "memories",
        sourceRevision: "after-validation",
        outcome: "available",
        capturedAtMs: 20,
        payload: { items: [{ id: "m-after", text: "MUTATED_AFTER_VALIDATION" }] },
      }, 20);
      return [];
    };
    const { store, adapter, kernel, session, transport } = fixture(buildMcpServers);
    storeForBuilder = store;
    sessionForBuilder = session;
    updateContextSource(store, {
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      source: "memories",
      sourceRevision: "before-validation",
      outcome: "available",
      capturedAtMs: 10,
      payload: { items: [{ id: "m-before", text: "ORIGINAL_ADMITTED_CONTEXT" }] },
    }, 10);
    const admitted = kernel.contextSnapshot(session.sessionId, session.ownerId);

    await transport.handleQuery(query(session.sessionId, {
      requestId: "snapshot-race",
      expectedContextSnapshotVersion: admitted.version,
      expectedContextSnapshotGeneration: admitted.snapshotGeneration,
      expectedContextRendererFingerprint: admitted.rendererFingerprint,
      expectedCapabilityVersion: admitted.capabilityVersion,
    }));

    expect(adapter.executed).toHaveLength(1);
    const prompt = adapter.executed[0].prompt
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    expect(prompt).toContain("ORIGINAL_ADMITTED_CONTEXT");
    expect(prompt).not.toContain("MUTATED_AFTER_VALIDATION");
    const runInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE request_id = ?",
      ["snapshot-race"],
    ).input_json));
    expect(runInput.contextSnapshotVersion).toBe(admitted.version);
    expect(runInput.contextSnapshotGeneration).toBe(admitted.snapshotGeneration);
    expect(runInput.admittedContextSnapshot.sourceOutcomes).toContainEqual(
      expect.objectContaining({ source: "memories", sourceRevision: "before-validation" }),
    );
    expect(kernel.contextSnapshot(session.sessionId, session.ownerId).sourceOutcomes).toContainEqual(
      expect.objectContaining({ source: "memories", sourceRevision: "after-validation" }),
    );
    store.close();
  });

  it("validates warmup against only the pinned session/profile identity", () => {
    const { store, session, transport } = fixture();
    expect(() => transport.handleWarmup({
      type: "warmup",
      protocolVersion: 2,
      requestId: "warmup-1",
      clientId: "client-1",
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      profileGeneration: 1,
    })).not.toThrow();
    expect(() => transport.handleWarmup({
      type: "warmup",
      protocolVersion: 2,
      requestId: "warmup-2",
      clientId: "client-1",
      ownerId: session.ownerId,
      sessionId: session.sessionId,
      profileGeneration: 2,
    })).toThrow(/does not match/);
    store.close();
  });

  it("rejects a forged wrong-owner invalidation before mutating that owner's binding", () => {
    const { store, transport } = fixture();
    const ownerBSession = store.insertSession({
      ownerId: "owner-b",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "owner-b-chat",
      defaultAdapterId: "fake",
    });
    const binding = store.insertAdapterBinding({
      sessionId: ownerBSession.sessionId,
      adapterId: "fake",
      bindingGeneration: 1,
      adapterNativeSessionId: "owner-b-native",
      adapterInstanceId: "owner-b-worker",
      resumeFidelity: "native",
      status: "active",
    });

    expect(() => transport.handleInvalidateSession({
      type: "invalidate_session",
      protocolVersion: 2,
      requestId: "forged-owner-b-invalidate",
      clientId: "client-1",
      ownerId: "owner-b",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "owner-b-chat",
    })).toThrow(/owner_mismatch/);
    expect(store.getRow(
      "SELECT status FROM adapter_bindings WHERE binding_id = ?",
      [binding.bindingId],
    ).status).toBe("active");
    store.close();
  });

  it("rejects an owner-A invalidation that arrives after the runtime transitions to owner B", () => {
    const { store, session, transport, setActiveOwner } = fixture();
    const binding = store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "fake",
      bindingGeneration: 1,
      adapterNativeSessionId: "owner-a-native",
      adapterInstanceId: "owner-a-worker",
      resumeFidelity: "native",
      status: "active",
    });
    const staleMessage = {
      type: "invalidate_session" as const,
      protocolVersion: 2 as const,
      requestId: "stale-owner-a-invalidate",
      clientId: "client-1",
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };

    setActiveOwner("owner-b");
    expect(() => transport.handleInvalidateSession(staleMessage)).toThrow(/owner_mismatch/);
    expect(store.getRow(
      "SELECT status FROM adapter_bindings WHERE binding_id = ?",
      [binding.bindingId],
    ).status).toBe("active");
    store.close();
  });

  it("derives cancellation authority from the persisted run owner", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId));
    await waitUntil(() => adapter.executed.length === 1);
    const run = store.getRow("SELECT run_id FROM runs WHERE session_id = ?", [session.sessionId]);

    await transport.handleInterrupt({
      requestId: "request-1",
      clientId: "client-1",
      ownerId: "owner",
      runId: String(run.run_id),
    });
    expect(adapter.cancelled).toHaveLength(1);
    expect(sent.findLast((message) => message.type === "cancel_ack")).toMatchObject({
      accepted: true,
      dispatchAttempted: true,
    });
    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await running;
    store.close();
  });

  it("rejects wrong-owner cancellation before dispatching a transport mutation", async () => {
    const { store, adapter, session, transport } = fixture();
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId));
    await waitUntil(() => adapter.executed.length === 1);
    const run = store.getRow("SELECT run_id FROM runs WHERE session_id = ?", [session.sessionId]);

    await expect(transport.handleInterrupt({
      requestId: "request-1",
      clientId: "client-1",
      ownerId: "owner-b",
      runId: String(run.run_id),
    })).rejects.toThrow(/owner_mismatch/);
    expect(adapter.cancelled).toHaveLength(0);

    adapter.resolveDeferred({ terminalStatus: "succeeded" });
    await running;
    store.close();
  });

  it("rejects cancellation after the active runtime owner changes", async () => {
    const { store, adapter, session, sent, transport, setActiveOwner } = fixture();
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId));
    await waitUntil(() => adapter.executed.length === 1);
    const run = store.getRow("SELECT run_id FROM runs WHERE session_id = ?", [session.sessionId]);
    setActiveOwner("owner-2");

    await transport.handleInterrupt({
      requestId: "request-1",
      clientId: "client-1",
      runId: String(run.run_id),
    });
    expect(adapter.cancelled).toHaveLength(0);
    expect(sent.findLast((message) => message.type === "cancel_ack")).toMatchObject({ accepted: false });
    setActiveOwner("owner");
    adapter.resolveDeferred({ terminalStatus: "cancelled" });
    await running;
    store.close();
  });

  it("terminalizes owner A before owner B admission and drops deferred adapter success", async () => {
    const { store, adapter, session, sent, transport, setActiveOwner } = fixture();
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId));
    await waitUntil(() => adapter.executed.length === 1);
    sent.splice(0);

    expect(transport.revokeOwner("owner", "owner_changed")).toHaveLength(1);
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    setActiveOwner("owner-b");

    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late owner A success" });
    await running;
    expect(sent).toEqual([]);
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE content LIKE '%late owner A success%'",
    ).count).toBe(0);
    store.close();
  });

  it("clear-owner revocation terminalizes foreground work even when the adapter ignores abort", async () => {
    const { store, adapter, session, sent, transport, setActiveOwner } = fixture();
    adapter.deferResult();
    const running = transport.handleQuery(query(session.sessionId));
    await waitUntil(() => adapter.executed.length === 1);
    sent.splice(0);

    setActiveOwner("");
    expect(transport.revokeOwner("owner", "owner_state_cleared")).toHaveLength(1);
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });

    adapter.resolveDeferred({ terminalStatus: "succeeded", text: "late cleared-owner success" });
    await running;
    expect(sent).toEqual([]);
    expect(store.getRow("SELECT status, final_text FROM runs LIMIT 1")).toMatchObject({
      status: "cancelled",
      final_text: null,
    });
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE content LIKE '%late cleared-owner success%'",
    ).count).toBe(0);
    store.close();
  });

  it("keeps overlapping request correlation isolated while sharing one pinned session", async () => {
    const { store, adapter, session, sent, transport } = fixture();
    const first = transport.handleQuery(query(session.sessionId, { requestId: "same", clientId: "client-a" }));
    const second = transport.handleQuery(query(session.sessionId, { requestId: "same", clientId: "client-b" }));
    await Promise.all([first, second]);
    const results = sent.filter((message) => message.type === "result");
    expect(results).toHaveLength(2);
    expect(new Set(results.map((message) => "clientId" in message ? message.clientId : undefined))).toEqual(
      new Set(["client-a", "client-b"]),
    );
    expect(adapter.executed).toHaveLength(2);
    store.close();
  });
});
