import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { handleAgentControlToolCall } from "../src/runtime/control-tools.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("durable agent-spawn producer journal", () => {
  it("repairs accepted and terminal floating spawns across restart byte-idempotently", async () => {
    const root = newRoot();
    const databasePath = join(root, "agent.sqlite");
    let { store, kernel } = createKernelHarness(databasePath, "acp");
    const parent = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
    }, () => 1);
    const pillId = "44d4ddf1-df81-4a29-8a2d-16fdb68f9163";
    const descriptor = producerDescriptor(pillId);
    const accepted = await kernel.spawnBackgroundAgent({
      ownerId: "owner",
      callerSessionId: parent.agentSessionId,
      clientId: "floating",
      requestId: "accepted-before-journal",
      prompt: descriptor.objective,
      title: descriptor.title,
      surfaceKind: "floating_bar",
      externalRefKind: "pill",
      externalRefId: pillId,
      mode: "act",
      metadata: { pillId, producerJournal: descriptor },
    });
    await waitUntil(() => String(store.getRow(
      "SELECT status FROM runs WHERE run_id = ?",
      [accepted.run.runId],
    ).status) === "succeeded");
    await waitUntil(() => String(store.getRow(
      "SELECT content_blocks_json FROM conversation_turns WHERE role = 'assistant'",
    ).content_blocks_json).includes("agentCompletion"));
    store.execute("DELETE FROM backend_turn_outbox");
    store.execute("DELETE FROM conversation_turn_revisions");
    store.execute("DELETE FROM conversation_turns");
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    store.close(); // Crash after acceptance/terminal state and before ensure.

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: true });
    kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
    const first = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: accepted.session.sessionId,
      runId: accepted.run.runId,
      nowMs: 100,
    });
    expect(first.userTurn.content).toBe(descriptor.userText);
    expect(first.assistantTurn).toMatchObject({
      content: descriptor.assistantText,
      producingRunId: accepted.run.runId,
      status: "completed",
    });
    expect(first.assistantTurn.createdAtMs).toBe(first.userTurn.createdAtMs + 1);
    expect(first.assistantTurn.contentBlocks).toEqual([
      {
        type: "agentSpawn",
        id: expect.stringMatching(/^agent_spawn_[a-f0-9]{24}$/),
        pillId,
        sessionId: accepted.session.sessionId,
        runId: accepted.run.runId,
        title: descriptor.title,
        objective: descriptor.objective,
      },
      expect.objectContaining({
        type: "agentCompletion",
        id: expect.stringMatching(/^agent_completion_[a-f0-9]{24}$/),
        pillId,
        sessionId: accepted.session.sessionId,
        runId: accepted.run.runId,
        status: "completed",
      }),
    ]);
    const committed = durableJournalBytes(store);

    // Simulate a crash after SQLite commit but before the Swift RPC reply, then
    // repeat hydration repair twice across another daemon open.
    store.close();
    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: true });
    kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
    for (const nowMs of [200, 300]) {
      kernel.ensureAgentSpawnJournal({
        ownerId: "owner",
        sessionId: accepted.session.sessionId,
        runId: accepted.run.runId,
        nowMs,
      });
    }
    expect(durableJournalBytes(store)).toBe(committed);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(2);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turn_revisions").count).toBe(2);
    expect(store.getRow(
      `SELECT COUNT(*) AS count FROM json_each(
         (SELECT content_blocks_json FROM conversation_turns WHERE role = 'assistant')
       ) WHERE json_extract(value, '$.type') = 'agentSpawn'`,
    ).count).toBe(1);
    expect(store.getRow(
      `SELECT COUNT(*) AS count FROM json_each(
         (SELECT content_blocks_json FROM conversation_turns WHERE role = 'assistant')
       ) WHERE json_extract(value, '$.type') = 'agentCompletion'`,
    ).count).toBe(1);
    store.close();
  });

  it("does not write an acknowledgement when spawn authorization is rejected", async () => {
    const root = newRoot();
    const { store, kernel } = createKernelHarness(join(root, "rejected.sqlite"), "acp");
    resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
    }, () => 1);
    const leaf = store.insertSession({
      ownerId: "owner",
      surfaceKind: "delegated_agent",
      externalRefKind: "agent",
      externalRefId: "leaf",
      defaultAdapterId: "acp",
      executionRole: "leaf",
    });
    await expect(kernel.spawnBackgroundAgent({
      ownerId: "owner",
      callerSessionId: leaf.sessionId,
      clientId: "floating",
      requestId: "rejected",
      prompt: "must not acknowledge",
      surfaceKind: "floating_bar",
      externalRefKind: "pill",
      externalRefId: "c3228974-1516-4b20-85cb-0868136e1b49",
      metadata: { producerJournal: producerDescriptor("c3228974-1516-4b20-85cb-0868136e1b49") },
    })).rejects.toThrow(/Leaf workers cannot create/);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    expect(store.allRows("SELECT run_id FROM runs")).toEqual([]);
    store.close();
  });

  it("rejects trusted direct producerTurnId metadata before accepting a child run", async () => {
    const root = newRoot();
    const { store, kernel } = createKernelHarness(join(root, "direct-producer-turn.sqlite"), "acp");
    const caller = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
    }, () => 1);
    const pillId = "897e3ef1-9dbb-41ca-9ac8-8ec52112f387";
    const rejected = JSON.parse(await handleAgentControlToolCall({
      kernel,
      callerSessionId: caller.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      trustedUserControl: true,
      getOwnerId: () => "owner",
    }, "spawn_agent", {
      objective: "Must not be accepted",
      originSurfaceKind: "main_chat",
      externalRefId: pillId,
      metadata: {
        producerJournal: {
          ...producerDescriptor(pillId),
          producerTurnId: "forged-producing-turn",
        },
      },
    }));
    expect(rejected).toMatchObject({
      ok: false,
      error: { message: expect.stringMatching(/producerTurnId is reserved for kernel-authorized/i) },
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM runs").count).toBe(0);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    store.close();
  });

  it("strips model-supplied producer metadata instead of forging another owner-bound chat", async () => {
    const root = newRoot();
    const { store, adapter, kernel } = createKernelHarness(join(root, "forgery.sqlite"), "acp");
    const caller = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "caller" },
      defaultAdapterId: "acp",
    }, () => 1);
    const victim = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "victim" },
      defaultAdapterId: "acp",
    }, () => 2);
    const pillId = "a7561e72-9f8c-4130-90a3-884c33f8c967";
    const forged = {
      ...producerDescriptor(pillId),
      surface: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "victim" },
      userText: "forged user text",
      assistantText: "forged assistant text",
    };
    const raw = await handleAgentControlToolCall({
      kernel,
      callerSessionId: caller.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      getOwnerId: () => "owner",
    }, "spawn_agent", {
      objective: "Legitimate objective",
      originSurfaceKind: "main_chat",
      externalRefId: pillId,
      metadata: { producerJournal: forged },
    });
    expect(JSON.parse(raw)).toMatchObject({ ok: true });
    await waitUntil(() => adapter.executed.length === 1);
    const childInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE session_id != ? ORDER BY created_at_ms DESC LIMIT 1",
      [caller.agentSessionId],
    ).input_json));
    expect(childInput.metadata.producerJournal).toBeUndefined();
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [victim.conversationId],
    ).count).toBe(0);
    store.close();
  });

  it("inherits the exact floating producer snapshot for a trusted direct spawn", async () => {
    const root = newRoot();
    const { store, adapter, kernel } = createKernelHarness(join(root, "direct-floating.sqlite"), "acp");
    const producer = resolveSurfaceSession(store, {
      ownerId: "owner",
      surfaceRef: { surfaceKind: "floating_chat", externalRefKind: "chat", externalRefId: "direct-floating" },
      defaultAdapterId: "acp",
    }, () => 1);
    const snapshot = kernel.updateContextSource({
      ownerId: "owner",
      sessionId: producer.agentSessionId,
      surfaceKind: "floating_chat",
      source: "workspace",
      sourceRevision: "floating-workspace@1",
      outcome: "available",
      capturedAtMs: 2,
      payload: { repository: "omi", worktree: "direct-floating" },
    }).snapshot;
    const pillId = "413b4972-e50d-4f14-942d-975b38b6db04";
    const descriptor = {
      schemaVersion: 1 as const,
      surface: { surfaceKind: "floating_chat", externalRefKind: "chat", externalRefId: "direct-floating" },
      continuityKey: `floating_spawn:${pillId}`,
      pillId,
      userText: "Research the floating-bar release",
      assistantText: "I started a background agent for that.",
      objective: "Research floating-bar release risks",
      title: "Floating Release Research",
    };
    const raw = await handleAgentControlToolCall({
      kernel,
      callerSessionId: producer.agentSessionId,
      executionRole: "coordinator",
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      trustedUserControl: true,
      getOwnerId: () => "owner",
    }, "spawn_agent", {
      objective: descriptor.objective,
      title: descriptor.title,
      originSurfaceKind: "floating_bar",
      visible: true,
      externalRefId: pillId,
      metadata: { producerJournal: descriptor },
    });
    const result = JSON.parse(raw) as { run: { runId: string }; session: { sessionId: string } };
    await waitUntil(() => adapter.executed.length === 1);
    await waitUntil(() => String(store.getRow(
      "SELECT status FROM runs WHERE run_id = ?",
      [result.run.runId],
    ).status) === "succeeded");
    const childInput = JSON.parse(String(store.getRow(
      "SELECT input_json FROM runs WHERE run_id = ?",
      [result.run.runId],
    ).input_json));
    expect(childInput.contextSnapshotVersion).toBe(snapshot.version);
    expect(childInput.contextSnapshotGeneration).toBe(snapshot.snapshotGeneration);
    expect(childInput.contextRendererFingerprint).toBe(childInput.admittedContextSnapshot.rendererFingerprint);
    expect(childInput.contextCapabilityVersion).toBe(childInput.admittedContextSnapshot.capabilityVersion);
    expect(childInput.admittedContextSnapshot.sourceOutcomes).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: "workspace", payload: { repository: "omi", worktree: "direct-floating" } }),
    ]));
    const ensured = kernel.ensureAgentSpawnJournal({
      ownerId: "owner",
      sessionId: result.session.sessionId,
      runId: result.run.runId,
    });
    expect(ensured).toMatchObject({
      conversationId: producer.conversationId,
      userTurn: { content: descriptor.userText },
      assistantTurn: { content: descriptor.assistantText },
    });
    store.close();
  });
});

function producerDescriptor(pillId: string) {
  return {
    schemaVersion: 1,
    surface: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
    continuityKey: `floating_spawn:${pillId}`,
    pillId,
    userText: "Research launch risks",
    assistantText: "I started a background agent for that.",
    objective: "Research launch risks",
    title: "Launch Risk Research",
  } as const;
}

function durableJournalBytes(store: SqliteAgentStore): string {
  return JSON.stringify({
    turns: store.allRows(
      `SELECT conversation_id, turn_id, turn_seq, producer_id, payload_hash, role, surface_kind,
              content, origin, status, content_blocks_json, resources_json, producing_run_id,
              metadata_json, created_at_ms, updated_at_ms, completed_at_ms
       FROM conversation_turns ORDER BY turn_seq ASC`,
    ),
    revisions: store.allRows(
      `SELECT conversation_id, turn_seq, generation, turn_id, producer_id, mutation_kind,
              turn_json, payload_hash, created_at_ms
       FROM conversation_turn_revisions ORDER BY turn_seq ASC`,
    ),
  });
}

function newRoot(): string {
  const root = mkdtempSync(join(tmpdir(), "omi-agent-spawn-journal-"));
  roots.push(root);
  return root;
}
