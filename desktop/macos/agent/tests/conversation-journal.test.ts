import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  ackBackendConversationDeleteOutbox,
  ackBackendTurnOutbox,
  ackBackendTurnOutboxWithWakes,
  applyBackendReconcilePage,
  beginBackendReconcile,
  beginBackendReconcilesForOwner,
  clearJournalConversation,
  drainBackendConversationDeleteOutbox,
  drainBackendTurnOutbox,
  failBackendTurnOutbox,
  failBackendReconcile,
  getJournalObservability,
  importRemoteJournalTurn,
  journalTurnChangedWakes,
  listJournalTurns,
  migrateJournalConversation,
  recordJournalExchange,
  recordJournalTurn,
  settleClearedBackendTurnClaim,
  updateJournalTurn,
} from "../src/runtime/conversation-journal.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import type { ConversationContentBlock, ConversationResource } from "../src/runtime/types.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("kernel conversation journal", () => {
  it("rolls back the first visible turn when the second exchange turn is rejected", () => {
    const fixture = newSurface("main_chat", "chat", "atomic-exchange");
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-assistant-collision",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "Original canonical answer",
      contentBlocks: [],
      delivery: "backend",
      createdAtMs: 1,
    });

    expect(() => recordJournalExchange(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turns: [
        {
          turnId: "turn-user-must-rollback",
          role: "user",
          surfaceKind: "main_chat",
          origin: "typed_chat",
          status: "completed",
          content: "This must not survive alone",
          contentBlocks: [],
          delivery: "backend",
          createdAtMs: 2,
        },
        {
          turnId: "turn-assistant-collision",
          role: "assistant",
          surfaceKind: "main_chat",
          origin: "typed_chat",
          status: "completed",
          content: "Conflicting answer",
          contentBlocks: [],
          delivery: "backend",
          createdAtMs: 3,
        },
      ],
    })).toThrow(/identity collision/i);

    const visible = listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      afterTurnSeq: 0,
      limit: 100,
    });
    expect(visible.turns.map((turn) => turn.turnId)).toEqual(["turn-assistant-collision"]);
    expect(drainBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      limit: 100,
      nowMs: 10,
    }).map((delivery) => delivery.turnId)).toEqual(["turn-assistant-collision"]);
    fixture.store.close();
  });

  it("atomically migrates the complete typed revision graph, outbox identity, and runtime visibility", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    const source = insertSurface(store, "main_chat", "chat", "legacy-task");
    const destination = insertSurface(store, "main_chat", "chat", "canonical-workstream");
    recordCompletedTextTurn(destination, "turn-existing", "Existing canonical turn", 10);
    recordJournalTurn(store, {
      ownerId: source.ownerId,
      conversationId: source.conversationId,
      turnId: "turn-migrated",
      producerId: "producer:migrated",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "streaming",
      content: "Drafting",
      contentBlocks: [
        { type: "text", id: "migrated:text", text: "Drafting" },
        {
          type: "agentSpawn",
          id: "migrated:spawn",
          sessionId: "ses-child",
          runId: "run-child",
          title: "Researcher",
          objective: "Inspect the evidence",
        },
      ],
      resources: [{
        id: "resource:migrated",
        origin: "generatedArtifact",
        title: "Draft report",
        state: "retained",
        mimeType: "text/markdown",
        uri: "file:///tmp/draft.md",
        artifactId: "artifact-draft",
        runId: "run-child",
      }],
      metadataJson: JSON.stringify({ marker: "preserve-me" }),
      delivery: "backend",
      createdAtMs: 20,
    });
    updateJournalTurn(store, {
      ownerId: source.ownerId,
      conversationId: source.conversationId,
      turnId: "turn-migrated",
      status: "completed",
      content: "Draft complete",
      appendContentBlocks: [{ type: "text", id: "migrated:final", text: "Draft complete" }],
      appendResources: [{
        id: "resource:final",
        origin: "generatedArtifact",
        title: "Final report",
        state: "retained",
        mimeType: "text/markdown",
        uri: "file:///tmp/final.md",
        artifactId: "artifact-final",
        runId: "run-child",
      }],
      nowMs: 21,
    });
    store.execute(
      `UPDATE backend_turn_outbox
       SET status = 'retrying', attempt_count = 2, delivery_generation = 3,
           available_at_ms = 99, last_error_code = 'transient'
       WHERE turn_id = 'turn-migrated'`,
    );

    const result = migrateJournalConversation(store, {
      ownerId: source.ownerId,
      sourceConversationId: source.conversationId,
      destinationConversationId: destination.conversationId,
      nowMs: 30,
    });

    expect(result).toMatchObject({ movedTurnCount: 1, movedRevisionCount: 2, movedOutboxCount: 1 });
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turns WHERE conversation_id = ?",
      [source.conversationId],
    ).count).toBe(0);
    const current = store.getRow(
      `SELECT status, content, content_blocks_json, resources_json, metadata_json, turn_seq
       FROM conversation_turns WHERE conversation_id = ? AND turn_id = 'turn-migrated'`,
      [destination.conversationId],
    );
    expect(current).toMatchObject({ status: "completed", content: "Draft complete" });
    expect(JSON.parse(String(current.content_blocks_json))).toHaveLength(3);
    expect(JSON.parse(String(current.resources_json))).toHaveLength(2);
    expect(JSON.parse(String(current.metadata_json))).toMatchObject({ marker: "preserve-me" });
    expect(store.getRow(
      `SELECT conversation_id, status, attempt_count, delivery_generation,
              conversation_generation, available_at_ms, last_error_code
       FROM backend_turn_outbox WHERE turn_id = 'turn-migrated'`,
    )).toMatchObject({
      conversation_id: destination.conversationId,
      status: "retrying",
      attempt_count: 2,
      delivery_generation: 3,
      conversation_generation: result.destinationGeneration,
      available_at_ms: 99,
      last_error_code: "transient",
    });
    const visible = listJournalTurns(store, {
      ownerId: source.ownerId,
      conversationId: destination.conversationId,
      limit: 20,
    });
    expect(visible.turns.map((turn) => turn.turnId)).toEqual([
      "turn-existing",
      "turn-migrated",
      "turn-migrated",
    ]);
    expect(visible.turns.at(-1)).toMatchObject({
      conversationId: destination.conversationId,
      turnId: "turn-migrated",
      status: "completed",
      contentBlocks: expect.arrayContaining([{ type: "text", id: "migrated:final", text: "Draft complete" }]),
      resources: expect.arrayContaining([expect.objectContaining({ id: "resource:final" })]),
    });

    store.close();
    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    const afterRestart = listJournalTurns(store, {
      ownerId: source.ownerId,
      conversationId: destination.conversationId,
      limit: 20,
    });
    expect(afterRestart.turns).toEqual(visible.turns);
    expect(store.getRow(
      "SELECT conversation_id FROM conversation_turns WHERE turn_id = 'turn-migrated'",
    ).conversation_id).toBe(destination.conversationId);
    store.close();
  });

  it("rolls back a destination identity collision without changing either journal byte-for-byte", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    const source = insertSurface(store, "main_chat", "chat", "collision-source");
    const destination = insertSurface(store, "main_chat", "chat", "collision-destination");
    recordJournalTurn(store, {
      ownerId: source.ownerId,
      conversationId: source.conversationId,
      turnId: "turn-collision-source",
      producerId: "producer:destination-collision",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "streaming",
      content: "Source draft",
      contentBlocks: [{ type: "text", id: "source:draft", text: "Source draft" }],
      resources: [{
        id: "source:resource",
        origin: "generatedArtifact",
        title: "Source artifact",
        state: "retained",
        mimeType: "text/plain",
        uri: "file:///tmp/source-artifact.txt",
        artifactId: "artifact-source",
      }],
      delivery: "backend",
      createdAtMs: 10,
    });
    updateJournalTurn(store, {
      ownerId: source.ownerId,
      conversationId: source.conversationId,
      turnId: "turn-collision-source",
      status: "completed",
      content: "Source complete",
      appendContentBlocks: [{ type: "text", id: "source:complete", text: "Source complete" }],
      nowMs: 11,
    });
    recordJournalTurn(store, {
      ownerId: destination.ownerId,
      conversationId: destination.conversationId,
      turnId: "turn-collision-destination",
      producerId: "producer:destination-collision",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "Destination canonical turn",
      contentBlocks: [{ type: "text", id: "destination:text", text: "Destination canonical turn" }],
      delivery: "backend",
      createdAtMs: 12,
    });
    store.execute(
      `UPDATE backend_turn_outbox
       SET status = 'retrying', attempt_count = 4, delivery_generation = 2,
           available_at_ms = 44, last_error_code = 'preserve_on_rollback'
       WHERE turn_id = 'turn-collision-source'`,
    );
    const before = journalStorageSnapshot(store);

    expect(() => migrateJournalConversation(store, {
      ownerId: source.ownerId,
      sourceConversationId: source.conversationId,
      destinationConversationId: destination.conversationId,
      nowMs: 100,
    })).toThrow(/producer identity collision/i);

    expect(journalStorageSnapshot(store)).toEqual(before);
    expect(store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE conversation_id = ?",
      [source.conversationId],
    ).count).toBe(2);
    expect(store.getRow(
      "SELECT status FROM backend_turn_outbox WHERE turn_id = 'turn-collision-source'",
    ).status).toBe("retrying");
    expect(store.getRow(
      "SELECT content FROM conversation_turns WHERE conversation_id = ? AND turn_id = 'turn-collision-destination'",
      [destination.conversationId],
    ).content).toBe("Destination canonical turn");
    store.close();
  });

  it("deduplicates retries by stable producer identity even when turn IDs differ", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const input = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      producerId: "producer:stable",
      role: "assistant" as const,
      surfaceKind: "main_chat",
      origin: "agent_runtime" as const,
      status: "completed" as const,
      content: "Stable result",
      contentBlocks: [{ type: "text" as const, id: "stable:text", text: "Stable result" }],
      delivery: "backend" as const,
      createdAtMs: 10,
    };
    const first = recordJournalTurn(fixture.store, { ...input, turnId: "turn-first" });
    const retry = recordJournalTurn(fixture.store, { ...input, turnId: "turn-regenerated" });

    expect(first).toMatchObject({ created: true, turn: { turnId: "turn-first" } });
    expect(retry).toMatchObject({
      created: false,
      duplicate: true,
      turn: { turnId: "turn-first", producerId: "producer:stable" },
    });
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    expect(() => recordJournalTurn(fixture.store, {
      ...input,
      turnId: "turn-collision",
      content: "Conflicting result",
      contentBlocks: [{ type: "text", id: "stable:text", text: "Conflicting result" }],
    })).toThrow(/producer identity collision/);
    fixture.store.close();
  });

  it("projects a typed pending turn immediately and leases it only after completion", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const blocks: ConversationContentBlock[] = [
      { type: "text", id: "block-text", text: "Working on it" },
      {
        type: "agentSpawn",
        id: "block-spawn",
        sessionId: "ses-child",
        runId: "run-child",
        title: "Researcher",
        objective: "Inspect today's memories",
      },
    ];
    const resources: ConversationResource[] = [{
      id: "artifact:report",
      origin: "generatedArtifact",
      title: "Memory report",
      state: "retained",
      mimeType: "text/markdown",
      uri: "file:///tmp/report.md",
      artifactId: "art-report",
      runId: "run-child",
    }];

    const recorded = recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-pending",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "pending",
      content: "Working on it",
      contentBlocks: blocks,
      resources,
      delivery: "backend",
      createdAtMs: 100,
    });

    expect(recorded).toMatchObject({ created: true, duplicate: false, outboxStatus: "pending" });
    expect(listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
    }).turns).toEqual([
      expect.objectContaining({
        turnId: "turn-pending",
        status: "pending",
        origin: "agent_runtime",
        contentBlocks: blocks,
        resources,
      }),
    ]);
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 101 })).toEqual([]);

    updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-pending",
      status: "completed",
      nowMs: 102,
    });
    const [delivery] = drainBackendTurnOutbox(fixture.store, { nowMs: 103 });
    expect(delivery).toMatchObject({
      turnId: "turn-pending",
      clientMessageId: "turn-pending",
      status: "delivering",
      attemptCount: 1,
      turn: { turnId: "turn-pending", status: "completed", contentBlocks: blocks, resources },
    });
    fixture.store.close();
  });

  it("acknowledges and reconciles a local canonical ID without a duplicate turn", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const floatingSession = fixture.store.insertSession({
      ownerId: fixture.ownerId,
      surfaceKind: "floating_chat",
      defaultAdapterId: "acp",
    });
    fixture.store.insertSurfaceConversation({
      ownerId: fixture.ownerId,
      surfaceKind: "floating_chat",
      externalRefKind: "chat",
      externalRefId: "notch",
      conversationId: fixture.conversationId,
      agentSessionId: floatingSession.sessionId,
      createdAtMs: 2,
      lastActiveAtMs: 2,
    });
    recordCompletedTextTurn(fixture, "turn-local", "One answer", 10);
    const [claim] = drainBackendTurnOutbox(fixture.store, { nowMs: 11 });

    const acknowledged = ackBackendTurnOutboxWithWakes(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: "turn-local",
      remoteId: "remote-1",
      attemptCount: claim.attemptCount,
      deliveryGeneration: claim.deliveryGeneration,
      conversationGeneration: claim.conversationGeneration,
      payloadHash: claim.payloadHash,
      nowMs: 12,
    });
    expect(acknowledged.outbox).toMatchObject({ status: "delivered", remoteId: "remote-1" });
    expect(acknowledged.wakes).toMatchObject([
      {
        conversationGeneration: 1,
        generationBaseTurnSeq: 0,
        surfaceKind: "floating_chat",
        externalRefKind: "chat",
        externalRefId: "notch",
        turn: { turnId: "turn-local", turnSeq: 2, remoteId: "remote-1", surfaceKind: "floating_chat" },
      },
      {
        conversationGeneration: 1,
        generationBaseTurnSeq: 0,
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefId: "default",
        turn: { turnId: "turn-local", turnSeq: 2, remoteId: "remote-1", surfaceKind: "main_chat" },
      },
    ]);
    expect(() => ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: "turn-local",
      remoteId: "remote-1",
      attemptCount: claim.attemptCount,
      deliveryGeneration: claim.deliveryGeneration,
      conversationGeneration: claim.conversationGeneration,
      payloadHash: claim.payloadHash,
      nowMs: 13,
    })).toThrow(/active claimed generation/);

    const reconciled = importRemoteJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      remoteId: "remote-1",
      canonicalTurnId: "turn-local",
      role: "assistant",
      surfaceKind: "main_chat",
      content: "One answer",
      contentBlocks: [{ type: "text", id: "ignored-remote-block", text: "One answer" }],
      createdAtMs: 10,
      nowMs: 14,
      source: "backend_reconcile",
    });
    expect(reconciled).toMatchObject({ imported: false, reconciledLocal: true });
    expect(reconciled.turn.turnId).toBe("turn-local");
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 15 })).toEqual([]);
    fixture.store.close();
  });

  it("requeues an in-flight backend delivery on daemon restart", () => {
    const databasePath = newDatabasePath();
    let now = 100;
    let store = new SqliteAgentStore({ databasePath, nowMs: () => now });
    const fixture = insertSurface(store, "main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-restart", "Persist me", now);
    expect(drainBackendTurnOutbox(store, { nowMs: now, leaseMs: 60_000 })[0]).toMatchObject({
      status: "delivering",
      attemptCount: 1,
    });
    store.close();

    now = 101;
    store = new SqliteAgentStore({ databasePath, nowMs: () => now });
    expect(store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-restart"],
    )).toEqual({ status: "retrying", last_error_code: "daemon_restart" });
    expect(drainBackendTurnOutbox(store, { nowMs: now })[0]).toMatchObject({
      turnId: "turn-restart",
      status: "delivering",
      attemptCount: 2,
    });
    store.close();
  });

  it("reconciles a backend row visible before outbox ACK into the canonical turn in place", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_pre_ack",
      clientId: "client",
      requestId: "pre-ack",
      status: "running",
      mode: "act",
    });
    const spawn: ConversationContentBlock = {
      type: "agentSpawn",
      id: "spawn:pre-ack",
      pillId: "pill-pre-ack",
      sessionId: fixture.sessionId,
      runId: run.runId,
      title: "Preserved agent",
      objective: "Preserve structured content",
    };
    const resource: ConversationResource = {
      id: "artifact:pre-ack",
      origin: "generatedArtifact",
      title: "Preserved artifact",
      state: "retained",
      artifactId: "art-pre-ack",
      runId: run.runId,
    };
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-pre-ack",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "completed",
      content: "Agent accepted",
      contentBlocks: [spawn],
      resources: [resource],
      producingRunId: run.runId,
      delivery: "backend",
      createdAtMs: 20,
    });
    expect(fixture.store.getRow(
      "SELECT status FROM backend_turn_outbox WHERE turn_id = 'turn-pre-ack'",
    )).toEqual({ status: "pending" });

    const request = beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 21,
    })!;
    const page = applyBackendReconcilePage(fixture.store, {
      ...request,
      turns: [{
        remoteId: "remote-pre-ack",
        canonicalTurnId: "turn-pre-ack",
        role: "assistant",
        content: "Backend projection text must not replace canonical content",
        contentBlocks: [{ type: "text", id: "remote:text", text: "ignored" }],
        resources: [],
        createdAtMs: 20,
      }],
      hasMore: false,
      nowMs: 22,
    });
    expect(page.importedTurns).toEqual([
      expect.objectContaining({
        turnId: "turn-pre-ack",
        remoteId: "remote-pre-ack",
        content: "Agent accepted",
        contentBlocks: [spawn],
        resources: [resource],
      }),
    ]);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow(
      "SELECT status, remote_id FROM backend_turn_outbox WHERE turn_id = 'turn-pre-ack'",
    )).toEqual({ status: "delivered", remote_id: "remote-pre-ack" });
    expect(drainBackendTurnOutbox(fixture.store, { ownerId: fixture.ownerId, nowMs: 23 })).toEqual([]);
    fixture.store.close();
  });

  it("keeps queued and in-flight backend claims isolated across owner switches", () => {
    const store = new SqliteAgentStore({ stateDir: newStateDir(), reconcileOnOpen: false });
    const ownerA = insertSurface(store, "main_chat", "chat", "a", "owner-a");
    const ownerB = insertSurface(store, "main_chat", "chat", "b", "owner-b");
    recordCompletedTextTurn(ownerA, "turn-owner-a", "A", 10);
    recordCompletedTextTurn(ownerB, "turn-owner-b", "B", 10);

    const [claimA] = drainBackendTurnOutbox(store, { ownerId: ownerA.ownerId, nowMs: 11, leaseMs: 10 });
    expect(claimA).toMatchObject({ turnId: "turn-owner-a", ownerId: "owner-a", status: "delivering" });
    const [claimB] = drainBackendTurnOutbox(store, { ownerId: ownerB.ownerId, nowMs: 12 });
    expect(claimB).toMatchObject({ turnId: "turn-owner-b", ownerId: "owner-b" });
    expect(() => failBackendTurnOutbox(store, {
      ownerId: ownerB.ownerId,
      turnId: claimA.turnId,
      attemptCount: claimA.attemptCount,
      deliveryGeneration: claimA.deliveryGeneration,
      conversationGeneration: claimA.conversationGeneration,
      payloadHash: claimA.payloadHash,
      errorCode: "backend_sync_owner_changed",
      retryAtMs: 13,
      nowMs: 13,
    })).toThrow(/outside owner scope/);
    expect(store.getRow(
      "SELECT status FROM backend_turn_outbox WHERE turn_id = ?",
      [claimA.turnId],
    )).toEqual({ status: "delivering" });
    expect(failBackendTurnOutbox(store, {
      ownerId: ownerA.ownerId,
      turnId: claimA.turnId,
      attemptCount: claimA.attemptCount,
      deliveryGeneration: claimA.deliveryGeneration,
      conversationGeneration: claimA.conversationGeneration,
      payloadHash: claimA.payloadHash,
      errorCode: "backend_sync_owner_changed",
      retryAtMs: 13,
      nowMs: 13,
    })).toMatchObject({ status: "retrying", ownerId: ownerA.ownerId });
    expect(drainBackendTurnOutbox(store, { ownerId: ownerB.ownerId, nowMs: 13 })).toEqual([]);
    expect(drainBackendTurnOutbox(store, { ownerId: ownerA.ownerId, nowMs: 13 })[0]).toMatchObject({
      turnId: claimA.turnId,
      ownerId: ownerA.ownerId,
      attemptCount: 2,
    });
    store.close();
  });

  it("deduplicates genuinely remote rows by backend remote ID", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const input = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      remoteId: "remote-only-1",
      role: "user" as const,
      surfaceKind: "main_chat",
      content: "Sent from another device",
      contentBlocks: [{ type: "text" as const, id: "remote-text", text: "Sent from another device" }],
      createdAtMs: 5,
      nowMs: 6,
      source: "backend_reconcile" as const,
    };
    const first = importRemoteJournalTurn(fixture.store, input);
    const second = importRemoteJournalTurn(fixture.store, { ...input, nowMs: 7 });

    expect(first).toMatchObject({ imported: true, reconciledLocal: false });
    expect(second).toMatchObject({ imported: false, reconciledLocal: false });
    expect(second.turn.turnId).toBe(first.turn.turnId);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    fixture.store.close();
  });

  it("pages the complete backend history by stable remote ID and advances the frontier", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const firstRequest = beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 100,
    })!;
    expect(firstRequest).toMatchObject({
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      targetKind: "messages",
      targetId: null,
      frontierRemoteId: null,
      pageCursor: null,
      pageLimit: 100,
    });

    const firstPage = applyBackendReconcilePage(fixture.store, {
      ...firstRequest,
      turns: [remoteTurn("remote-3", 5), remoteTurn("remote-2", 50)],
      hasMore: true,
      nextCursor: "remote-2",
      nowMs: 101,
    });
    expect(firstPage).toMatchObject({
      completed: false,
      importedTurns: [
        expect.objectContaining({ remoteId: "remote-3" }),
        expect.objectContaining({ remoteId: "remote-2" }),
      ],
      nextRequest: { pageCursor: "remote-2", frontierRemoteId: null },
    });
    const secondPage = applyBackendReconcilePage(fixture.store, {
      ...firstPage.nextRequest!,
      turns: [remoteTurn("remote-1", 1)],
      hasMore: false,
      nowMs: 102,
    });
    expect(secondPage).toMatchObject({ completed: true, nextRequest: null });
    expect(fixture.store.getRow(
      `SELECT status, frontier_remote_id, page_cursor, page_count
       FROM backend_reconcile_state WHERE conversation_id = ?`,
      [fixture.conversationId],
    )).toEqual({ status: "idle", frontier_remote_id: "remote-3", page_cursor: null, page_count: 0 });

    const incremental = beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 200,
    })!;
    expect(incremental.frontierRemoteId).toBe("remote-3");
    const incrementalPage = applyBackendReconcilePage(fixture.store, {
      ...incremental,
      turns: [remoteTurn("remote-4", 3), remoteTurn("remote-3", 500), remoteTurn("remote-2", 2)],
      hasMore: true,
      nowMs: 201,
    });
    expect(incrementalPage).toMatchObject({
      completed: true,
      nextRequest: null,
      importedTurns: [expect.objectContaining({ remoteId: "remote-4" })],
    });
    expect(fixture.store.allRows(
      "SELECT remote_id FROM conversation_turns ORDER BY remote_id ASC",
    )).toEqual([
      { remote_id: "remote-1" },
      { remote_id: "remote-2" },
      { remote_id: "remote-3" },
      { remote_id: "remote-4" },
    ]);
    expect(fixture.store.getRow(
      "SELECT frontier_remote_id FROM backend_reconcile_state WHERE conversation_id = ?",
      [fixture.conversationId],
    )).toEqual({ frontier_remote_id: "remote-4" });
    fixture.store.close();
  });

  it("restarts backend reconciliation from its stable frontier and deduplicates replayed pages", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    const fixture = insertSurface(store, "main_chat", "chat", "default");
    const request = beginBackendReconcile(store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 300,
    })!;
    const firstPage = applyBackendReconcilePage(store, {
      ...request,
      turns: [remoteTurn("restart-3", 30), remoteTurn("restart-2", 20)],
      hasMore: true,
      nextCursor: "restart-2",
      nowMs: 301,
    });
    expect(firstPage.nextRequest?.pageCursor).toBe("restart-2");
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: true, nowMs: () => 302 });
    expect(store.getRow(
      `SELECT status, frontier_remote_id, page_cursor, last_error_code
       FROM backend_reconcile_state WHERE conversation_id = ?`,
      [fixture.conversationId],
    )).toEqual({
      status: "idle",
      frontier_remote_id: null,
      page_cursor: null,
      last_error_code: "daemon_restart",
    });
    const replay = beginBackendReconcile(store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 303,
    })!;
    expect(replay).toMatchObject({ frontierRemoteId: null, pageCursor: null });
    const replayedPage = applyBackendReconcilePage(store, {
      ...replay,
      turns: [remoteTurn("restart-3", 30), remoteTurn("restart-2", 20)],
      hasMore: true,
      nextCursor: "restart-2",
      nowMs: 304,
    });
    expect(replayedPage.importedTurns).toEqual([]);
    applyBackendReconcilePage(store, {
      ...replayedPage.nextRequest!,
      turns: [remoteTurn("restart-1", 10)],
      hasMore: false,
      nowMs: 305,
    });
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(3);
    expect(store.getRow(
      "SELECT status, frontier_remote_id FROM backend_reconcile_state WHERE conversation_id = ?",
      [fixture.conversationId],
    )).toEqual({ status: "idle", frontier_remote_id: "restart-3" });
    store.close();
  });

  it("does not skip an older message when a newer row is inserted between cursor pages", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const request = beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 350,
    })!;
    const backendRows = [
      remoteTurn("cursor-3", 30),
      remoteTurn("cursor-2", 20),
      remoteTurn("cursor-1", 10),
    ];
    const pageAfter = (cursor: string | null, limit: number) => {
      const start = cursor === null ? 0 : backendRows.findIndex((turn) => turn.remoteId === cursor) + 1;
      return backendRows.slice(start, start + limit);
    };
    const firstRows = pageAfter(request.pageCursor, 2);
    const first = applyBackendReconcilePage(fixture.store, {
      ...request,
      turns: firstRows,
      hasMore: true,
      nextCursor: firstRows.at(-1)!.remoteId,
      nowMs: 351,
    });

    // A mutable offset would now start at index 2 and replay cursor-2, skipping
    // cursor-1. The stable start-after identity still begins after cursor-2.
    backendRows.unshift(remoteTurn("cursor-4", 40));
    const secondRows = pageAfter(first.nextRequest!.pageCursor, 2);
    expect(secondRows.map((turn) => turn.remoteId)).toEqual(["cursor-1"]);
    applyBackendReconcilePage(fixture.store, {
      ...first.nextRequest!,
      turns: secondRows,
      hasMore: false,
      nowMs: 352,
    });
    expect(fixture.store.allRows(
      "SELECT remote_id FROM conversation_turns ORDER BY remote_id ASC",
    )).toEqual([
      { remote_id: "cursor-1" },
      { remote_id: "cursor-2" },
      { remote_id: "cursor-3" },
    ]);
    fixture.store.close();
  });

  it("rejects stale or cross-owner backend reconcile pages and permits exact inactive-owner failure", () => {
    const store = new SqliteAgentStore({ stateDir: newStateDir(), reconcileOnOpen: false });
    const ownerA = insertSurface(store, "main_chat", "chat", "a", "owner-a");
    insertSurface(store, "main_chat", "chat", "b", "owner-b");
    const request = beginBackendReconcile(store, {
      ownerId: ownerA.ownerId,
      conversationId: ownerA.conversationId,
      nowMs: 400,
    })!;
    const page = { ...request, turns: [remoteTurn("owner-a-1", 1)], hasMore: false, nowMs: 401 };
    expect(() => applyBackendReconcilePage(store, { ...page, ownerId: "owner-b" })).toThrow(/owner-scoped/);
    expect(() => applyBackendReconcilePage(store, { ...page, reconcileId: "reconcile:stale" })).toThrow(
      /owner-scoped/,
    );
    expect(() => applyBackendReconcilePage(store, { ...page, pageCursor: "wrong-cursor" })).toThrow(/owner-scoped/);
    expect(() => failBackendReconcile(store, {
      ownerId: "owner-b",
      reconcileId: request.reconcileId,
      conversationId: request.conversationId,
      errorCode: "backend_sync_owner_changed",
      nowMs: 402,
    })).toThrow(/owner-scoped/);
    failBackendReconcile(store, {
      ownerId: ownerA.ownerId,
      reconcileId: request.reconcileId,
      conversationId: request.conversationId,
      errorCode: "backend_sync_owner_changed",
      nowMs: 403,
    });
    expect(store.getRow(
      `SELECT owner_id, status, in_flight_id, last_error_code
       FROM backend_reconcile_state WHERE conversation_id = ?`,
      [request.conversationId],
    )).toEqual({
      owner_id: ownerA.ownerId,
      status: "failed",
      in_flight_id: null,
      last_error_code: "backend_sync_owner_changed",
    });
    store.close();
  });

  it("schedules backend reads only on an explicit owner or main-chat refresh trigger", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    for (const nowMs of [500, 501, 502]) {
      expect(drainBackendTurnOutbox(fixture.store, { ownerId: fixture.ownerId, nowMs })).toEqual([]);
    }
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_reconcile_state").count).toBe(0);

    const [activation] = beginBackendReconcilesForOwner(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 503,
    });
    expect(activation).toMatchObject({ conversationId: fixture.conversationId, pageCursor: null });
    expect(beginBackendReconcilesForOwner(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 504,
    })).toEqual([]);
    applyBackendReconcilePage(fixture.store, {
      ...activation,
      turns: [],
      hasMore: false,
      nowMs: 505,
    });
    expect(beginBackendReconcilesForOwner(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 506,
    })).toEqual([]);
    expect(beginBackendReconcilesForOwner(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 5_504,
    })).toHaveLength(1);
    fixture.store.close();
  });

  it("generation-fences an in-flight remote page across clear and suppresses refresh until delete ACK", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const request = beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 600,
    })!;
    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 601,
    });
    expect(() => applyBackendReconcilePage(fixture.store, {
      ...request,
      turns: [remoteTurn("stale-after-clear", 1)],
      hasMore: false,
      nowMs: 602,
    })).toThrow(/owner-scoped/);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    expect(beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 10_000,
    })).toBeNull();
    const [deleteClaim] = drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 603,
    });
    expect(deleteClaim.operationId).toBe(cleared.backendDeleteOperationId);
    ackBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      operationId: deleteClaim.operationId,
      conversationGeneration: deleteClaim.conversationGeneration,
      attemptCount: deleteClaim.attemptCount,
      deliveryGeneration: deleteClaim.deliveryGeneration,
      payloadHash: deleteClaim.payloadHash,
      nowMs: 604,
    });
    expect(beginBackendReconcile(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      nowMs: 605,
    })).toMatchObject({ frontierRemoteId: null, pageCursor: null });
    fixture.store.close();
  });

  it("projects remote import wakes to exact app and session surface references", () => {
    for (const externalRefId of ["default|app-123", "server-session-123"]) {
      const fixture = newSurface("main_chat", "chat", externalRefId);
      const request = beginBackendReconcile(fixture.store, {
        ownerId: fixture.ownerId,
        conversationId: fixture.conversationId,
        nowMs: 700,
      })!;
      const page = applyBackendReconcilePage(fixture.store, {
        ...request,
        turns: [remoteTurn(`remote-${externalRefId}`, 1)],
        hasMore: false,
        nowMs: 701,
      });
      expect(journalTurnChangedWakes(fixture.store, fixture.ownerId, page.importedTurns[0]!)).toEqual([
        expect.objectContaining({
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId,
          conversationGeneration: 1,
          turn: expect.objectContaining({ remoteId: `remote-${externalRefId}`, surfaceKind: "main_chat" }),
        }),
      ]);
      fixture.store.close();
    }
  });

  it("keeps task and workstream turns in the same journal without backend outbox rows", () => {
    const dir = newStateDir();
    const store = new SqliteAgentStore({ stateDir: dir, reconcileOnOpen: false });
    const task = insertSurface(store, "task_chat", "task", "task-1");
    const workstream = insertSurface(store, "workstream", "workstream", "ws-1");

    for (const [fixture, origin, turnId] of [
      [task, "task_chat", "turn-task"],
      [workstream, "workstream", "turn-workstream"],
    ] as const) {
      expect(recordJournalTurn(store, {
        ownerId: fixture.ownerId,
        conversationId: fixture.conversationId,
        turnId,
        role: "user",
        surfaceKind: origin,
        origin,
        status: "completed",
        content: `Local ${origin}`,
        contentBlocks: [{ type: "text", id: `${turnId}:text`, text: `Local ${origin}` }],
        delivery: "local",
        createdAtMs: 20,
      })).toMatchObject({ created: true, outboxStatus: null });
    }
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(2);
    expect(store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    expect(() => recordJournalTurn(store, {
      ownerId: task.ownerId,
      conversationId: task.conversationId,
      role: "user",
      surfaceKind: "task_chat",
      origin: "task_chat",
      content: "Wrong destination",
      contentBlocks: [{ type: "text", id: "wrong:text", text: "Wrong destination" }],
      delivery: "backend",
    })).toThrow("local journal records");
    store.close();
  });

  it("adds agent completion and resources to the producing turn idempotently", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run-producing",
      clientId: "client",
      requestId: "request",
      status: "running",
      mode: "act",
      createdAtMs: 30,
    });
    const spawn: ConversationContentBlock = {
      type: "agentSpawn",
      id: "agent-spawn",
      sessionId: fixture.sessionId,
      runId: run.runId,
      title: "Memory agent",
      objective: "Find an insight",
    };
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-producing",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "pending",
      content: "Agent running",
      contentBlocks: [spawn],
      producingRunId: run.runId,
      delivery: "backend",
      createdAtMs: 31,
    });
    const completion: ConversationContentBlock = {
      type: "agentCompletion",
      id: "agent-completion",
      sessionId: fixture.sessionId,
      runId: run.runId,
      title: "Memory agent",
      promptSnippet: "Find an insight",
      output: "The surprising insight",
      status: "completed",
    };
    const resource: ConversationResource = {
      id: "artifact:insight",
      origin: "generatedArtifact",
      title: "Insight",
      state: "retained",
      artifactId: "art-insight",
      runId: run.runId,
    };
    for (const nowMs of [32, 33]) {
      updateJournalTurn(fixture.store, {
        ownerId: fixture.ownerId,
        conversationId: fixture.conversationId,
        turnId: "turn-producing",
        status: "completed",
        content: "The surprising insight",
        appendContentBlocks: [completion],
        appendResources: [resource],
        nowMs,
      });
    }

    const revisions = listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
    }).turns;
    const turn = revisions.at(-1)!;
    expect(revisions.map((revision) => revision.status)).toEqual(["pending", "completed"]);
    expect(turn).toMatchObject({
      turnId: "turn-producing",
      producingRunId: run.runId,
      status: "completed",
      contentBlocks: [spawn, completion],
      resources: [resource],
    });
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 34 })[0].turn).toMatchObject({
      contentBlocks: [spawn, completion],
      resources: [resource],
    });
    fixture.store.close();
  });

  it("keeps turn and outbox insertion idempotent and rejects same-ID collisions", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const input = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-idempotent",
      role: "user" as const,
      surfaceKind: "main_chat",
      origin: "typed_chat" as const,
      status: "completed" as const,
      content: "Same logical turn",
      contentBlocks: [{ type: "text" as const, id: "same:text", text: "Same logical turn" }],
      delivery: "backend" as const,
      createdAtMs: 50,
    };
    expect(recordJournalTurn(fixture.store, input)).toMatchObject({ created: true, duplicate: false });
    expect(recordJournalTurn(fixture.store, input)).toMatchObject({ created: false, duplicate: true });
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    expect(() => recordJournalTurn(fixture.store, { ...input, content: "Collision" })).toThrow(
      "different journal content",
    );
    fixture.store.close();
  });

  it("retries bounded delivery failures and exposes state-only observability", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-retry", "Sensitive private content", 60);
    const [claim] = drainBackendTurnOutbox(fixture.store, { nowMs: 61 });
    expect(() => failBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: "turn-retry",
      attemptCount: claim.attemptCount,
      deliveryGeneration: claim.deliveryGeneration,
      conversationGeneration: claim.conversationGeneration,
      payloadHash: claim.payloadHash,
      errorCode: "raw network error body",
      retryAtMs: 70,
    })).toThrow("bounded error code");
    expect(failBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: "turn-retry",
      attemptCount: claim.attemptCount,
      deliveryGeneration: claim.deliveryGeneration,
      conversationGeneration: claim.conversationGeneration,
      payloadHash: claim.payloadHash,
      errorCode: "network_unavailable",
      retryAtMs: 70,
      nowMs: 62,
    })).toMatchObject({ status: "retrying", lastErrorCode: "network_unavailable" });
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 69 })).toEqual([]);
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 70 })[0]).toMatchObject({ attemptCount: 2 });

    const health = getJournalObservability(fixture.store, { ownerId: fixture.ownerId });
    expect(health).toEqual({
      turnStatusCounts: { completed: 1 },
      deliveryStatusCounts: { delivering: 1 },
      oldestPendingDeliveryCreatedAtMs: 60,
    });
    expect(JSON.stringify(health)).not.toContain("Sensitive private content");
    fixture.store.close();
  });

  it("keeps a monotonic generation base and hard-deletes stale delivery claims across clear", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-revision", "v1", 80);
    const updated = updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-revision",
      content: "v2",
      nowMs: 81,
    });
    const beforeClear = listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      afterTurnSeq: 0,
    });
    expect(beforeClear.turns.map((turn) => [turn.turnId, turn.content, turn.turnSeq])).toEqual([
      ["turn-revision", "v1", 1],
      ["turn-revision", "v2", 2],
    ]);
    expect(updated.turnSeq).toBe(2);
    const [staleClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 82 });

    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 83,
    });
    expect(cleared).toMatchObject({
      generation: 2,
      generationBaseTurnSeq: 3,
      highWaterTurnSeq: 3,
      deletedTurns: 1,
      backendDeleteOperationId: `delete:${fixture.conversationId}:2`,
    });
    const empty = listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      afterTurnSeq: cleared.generationBaseTurnSeq,
    });
    expect(empty).toMatchObject({ generation: 2, generationBaseTurnSeq: 3, turns: [] });
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    const [deleteClaim] = drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 84,
    });
    expect(deleteClaim).toMatchObject({
      operationId: cleared.backendDeleteOperationId!,
      ownerId: fixture.ownerId,
      conversationGeneration: 2,
      targetKind: "messages",
      targetId: null,
      status: "delivering",
    });
    expect(() => ackBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      operationId: deleteClaim.operationId,
      conversationGeneration: deleteClaim.conversationGeneration,
      attemptCount: deleteClaim.attemptCount,
      deliveryGeneration: deleteClaim.deliveryGeneration,
      payloadHash: deleteClaim.payloadHash,
      nowMs: 84,
    })).toThrow(/prior turn claims/);
    expect(settleClearedBackendTurnClaim(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: staleClaim.turnId,
      conversationId: staleClaim.conversationId,
      attemptCount: staleClaim.attemptCount,
      deliveryGeneration: staleClaim.deliveryGeneration,
      conversationGeneration: staleClaim.conversationGeneration,
      payloadHash: staleClaim.payloadHash,
      ok: true,
      nowMs: 84,
    })).toBe(true);
    expect(ackBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      operationId: deleteClaim.operationId,
      conversationGeneration: deleteClaim.conversationGeneration,
      attemptCount: deleteClaim.attemptCount,
      deliveryGeneration: deleteClaim.deliveryGeneration,
      payloadHash: deleteClaim.payloadHash,
      nowMs: 85,
    })).toMatchObject({ status: "delivered" });
    expect(() => ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: staleClaim.turnId,
      remoteId: "late-remote-id",
      attemptCount: staleClaim.attemptCount,
      deliveryGeneration: staleClaim.deliveryGeneration,
      conversationGeneration: staleClaim.conversationGeneration,
      payloadHash: staleClaim.payloadHash,
      nowMs: 84,
    })).toThrow(/Unknown journal turn|no backend delivery/);
    expect(() => clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
    })).toThrow(/generation is stale/);
    fixture.store.close();
  });

  it("orders clear barriers before a new-generation POST and settles the pre-clear physical claim", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-old", "Old", 100);
    const [oldClaim] = drainBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 101,
      leaseMs: 1_000,
    });
    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 102,
    });
    recordCompletedTextTurn(fixture, "turn-new", "New", 103);
    expect(drainBackendTurnOutbox(fixture.store, { ownerId: fixture.ownerId, nowMs: 104 })).toEqual([]);
    const [deleteClaim] = drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 104,
    });
    expect(deleteClaim).toMatchObject({ operationId: cleared.backendDeleteOperationId, conversationGeneration: 2 });
    expect(settleClearedBackendTurnClaim(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: oldClaim.turnId,
      conversationId: oldClaim.conversationId,
      attemptCount: oldClaim.attemptCount,
      deliveryGeneration: oldClaim.deliveryGeneration,
      conversationGeneration: oldClaim.conversationGeneration,
      payloadHash: oldClaim.payloadHash,
      ok: true,
      nowMs: 105,
    })).toBe(true);
    ackBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      operationId: deleteClaim.operationId,
      conversationGeneration: deleteClaim.conversationGeneration,
      attemptCount: deleteClaim.attemptCount,
      deliveryGeneration: deleteClaim.deliveryGeneration,
      payloadHash: deleteClaim.payloadHash,
      nowMs: 106,
    });
    expect(drainBackendTurnOutbox(fixture.store, { ownerId: fixture.ownerId, nowMs: 107 })[0]).toMatchObject({
      turnId: "turn-new",
      conversationGeneration: 2,
    });
    fixture.store.close();
  });

  it("rejects a journal clear without an exact positive generation fence", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    expect(() => clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: undefined,
    } as unknown as Parameters<typeof clearJournalConversation>[1])).toThrow(/positive integer/);
    expect(listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
    }).generation).toBe(1);
    fixture.store.close();
  });

  it("enqueues session deletion targets instead of acknowledging a local-only clear", () => {
    const fixture = newSurface("main_chat", "chat", "server-session-1");
    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 90,
    });
    expect(cleared.backendDeleteOperationId).toBe(`delete:${fixture.conversationId}:2`);
    expect(drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 91,
    })[0]).toMatchObject({
      targetKind: "chat_session",
      targetId: "server-session-1",
    });
    fixture.store.close();
  });

  it("tombstones empty failed placeholders and projects structured-only completion deterministically", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-empty-failed",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "failed",
      content: "",
      contentBlocks: [],
      delivery: "backend",
      createdAtMs: 90,
    });
    expect(fixture.store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-empty-failed"],
    )).toEqual({ status: "failed", last_error_code: "empty_failed_turn_cancelled" });

    const block = { type: "thinking" as const, id: "structured", text: "finished" };
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-structured",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "completed",
      content: "",
      contentBlocks: [block],
      delivery: "backend",
      createdAtMs: 91,
    });
    const [delivery] = drainBackendTurnOutbox(fixture.store, { nowMs: 92 });
    expect(delivery).toMatchObject({
      turnId: "turn-structured",
      payload: { text: "Done.", sender: "ai" },
    });
    expect(JSON.parse(delivery.payload.metadata!)).toMatchObject({ content_blocks: [block] });
    expect(delivery.payloadHash).toMatch(/^sha256:[a-f0-9]{64}$/);
    fixture.store.close();
  });
});

interface SurfaceFixture {
  store: SqliteAgentStore;
  ownerId: string;
  sessionId: string;
  conversationId: string;
}

function newSurface(surfaceKind: string, externalRefKind: string, externalRefId: string): SurfaceFixture {
  const store = new SqliteAgentStore({ stateDir: newStateDir(), reconcileOnOpen: false });
  return insertSurface(store, surfaceKind, externalRefKind, externalRefId);
}

function insertSurface(
  store: SqliteAgentStore,
  surfaceKind: string,
  externalRefKind: string,
  externalRefId: string,
  ownerId = "owner",
): SurfaceFixture {
  const session = store.insertSession({ ownerId, surfaceKind, defaultAdapterId: "acp" });
  const conversationId = `conv-${surfaceKind}-${externalRefId}`;
  store.insertSurfaceConversation({
    ownerId,
    surfaceKind,
    externalRefKind,
    externalRefId,
    conversationId,
    agentSessionId: session.sessionId,
    createdAtMs: 1,
    lastActiveAtMs: 1,
  });
  return { store, ownerId, sessionId: session.sessionId, conversationId };
}

function recordCompletedTextTurn(
  fixture: SurfaceFixture,
  turnId: string,
  content: string,
  createdAtMs: number,
): void {
  recordJournalTurn(fixture.store, {
    ownerId: fixture.ownerId,
    conversationId: fixture.conversationId,
    turnId,
    role: "assistant",
    surfaceKind: "main_chat",
    origin: "typed_chat",
    status: "completed",
    content,
    contentBlocks: [{ type: "text", id: `${turnId}:text`, text: content }],
    delivery: "backend",
    createdAtMs,
  });
}

function journalStorageSnapshot(store: SqliteAgentStore) {
  return {
    turns: store.allRows(
      "SELECT * FROM conversation_turns ORDER BY conversation_id, turn_seq, turn_id",
    ),
    revisions: store.allRows(
      "SELECT * FROM conversation_turn_revisions ORDER BY conversation_id, generation, turn_seq",
    ),
    outbox: store.allRows(
      "SELECT * FROM backend_turn_outbox ORDER BY conversation_id, turn_id",
    ),
    state: store.allRows(
      "SELECT * FROM conversation_journal_state ORDER BY conversation_id",
    ),
  };
}

function remoteTurn(remoteId: string, createdAtMs: number) {
  return {
    remoteId,
    role: "assistant" as const,
    content: `Remote ${remoteId}`,
    contentBlocks: [{ type: "text" as const, id: `${remoteId}:text`, text: `Remote ${remoteId}` }],
    createdAtMs,
  };
}

function newStateDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-conversation-journal-"));
  createdDirs.push(dir);
  return dir;
}

function newDatabasePath(): string {
  return join(newStateDir(), "agent.sqlite3");
}
