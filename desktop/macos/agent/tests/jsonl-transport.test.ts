import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import type { OutboundMessageDraft, QueryMessage } from "../src/protocol.js";
import { JsonlTransport } from "../src/runtime/jsonl-transport.js";
import { updateContextSource } from "../src/runtime/context-snapshot.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function fixture() {
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
    surfaceKind: "main_chat",
    prompt: "hello",
    mode: "act",
    ...overrides,
  };
}

describe("JsonlTransport kernel-owned query contract", () => {
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

    for (const field of ["runId", "attemptId", "eventId", "surfaceContextJson", "systemPrompt", "cwd", "model"] as const) {
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
