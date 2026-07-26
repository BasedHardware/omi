import { createHash } from "node:crypto";
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
  classifyBackendTurnResultDisposition,
  drainBackendConversationDeleteOutbox,
  drainBackendTurnOutbox,
  failBackendTurnOutbox,
  failBackendReconcile,
  getJournalObservability,
  importRemoteJournalTurn,
  journalTurnForSurfaceProjection,
  journalTurnChangedWakes,
  listJournalTurns,
  migrateJournalConversation,
  OUTBOX_CANONICAL_HASH_MISMATCH_CODE,
  recordJournalExchange,
  recordJournalTurn,
  settleClearedBackendTurnClaim,
  assertPublicJournalUpdatePolicy,
  terminalizeJournalTurn,
  updateJournalTurn,
} from "../src/runtime/conversation-journal.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import type { ConversationContentBlock, ConversationResource } from "../src/runtime/types.js";
import { assertPublicJournalRecordAuthority } from "../src/protocol.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

describe("kernel conversation journal", () => {
  it("projects shared chat revisions through the requesting binding with owner-fenced wakes", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    const realtimeSession = fixture.store.insertSession({
      ownerId: fixture.ownerId,
      surfaceKind: "realtime_voice",
      defaultAdapterId: "acp",
    });
    fixture.store.insertSurfaceConversation({
      ownerId: fixture.ownerId,
      surfaceKind: "realtime_voice",
      externalRefKind: "chat",
      externalRefId: "default",
      conversationId: fixture.conversationId,
      agentSessionId: realtimeSession.sessionId,
      createdAtMs: 2,
      lastActiveAtMs: 2,
    });
    const recorded = recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-voice-spawn",
      role: "assistant",
      surfaceKind: "realtime_voice",
      origin: "realtime_voice",
      status: "completed",
      content: "I started a background agent for that.",
      contentBlocks: [{
        type: "agentSpawn",
        id: "spawn-voice",
        sessionId: "session-child",
        runId: "run-child",
        title: "Memory insight",
        objective: "Find a surprising memory insight",
      }],
      createdAtMs: 3,
    }).turn;

    const listed = listJournalTurns(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
    });
    expect(listed.turns).toMatchObject([{ surfaceKind: "realtime_voice" }]);
    expect(journalTurnForSurfaceProjection(listed.turns[0]!, "main_chat")).toMatchObject({
      turnId: "turn-voice-spawn",
      surfaceKind: "main_chat",
      origin: "realtime_voice",
    });
    expect(recorded.surfaceKind).toBe("realtime_voice");

    expect(journalTurnChangedWakes(fixture.store, fixture.ownerId, recorded)).toMatchObject([
      {
        ownerId: fixture.ownerId,
        surfaceKind: "main_chat",
        externalRefKind: "chat",
        externalRefId: "default",
        turn: { turnId: "turn-voice-spawn", surfaceKind: "main_chat" },
      },
      {
        ownerId: fixture.ownerId,
        surfaceKind: "realtime_voice",
        externalRefKind: "chat",
        externalRefId: "default",
        turn: { turnId: "turn-voice-spawn", surfaceKind: "realtime_voice" },
      },
    ]);
    fixture.store.close();
  });

  it("derives delivery from the canonical conversation and rejects surface spoofing", () => {
    const store = new SqliteAgentStore({ stateDir: newStateDir(), reconcileOnOpen: false });
    const main = insertSurface(store, "main_chat", "chat", "canonical-main");
    const onboarding = insertSurface(store, "onboarding", "session", "canonical-onboarding");
    const task = insertSurface(store, "task_chat", "task", "canonical-task");
    const base = {
      ownerId: main.ownerId,
      role: "user" as const,
      origin: "typed_chat" as const,
      status: "completed" as const,
      content: "Canonical delivery boundary",
      contentBlocks: [{ type: "text" as const, id: "canonical:text", text: "Canonical delivery boundary" }],
      createdAtMs: 1,
    };

    expect(recordJournalTurn(store, {
      ...base,
      conversationId: main.conversationId,
      turnId: "turn-main",
      surfaceKind: "main_chat",
    })).toMatchObject({ created: true, outboxStatus: "pending" });
    expect(recordJournalTurn(store, {
      ...base,
      conversationId: task.conversationId,
      turnId: "turn-task",
      surfaceKind: "task_chat",
      origin: "task_chat",
    })).toMatchObject({ created: true, outboxStatus: null });
    expect(recordJournalTurn(store, {
      ...base,
      conversationId: onboarding.conversationId,
      turnId: "turn-onboarding",
      surfaceKind: "onboarding",
    })).toMatchObject({ created: true, outboxStatus: null });
    expect(() => recordJournalTurn(store, {
      ...base,
      conversationId: main.conversationId,
      turnId: "turn-main-surface-spoof",
      surfaceKind: "task_chat",
      origin: "task_chat",
    })).toThrow(/canonical conversation delivery boundary/i);

    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(3);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turn_revisions").count).toBe(3);
    expect(store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_journal_state").count).toBe(3);
    store.close();
  });

  it("rejects forged delivery before mutation and commits a valid backend exchange atomically", () => {
    const fixture = newSurface("main_chat", "chat", "wire-authority");
    expect(() => assertPublicJournalRecordAuthority({
      turnId: "turn-forged",
      role: "user",
      delivery: "local",
    })).toThrow(/delivery is kernel-owned/i);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    const turns = [
      {
        turnId: "turn-wire-user",
        role: "user" as const,
        surfaceKind: "main_chat",
        origin: "typed_chat" as const,
        status: "completed" as const,
        content: "Question",
        contentBlocks: [] as ConversationContentBlock[],
        createdAtMs: 1,
      },
      {
        turnId: "turn-wire-assistant",
        role: "assistant" as const,
        surfaceKind: "main_chat",
        origin: "typed_chat" as const,
        status: "completed" as const,
        content: "Answer",
        contentBlocks: [] as ConversationContentBlock[],
        createdAtMs: 2,
      },
    ];
    turns.forEach(assertPublicJournalRecordAuthority);
    expect(recordJournalExchange(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turns,
    }).createdTurns).toHaveLength(2);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(2);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(2);
    fixture.store.close();
  });

  it("rejects mixed exchange surfaces and mixed canonical delivery bindings atomically", () => {
    const fixture = newSurface("main_chat", "chat", "mixed-delivery");
    expect(() => recordJournalExchange(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turns: [
        {
          turnId: "turn-mixed-user",
          role: "user",
          surfaceKind: "main_chat",
          origin: "typed_chat",
          status: "completed",
          content: "User half",
          contentBlocks: [],
          createdAtMs: 1,
        },
        {
          turnId: "turn-mixed-assistant",
          role: "assistant",
          surfaceKind: "task_chat",
          origin: "task_chat",
          status: "completed",
          content: "Assistant half",
          contentBlocks: [],
          createdAtMs: 2,
        },
      ],
    })).toThrow(/canonical conversation delivery boundary/i);

    const localSession = fixture.store.insertSession({
      ownerId: fixture.ownerId,
      surfaceKind: "task_chat",
      defaultAdapterId: "acp",
    });
    fixture.store.insertSurfaceConversation({
      ownerId: fixture.ownerId,
      surfaceKind: "task_chat",
      externalRefKind: "task",
      externalRefId: "mixed-delivery-task",
      conversationId: fixture.conversationId,
      agentSessionId: localSession.sessionId,
      createdAtMs: 3,
      lastActiveAtMs: 3,
    });
    expect(() => recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-mixed-canonical",
      role: "user",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "Must not commit",
      contentBlocks: [],
      createdAtMs: 4,
    })).toThrow(/mixes local-only and backend-backed canonical surfaces/i);

    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(0);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turn_revisions").count).toBe(0);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_journal_state").count).toBe(0);
    fixture.store.close();
  });

  it("rejects a late realtime provider projection that collides with a canonical agent-spawn turn", () => {
    const fixture = newSurface("main_chat", "chat", "voice-collision");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_voice_collision",
      clientId: "realtime",
      requestId: "voice-collision",
      status: "running",
      mode: "act",
    });
    const continuityKey = "voice:strict-collision";
    const turnId = `turn_${createHash("sha256")
      .update(`${continuityKey}\0assistant`)
      .digest("hex")
      .slice(0, 32)}`;
    const canonical = recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId,
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "realtime_voice",
      status: "completed",
      content: "I started the background agent.",
      contentBlocks: [{
        type: "agentSpawn",
        id: "voice:spawn",
        sessionId: fixture.sessionId,
        runId: run.runId,
        title: "Voice researcher",
        objective: "Research the launch",
      }],
      resources: [],
      producingRunId: run.runId,
      metadataJson: JSON.stringify({ continuityKey }),
      createdAtMs: 1,
    });

    expect(() => recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId,
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "realtime_voice",
      status: "completed",
      content: "Ordinary provider completion text",
      contentBlocks: [],
      resources: [],
      metadataJson: JSON.stringify({ continuityKey }),
      createdAtMs: 2,
    })).toThrow(/identity collision has different journal content/i);
    expect(fixture.store.getRow(
      "SELECT content, content_blocks_json FROM conversation_turns WHERE turn_id = ?",
      [turnId],
    )).toEqual({
      content: canonical.turn.content,
      content_blocks_json: JSON.stringify(canonical.turn.contentBlocks),
    });
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM conversation_turn_revisions").count).toBe(1);
    expect(fixture.store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(1);
    fixture.store.close();
  });

  it("terminalizes a producing turn from the exact canonical run attempt and replays idempotently", () => {
    const fixture = newSurface("task_chat", "task", "terminal-success");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_terminal_success",
      clientId: "task-chat",
      requestId: "terminal-success",
      status: "succeeded",
      mode: "act",
    });
    const attempt = fixture.store.insertAttempt({
      attemptId: "att_terminal_success",
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "fake",
      adapterInstanceId: "fake:terminal-success",
    });
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-success",
      role: "assistant",
      surfaceKind: "task_chat",
      origin: "task_chat",
      status: "streaming",
      content: "Working",
      contentBlocks: [{ type: "text", id: "terminal:text", text: "Working" }],
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      createdAtMs: 10,
    });
    const terminalization = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-success",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "accept" as const,
      content: "Canonical result",
      replaceContentBlocks: [{ type: "text" as const, id: "terminal:text", text: "Canonical result" }],
      replaceResources: [{
        id: "terminal:artifact",
        origin: "generatedArtifact" as const,
        title: "Canonical artifact",
        state: "retained" as const,
        artifactId: "artifact-terminal",
        runId: run.runId,
      }],
      nowMs: 11,
    };
    const completed = terminalizeJournalTurn(fixture.store, terminalization);
    expect(completed).toMatchObject({
      status: "completed",
      content: "Canonical result",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      completedAtMs: 11,
    });
    const revisionCount = fixture.store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE turn_id = ?",
      [completed.turnId],
    ).count;
    expect(terminalizeJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: completed.turnId,
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "accept",
      nowMs: 12,
    })).toEqual(completed);
    expect(terminalizeJournalTurn(fixture.store, { ...terminalization, nowMs: 13 })).toEqual(completed);
    expect(fixture.store.getRow(
      "SELECT COUNT(*) AS count FROM conversation_turn_revisions WHERE turn_id = ?",
      [completed.turnId],
    ).count).toBe(revisionCount);
    expect(() => terminalizeJournalTurn(fixture.store, {
      ...terminalization,
      content: "Conflicting replay",
      nowMs: 14,
    })).toThrow(/already terminalized with different canonical material/i);
    fixture.store.close();
  });

  it("keeps one logical exchange durable across a lost terminal acknowledgement and relaunch", () => {
    const stateDir = newStateDir();
    const store = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    const fixture = insertSurface(store, "main_chat", "chat", "lost-terminal-ack");
    // Keep these identical to ChatProvider.messageIds(forAttemptId:): the
    // attempt is the user identity and its `-assistant` suffix is the peer.
    const attemptId = "RELAUNCH-PERSIST-1784573311";
    const userTurnId = attemptId;
    const assistantTurnId = `${attemptId}-assistant`;
    const fullText = "RELAUNCH-PERSIST-1784573311";
    const preservedSpawn = {
      type: "agentSpawn" as const,
      id: "lost-ack:spawn",
      sessionId: fixture.sessionId,
      runId: "run_lost_terminal_ack",
      title: "Durable child",
      objective: "Preserve the child card across terminal replay",
    };
    const terminalResource = {
      id: "artifact:lost-terminal-ack",
      origin: "generatedArtifact" as const,
      title: "durable-result.txt",
      state: "retained" as const,
      artifactId: "artifact-lost-terminal-ack",
      sessionId: fixture.sessionId,
      runId: "run_lost_terminal_ack",
    };
    const run = store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_lost_terminal_ack",
      clientId: "main-chat",
      requestId: attemptId,
      status: "succeeded",
      mode: "act",
    });
    const attempt = store.insertAttempt({
      attemptId: "att_lost_terminal_ack",
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "fake",
      adapterInstanceId: "fake:lost-terminal-ack",
    });
    const exchange = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turns: [
        {
          turnId: userTurnId,
          role: "user" as const,
          surfaceKind: "main_chat",
          origin: "typed_chat" as const,
          status: "completed" as const,
          content: "Echo the durable nonce.",
          contentBlocks: [{ type: "text" as const, id: "lost-ack:user", text: "Echo the durable nonce." }],
          createdAtMs: 10,
        },
        {
          turnId: assistantTurnId,
          role: "assistant" as const,
          surfaceKind: "main_chat",
          origin: "typed_chat" as const,
          status: "streaming" as const,
          content: "RELAUNCH-PERSIST-1",
          contentBlocks: [
            { type: "text" as const, id: "lost-ack:stream", text: "RELAUNCH-PERSIST-1" },
            preservedSpawn,
          ],
          producingRunId: run.runId,
          producingAttemptId: attempt.attemptId,
          createdAtMs: 11,
        },
      ],
    };

    expect(recordJournalExchange(store, exchange).createdTurns).toHaveLength(2);
    // The kernel committed before the caller lost its terminal RPC response.
    // Replaying the same stable logical IDs is the bounded retry, not another write.
    expect(recordJournalExchange(store, exchange).createdTurns).toHaveLength(0);
    const terminalization = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: assistantTurnId,
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "accept" as const,
      content: fullText,
      replaceContentBlocks: [{
        type: "text" as const,
        id: "lost-ack:assistant",
        text: fullText,
      }],
      replaceResources: [terminalResource],
      nowMs: 12,
    };
    void terminalizeJournalTurn(store, terminalization); // terminal response lost after durable commit
    expect(terminalizeJournalTurn(store, { ...terminalization, nowMs: 13 })).toMatchObject({
      turnId: assistantTurnId,
      status: "completed",
    });
    store.close();

    const relaunched = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    // Durable logical rows own canonical identity; revisions are deliberately
    // append-only and must replay in sequence rather than through an ad hoc Map.
    expect(relaunched.allRows(
      "SELECT turn_id, role, status FROM conversation_turns WHERE conversation_id = ? ORDER BY turn_id",
      [fixture.conversationId],
    )).toEqual([
      { turn_id: userTurnId, role: "user", status: "completed" },
      { turn_id: assistantTurnId, role: "assistant", status: "completed" },
    ]);
    const replay = listJournalTurns(relaunched, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
    }).turns;
    expect(replay.map((turn) => [turn.turnId, turn.status])).toEqual([
      [userTurnId, "completed"],
      [assistantTurnId, "streaming"],
      [assistantTurnId, "completed"],
    ]);
    const canonicalUser = relaunched.getRow(
      "SELECT turn_id, role, status, content FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?",
      [fixture.conversationId, userTurnId],
    );
    const canonicalAssistant = relaunched.getRow(
      `SELECT turn_id, role, status, content, content_blocks_json, resources_json
       FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?`,
      [fixture.conversationId, assistantTurnId],
    );
    expect(canonicalUser).toMatchObject({
      turn_id: userTurnId,
      role: "user",
      status: "completed",
    });
    expect(canonicalAssistant).toMatchObject({
      turn_id: assistantTurnId,
      role: "assistant",
      status: "completed",
      content: fullText,
    });
    expect(JSON.parse(String(canonicalAssistant.content_blocks_json))).toEqual([
      { type: "text", id: "lost-ack:assistant", text: fullText },
      preservedSpawn,
    ]);
    expect(JSON.parse(String(canonicalAssistant.resources_json))).toEqual([terminalResource]);
    expect(String(canonicalAssistant.content)).not.toBe("RELAUNCH-PERSIST-1");
    relaunched.close();
  });

  it("rejects stale, unknown, and nonterminal attempt proofs without mutating the turn", () => {
    const fixture = newSurface("task_chat", "task", "terminal-authority");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_terminal_authority",
      clientId: "task-chat",
      requestId: "terminal-authority",
      status: "succeeded",
      mode: "act",
    });
    const stale = fixture.store.insertAttempt({
      attemptId: "att_terminal_stale",
      runId: run.runId,
      attemptNo: 1,
      status: "failed",
      adapterId: "fake",
      adapterInstanceId: "fake:stale",
    });
    const latest = fixture.store.insertAttempt({
      attemptId: "att_terminal_latest",
      runId: run.runId,
      attemptNo: 2,
      status: "succeeded",
      adapterId: "fake",
      adapterInstanceId: "fake:latest",
    });
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-authority",
      role: "assistant",
      surfaceKind: "task_chat",
      origin: "task_chat",
      status: "streaming",
      content: "Unchanged",
      contentBlocks: [],
      producingRunId: run.runId,
      producingAttemptId: latest.attemptId,
      createdAtMs: 20,
    });
    const input = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-authority",
      producingRunId: run.runId,
      producingAttemptId: stale.attemptId,
      disposition: "accept" as const,
      content: "Must not land",
      replaceContentBlocks: [] as ConversationContentBlock[],
      replaceResources: [] as ConversationResource[],
      nowMs: 21,
    };
    const before = journalStorageSnapshot(fixture.store);
    expect(() => terminalizeJournalTurn(fixture.store, input)).toThrow(/latest canonical run attempt/i);
    expect(() => terminalizeJournalTurn(fixture.store, {
      ...input,
      producingAttemptId: "att_unknown",
    })).toThrow(/unknown or outside owner scope/i);
    expect(journalStorageSnapshot(fixture.store)).toEqual(before);

    const completed = terminalizeJournalTurn(fixture.store, {
      ...input,
      producingAttemptId: latest.attemptId,
      content: "Latest wins",
      nowMs: 22,
    });
    expect(completed).toMatchObject({ status: "completed", producingAttemptId: latest.attemptId });
    const after = journalStorageSnapshot(fixture.store);
    expect(() => terminalizeJournalTurn(fixture.store, input)).toThrow(/latest canonical run attempt/i);
    expect(journalStorageSnapshot(fixture.store)).toEqual(after);

    const activeRun = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_terminal_active",
      clientId: "task-chat",
      requestId: "terminal-active",
      status: "running",
      mode: "act",
    });
    const activeAttempt = fixture.store.insertAttempt({
      attemptId: "att_terminal_active",
      runId: activeRun.runId,
      attemptNo: 1,
      status: "running",
      adapterId: "fake",
      adapterInstanceId: "fake:active",
    });
    expect(() => terminalizeJournalTurn(fixture.store, {
      ...input,
      producingRunId: activeRun.runId,
      producingAttemptId: activeAttempt.attemptId,
    })).toThrow(/requires a terminal canonical run and attempt/i);
    fixture.store.close();
  });

  it("maps a canonical cancelled run to a failed journal terminal state atomically", () => {
    const fixture = newSurface("task_chat", "task", "terminal-cancelled");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_terminal_cancelled",
      clientId: "task-chat",
      requestId: "terminal-cancelled",
      status: "cancelled",
      mode: "act",
    });
    const attempt = fixture.store.insertAttempt({
      attemptId: "att_terminal_cancelled",
      runId: run.runId,
      attemptNo: 1,
      status: "cancelled",
      adapterId: "fake",
      adapterInstanceId: "fake:cancelled",
    });
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-cancelled",
      role: "assistant",
      surfaceKind: "task_chat",
      origin: "task_chat",
      status: "pending",
      content: "",
      contentBlocks: [],
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      createdAtMs: 30,
    });
    const failed = terminalizeJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-terminal-cancelled",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "accept",
      content: "Cancelled",
      replaceContentBlocks: [{ type: "text", id: "cancelled:text", text: "Cancelled" }],
      replaceResources: [],
      nowMs: 31,
    });
    expect(failed).toMatchObject({
      status: "failed",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      content: "Cancelled",
    });
    fixture.store.close();
  });

  it("preserves kernel-owned agent blocks and resources across stale final accept replacement", () => {
    const fixture = newSurface("main_chat", "chat", "monotonic-accept");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_monotonic_accept",
      clientId: "main-chat",
      requestId: "monotonic-accept",
      status: "succeeded",
      mode: "act",
    });
    const attempt = fixture.store.insertAttempt({
      attemptId: "att_monotonic_accept",
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "fake",
      adapterInstanceId: "fake:monotonic",
    });
    const spawn: ConversationContentBlock = {
      type: "agentSpawn",
      id: "monotonic:spawn",
      pillId: "pill-monotonic",
      sessionId: "ses-child-monotonic",
      runId: "run-child-monotonic",
      title: "Child agent",
      objective: "Preserve durable child state",
    };
    const completion: ConversationContentBlock = {
      type: "agentCompletion",
      id: "monotonic:completion",
      pillId: "pill-monotonic",
      sessionId: "ses-child-monotonic",
      runId: "run-child-monotonic",
      title: "Child agent",
      promptSnippet: "Preserve durable child state",
      output: "Child finished",
      status: "completed",
    };
    const resource: ConversationResource = {
      id: "monotonic:resource",
      origin: "generatedArtifact",
      title: "Child artifact",
      state: "retained",
      artifactId: "artifact-monotonic",
      runId: "run-child-monotonic",
    };
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-monotonic-accept",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "streaming",
      content: "Early text",
      contentBlocks: [{ type: "text", id: "monotonic:text", text: "Early text" }, spawn],
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      createdAtMs: 40,
    });
    updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-monotonic-accept",
      appendContentBlocks: [completion],
      appendResources: [resource],
      nowMs: 41,
    });

    const terminal = terminalizeJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-monotonic-accept",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "accept",
      content: "Final text",
      replaceContentBlocks: [{ type: "text", id: "monotonic:text", text: "Final text" }],
      replaceResources: [],
      nowMs: 42,
    });
    expect(terminal).toMatchObject({
      status: "completed",
      content: "Final text",
      contentBlocks: [
        { type: "text", id: "monotonic:text", text: "Final text" },
        spawn,
        completion,
      ],
      resources: [resource],
    });

    const lateCompletion: ConversationContentBlock = {
      ...completion,
      id: "monotonic:completion-late",
      output: "Late durable completion",
    };
    const lateResource: ConversationResource = {
      ...resource,
      id: "monotonic:resource-late",
      artifactId: "artifact-monotonic-late",
    };
    const append = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: terminal.turnId,
      appendContentBlocks: [lateCompletion],
      appendResources: [lateResource],
      nowMs: 43,
    };
    expect(() => assertPublicJournalUpdatePolicy(fixture.store, append)).not.toThrow();
    expect(updateJournalTurn(fixture.store, append)).toMatchObject({
      contentBlocks: expect.arrayContaining([lateCompletion]),
      resources: expect.arrayContaining([lateResource]),
    });
    const beforeRejected = journalStorageSnapshot(fixture.store);
    const replacement = {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: terminal.turnId,
      content: "Late replacement",
      replaceContentBlocks: [] as ConversationContentBlock[],
      nowMs: 44,
    };
    expect(() => assertPublicJournalUpdatePolicy(fixture.store, replacement)).toThrow(
      /only typed completion\/resource appends/i,
    );
    expect(journalStorageSnapshot(fixture.store)).toEqual(beforeRejected);
    fixture.store.close();
  });

  it("rejects every queued public mutation after an exact discard without changing journal state", () => {
    const fixture = newSurface("main_chat", "chat", "discard-guard");
    const run = fixture.store.insertRun({
      sessionId: fixture.sessionId,
      runId: "run_discard_guard",
      clientId: "main-chat",
      requestId: "discard-guard",
      status: "cancelled",
      mode: "act",
    });
    const attempt = fixture.store.insertAttempt({
      attemptId: "att_discard_guard",
      runId: run.runId,
      attemptNo: 1,
      status: "cancelled",
      adapterId: "fake",
      adapterInstanceId: "fake:discard",
    });
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-discard-guard",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "streaming",
      content: "Do not resurrect",
      contentBlocks: [{ type: "text", id: "discard:text", text: "Do not resurrect" }],
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      createdAtMs: 50,
    });
    terminalizeJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-discard-guard",
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      disposition: "discard",
      nowMs: 51,
    });
    const before = journalStorageSnapshot(fixture.store);
    for (const update of [
      { content: "Late delta" },
      { status: "streaming" as const },
      { replaceContentBlocks: [] as ConversationContentBlock[] },
      { appendResources: [{
        id: "discard:late-resource",
        origin: "generatedArtifact" as const,
        title: "Late",
        state: "retained" as const,
        runId: run.runId,
      }] },
    ]) {
      expect(() => assertPublicJournalUpdatePolicy(fixture.store, {
        ownerId: fixture.ownerId,
        conversationId: fixture.conversationId,
        turnId: "turn-discard-guard",
        ...update,
      })).toThrow(/rejects every public update/i);
    }
    expect(journalStorageSnapshot(fixture.store)).toEqual(before);
    expect(fixture.store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-discard-guard"],
    )).toEqual({ status: "failed", last_error_code: "discarded_terminal_projection" });
    fixture.store.close();
  });

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

  it("quarantines a canonical-hash-mismatched outbox row instead of wedging the pump", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    // Two completed turns → two pending outbox rows.
    recordCompletedTextTurn(fixture, "turn-poisoned", "First answer", 10);
    recordCompletedTextTurn(fixture, "turn-healthy", "Second answer", 20);

    // Simulate the durable corruption seen in the field: the stored outbox
    // payload hash diverges from the canonical journal turn. Previously this
    // threw out of the batch transaction, so the 1s pump re-selected the same
    // row forever and never delivered any turn.
    fixture.store.execute(
      "UPDATE backend_turn_outbox SET payload_hash = ? WHERE turn_id = ?",
      ["stale-divergent-hash", "turn-poisoned"],
    );

    const quarantined: string[] = [];
    const deliveries = drainBackendTurnOutbox(fixture.store, {
      nowMs: 30,
      onQuarantine: (turnId) => quarantined.push(turnId),
    });

    // The healthy turn still delivers; the poisoned row is parked, not thrown.
    expect(deliveries.map((d) => d.turnId)).toEqual(["turn-healthy"]);
    expect(quarantined).toEqual(["turn-poisoned"]);
    const parked = fixture.store.getRow(
      "SELECT status, last_error_code FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-poisoned"],
    );
    expect(parked).toMatchObject({
      status: "failed",
      last_error_code: OUTBOX_CANONICAL_HASH_MISMATCH_CODE,
    });

    // Re-draining does not re-select the parked row: the pump makes progress and
    // stops hot-looping (no second quarantine, no throw).
    const secondQuarantine: string[] = [];
    const secondPass = drainBackendTurnOutbox(fixture.store, {
      nowMs: 60,
      onQuarantine: (turnId) => secondQuarantine.push(turnId),
    });
    expect(secondPass).toEqual([]);
    expect(secondQuarantine).toEqual([]);

    // A later legitimate mutation re-stamps the hash and re-arms delivery.
    updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-poisoned",
      content: "First answer, revised",
      contentBlocks: [{ type: "text", id: "turn-poisoned:text", text: "First answer, revised" }],
      status: "completed",
      nowMs: 70,
    });
    const rearmed = drainBackendTurnOutbox(fixture.store, { nowMs: 80 });
    expect(rearmed.map((d) => d.turnId)).toEqual(["turn-poisoned"]);
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

  it("absorbs only a proven superseded backend turn claim after a journal revision", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-superseded", "revision one", 20);
    const [revisionOneClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 21 });
    updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-superseded",
      content: "revision two",
      nowMs: 22,
    });
    expect(fixture.store.getRow(
      `SELECT status, attempt_count, delivery_generation, payload_hash
       FROM backend_turn_outbox WHERE turn_id = ?`,
      ["turn-superseded"],
    )).toMatchObject({
      status: "pending",
      attempt_count: 0,
      delivery_generation: revisionOneClaim.deliveryGeneration,
    });
    expect(classifyBackendTurnResultDisposition(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionOneClaim.turnId,
      conversationId: revisionOneClaim.conversationId,
      attemptCount: revisionOneClaim.attemptCount,
      deliveryGeneration: revisionOneClaim.deliveryGeneration,
      conversationGeneration: revisionOneClaim.conversationGeneration,
      payloadHash: revisionOneClaim.payloadHash,
      ok: true,
      remoteId: "remote-revision-one",
    })).toBe("superseded");
    expect(() => ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionOneClaim.turnId,
      remoteId: "remote-revision-one",
      attemptCount: revisionOneClaim.attemptCount,
      deliveryGeneration: revisionOneClaim.deliveryGeneration,
      conversationGeneration: revisionOneClaim.conversationGeneration,
      payloadHash: revisionOneClaim.payloadHash,
    })).toThrow(/active claimed generation/);

    const [revisionTwoClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 23 });
    expect(revisionTwoClaim.deliveryGeneration).toBeGreaterThan(revisionOneClaim.deliveryGeneration);
    expect(classifyBackendTurnResultDisposition(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionOneClaim.turnId,
      conversationId: revisionOneClaim.conversationId,
      attemptCount: revisionOneClaim.attemptCount,
      deliveryGeneration: revisionOneClaim.deliveryGeneration,
      conversationGeneration: revisionOneClaim.conversationGeneration,
      payloadHash: revisionOneClaim.payloadHash,
      ok: true,
      remoteId: "remote-revision-one",
    })).toBe("superseded");
    expect(classifyBackendTurnResultDisposition(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionTwoClaim.turnId,
      conversationId: revisionTwoClaim.conversationId,
      attemptCount: revisionTwoClaim.attemptCount,
      deliveryGeneration: revisionTwoClaim.deliveryGeneration,
      conversationGeneration: revisionTwoClaim.conversationGeneration,
      payloadHash: revisionTwoClaim.payloadHash,
      ok: true,
      remoteId: "remote-revision-two",
    })).toBe("active");
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionOneClaim.turnId,
      conversationId: revisionOneClaim.conversationId,
      attemptCount: revisionOneClaim.attemptCount,
      deliveryGeneration: revisionTwoClaim.deliveryGeneration,
      conversationGeneration: revisionOneClaim.conversationGeneration,
      payloadHash: revisionOneClaim.payloadHash,
      ok: true,
      remoteId: "forged-same-generation",
    })).toThrow(/does not match the active claimed generation/i);

    ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionTwoClaim.turnId,
      remoteId: "remote-revision-two",
      attemptCount: revisionTwoClaim.attemptCount,
      deliveryGeneration: revisionTwoClaim.deliveryGeneration,
      conversationGeneration: revisionTwoClaim.conversationGeneration,
      payloadHash: revisionTwoClaim.payloadHash,
      nowMs: 24,
    });
    expect(classifyBackendTurnResultDisposition(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: revisionOneClaim.turnId,
      conversationId: revisionOneClaim.conversationId,
      attemptCount: revisionOneClaim.attemptCount,
      deliveryGeneration: revisionOneClaim.deliveryGeneration,
      conversationGeneration: revisionOneClaim.conversationGeneration,
      payloadHash: revisionOneClaim.payloadHash,
      ok: true,
      remoteId: "remote-revision-one",
    })).toBe("superseded");

    const activeResult = {
      ownerId: fixture.ownerId,
      turnId: revisionTwoClaim.turnId,
      conversationId: revisionTwoClaim.conversationId,
      attemptCount: revisionTwoClaim.attemptCount,
      deliveryGeneration: revisionTwoClaim.deliveryGeneration,
      conversationGeneration: revisionTwoClaim.conversationGeneration,
      payloadHash: revisionTwoClaim.payloadHash,
      ok: true,
      remoteId: "remote-revision-two",
    } as const;
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...activeResult,
      ownerId: "other-owner",
    })).toThrow(/owner does not match/i);
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...activeResult,
      conversationId: "other-conversation",
    })).toThrow(/conversation does not match/i);
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...activeResult,
      deliveryGeneration: revisionTwoClaim.deliveryGeneration + 1,
    })).toThrow(/future delivery generation/i);
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...activeResult,
      payloadHash: "sha256:forged-same-generation",
    })).toThrow(/never a canonical journal revision/i);
    fixture.store.close();
  });

  it("recognizes exact duplicate backend results but rejects conflicting replays", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-duplicate-success", "success", 30);
    const [successClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 31 });
    ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: successClaim.turnId,
      remoteId: "remote-success",
      attemptCount: successClaim.attemptCount,
      deliveryGeneration: successClaim.deliveryGeneration,
      conversationGeneration: successClaim.conversationGeneration,
      payloadHash: successClaim.payloadHash,
      nowMs: 32,
    });
    const successResult = {
      ownerId: fixture.ownerId,
      turnId: successClaim.turnId,
      conversationId: successClaim.conversationId,
      attemptCount: successClaim.attemptCount,
      deliveryGeneration: successClaim.deliveryGeneration,
      conversationGeneration: successClaim.conversationGeneration,
      payloadHash: successClaim.payloadHash,
      ok: true,
      remoteId: "remote-success",
    } as const;
    expect(classifyBackendTurnResultDisposition(fixture.store, successResult)).toBe("duplicate");
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...successResult,
      remoteId: "conflicting-remote",
    })).toThrow(/conflicts with the delivered result/i);

    recordCompletedTextTurn(fixture, "turn-duplicate-failure", "failure", 33);
    const [failureClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 34 });
    failBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: failureClaim.turnId,
      attemptCount: failureClaim.attemptCount,
      deliveryGeneration: failureClaim.deliveryGeneration,
      conversationGeneration: failureClaim.conversationGeneration,
      payloadHash: failureClaim.payloadHash,
      errorCode: "backend_sync_http_retryable",
      nowMs: 35,
    });
    const failureResult = {
      ownerId: fixture.ownerId,
      turnId: failureClaim.turnId,
      conversationId: failureClaim.conversationId,
      attemptCount: failureClaim.attemptCount,
      deliveryGeneration: failureClaim.deliveryGeneration,
      conversationGeneration: failureClaim.conversationGeneration,
      payloadHash: failureClaim.payloadHash,
      ok: false,
      errorCode: "backend_sync_http_retryable",
    } as const;
    expect(classifyBackendTurnResultDisposition(fixture.store, failureResult)).toBe("duplicate");
    expect(() => classifyBackendTurnResultDisposition(fixture.store, {
      ...failureResult,
      errorCode: "different_failure",
    })).toThrow(/conflicts with the settled result/i);
    fixture.store.close();
  });

  it("requeues each newer canonical revision once and rejects stale delivery claims", () => {
    const fixture = newSurface("main_chat", "chat", "revision-aware");
    recordCompletedTextTurn(fixture, "turn-revision-aware", "Version one", 10);

    const [firstClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 11 });
    expect(firstClaim).toMatchObject({
      attemptCount: 1,
      deliveryGeneration: 1,
      payload: { journalRevision: 1, text: "Version one" },
    });
    ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: firstClaim.turnId,
      remoteId: "remote-revision-aware",
      attemptCount: firstClaim.attemptCount,
      deliveryGeneration: firstClaim.deliveryGeneration,
      conversationGeneration: firstClaim.conversationGeneration,
      payloadHash: firstClaim.payloadHash,
      nowMs: 12,
    });

    const revised = updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: firstClaim.turnId,
      content: "Version two",
      replaceContentBlocks: [{ type: "text", id: "turn-revision-aware:text", text: "Version two" }],
      nowMs: 13,
    });
    expect(revised.turnSeq).toBe(3);
    expect(fixture.store.getRow(
      `SELECT status, attempt_count, remote_id FROM backend_turn_outbox WHERE turn_id = ?`,
      [firstClaim.turnId],
    )).toEqual({ status: "pending", attempt_count: 0, remote_id: "remote-revision-aware" });
    const beforeReplay = fixture.store.getRow(
      `SELECT turn_seq, payload_hash FROM conversation_turns WHERE turn_id = ?`,
      [firstClaim.turnId],
    );
    updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: firstClaim.turnId,
      content: "Version two",
      replaceContentBlocks: [{ type: "text", id: "turn-revision-aware:text", text: "Version two" }],
      nowMs: 14,
    });
    expect(fixture.store.getRow(
      `SELECT turn_seq, payload_hash FROM conversation_turns WHERE turn_id = ?`,
      [firstClaim.turnId],
    )).toEqual(beforeReplay);

    const [secondClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 15 });
    expect(secondClaim).toMatchObject({
      attemptCount: 1,
      deliveryGeneration: 2,
      payload: {
        journalRevision: revised.turnSeq,
        text: "Version two",
      },
    });
    expect(() => ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: firstClaim.turnId,
      remoteId: "remote-revision-aware",
      attemptCount: firstClaim.attemptCount,
      deliveryGeneration: firstClaim.deliveryGeneration,
      conversationGeneration: firstClaim.conversationGeneration,
      payloadHash: firstClaim.payloadHash,
      nowMs: 16,
    })).toThrow(/active claimed generation/);
    ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: secondClaim.turnId,
      remoteId: "remote-revision-aware",
      attemptCount: secondClaim.attemptCount,
      deliveryGeneration: secondClaim.deliveryGeneration,
      conversationGeneration: secondClaim.conversationGeneration,
      payloadHash: secondClaim.payloadHash,
      nowMs: 17,
    });
    expect(drainBackendTurnOutbox(fixture.store, { nowMs: 18 })).toEqual([]);

    const newest = updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: firstClaim.turnId,
      content: "Version three",
      nowMs: 19,
    });
    const [thirdClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 20 });
    expect(thirdClaim.payload.journalRevision).toBe(newest.turnSeq);
    expect(thirdClaim.payload.journalRevision).toBeGreaterThan(secondClaim.payload.journalRevision);
    expect(thirdClaim.deliveryGeneration).toBe(3);
    fixture.store.close();
  });

  it("converges a newer revision after the first backend acknowledgement is lost", () => {
    const fixture = newSurface("main_chat", "chat", "lost-ack");
    recordCompletedTextTurn(fixture, "turn-lost-ack", "Initial projection", 30);
    const [lostAckClaim] = drainBackendTurnOutbox(fixture.store, { nowMs: 31, leaseMs: 60_000 });
    expect(lostAckClaim.payload).toMatchObject({
      clientMessageId: "turn-lost-ack",
      journalRevision: 1,
      text: "Initial projection",
    });

    const enriched = updateJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: lostAckClaim.turnId,
      content: "Enriched projection",
      nowMs: 32,
    });
    expect(fixture.store.getRow(
      `SELECT status, attempt_count, delivery_generation, remote_id
       FROM backend_turn_outbox WHERE turn_id = ?`,
      [lostAckClaim.turnId],
    )).toEqual({ status: "pending", attempt_count: 0, delivery_generation: 1, remote_id: null });

    const [retry] = drainBackendTurnOutbox(fixture.store, { nowMs: 33 });
    expect(retry).toMatchObject({
      attemptCount: 1,
      deliveryGeneration: 2,
      payload: {
        clientMessageId: lostAckClaim.payload.clientMessageId,
        journalRevision: enriched.turnSeq,
        text: "Enriched projection",
      },
    });
    expect(() => ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: lostAckClaim.turnId,
      remoteId: "remote-lost-ack",
      attemptCount: lostAckClaim.attemptCount,
      deliveryGeneration: lostAckClaim.deliveryGeneration,
      conversationGeneration: lostAckClaim.conversationGeneration,
      payloadHash: lostAckClaim.payloadHash,
      nowMs: 34,
    })).toThrow(/active claimed generation/);
    expect(ackBackendTurnOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      turnId: retry.turnId,
      remoteId: "remote-lost-ack",
      attemptCount: retry.attemptCount,
      deliveryGeneration: retry.deliveryGeneration,
      conversationGeneration: retry.conversationGeneration,
      payloadHash: retry.payloadHash,
      nowMs: 35,
    })).toMatchObject({ status: "delivered", remoteId: "remote-lost-ack" });
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

  it("repairs a startup-terminalized turn before it can starve later backend chat sync", () => {
    const databasePath = newDatabasePath();
    let store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 100 });
    const fixture = insertSurface(store, "main_chat", "chat", "restart-outbox");
    recordCompletedTextTurn(fixture, "turn-already-delivered", "Do not resend", 5);
    const [deliveredClaim] = drainBackendTurnOutbox(store, { nowMs: 6 });
    ackBackendTurnOutbox(store, {
      ownerId: fixture.ownerId,
      turnId: deliveredClaim.turnId,
      remoteId: "remote-already-delivered",
      attemptCount: deliveredClaim.attemptCount,
      deliveryGeneration: deliveredClaim.deliveryGeneration,
      conversationGeneration: deliveredClaim.conversationGeneration,
      payloadHash: deliveredClaim.payloadHash,
      nowMs: 7,
    });
    const run = store.insertRun({
      sessionId: fixture.sessionId,
      clientId: "client",
      requestId: "interrupted-after-run-success",
      status: "succeeded",
      mode: "ask",
      completedAtMs: 11,
    });
    const attempt = store.insertAttempt({
      runId: run.runId,
      attemptNo: 1,
      status: "succeeded",
      adapterId: "acp",
      adapterInstanceId: "",
      completedAtMs: 11,
    });
    recordJournalTurn(store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-interrupted",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "agent_runtime",
      status: "streaming",
      content: "",
      contentBlocks: [],
      producingRunId: run.runId,
      producingAttemptId: attempt.attemptId,
      createdAtMs: 10,
    });
    const staleHash = String(store.getRow(
      "SELECT payload_hash FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-interrupted"],
    ).payload_hash);
    store.close();

    store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false, nowMs: () => 20 });
    expect(store.reconcileStartup()).toMatchObject({
      reconciledJournalTurnIds: ["turn-interrupted"],
      repairedBackendTurnOutboxIds: ["turn-interrupted"],
    });
    const repairedOutbox = store.getRow(
      "SELECT status, last_error_code, payload_hash FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-interrupted"],
    );
    expect(repairedOutbox).toMatchObject({
      status: "failed",
      last_error_code: "empty_completed_turn_cancelled",
    });
    expect(repairedOutbox.payload_hash).not.toBe(staleHash);
    expect(store.getRow(
      "SELECT status, remote_id FROM backend_turn_outbox WHERE turn_id = ?",
      ["turn-already-delivered"],
    )).toEqual({
      status: "delivered",
      remote_id: "remote-already-delivered",
    });

    const resumedFixture = {
      store,
      ownerId: fixture.ownerId,
      sessionId: fixture.sessionId,
      conversationId: fixture.conversationId,
    };
    recordCompletedTextTurn(resumedFixture, "turn-after-restart", "Chat still syncs", 30);
    expect(drainBackendTurnOutbox(store, { nowMs: 31 })).toMatchObject([
      {
        turnId: "turn-after-restart",
        payload: { text: "Chat still syncs" },
      },
    ]);
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
        createdAtMs: 20,
      })).toMatchObject({ created: true, outboxStatus: null });
    }
    expect(store.getRow("SELECT COUNT(*) AS count FROM conversation_turns").count).toBe(2);
    expect(store.getRow("SELECT COUNT(*) AS count FROM backend_turn_outbox").count).toBe(0);
    expect(recordJournalTurn(store, {
      ownerId: task.ownerId,
      conversationId: task.conversationId,
      role: "user",
      surfaceKind: "task_chat",
      origin: "task_chat",
      content: "Wrong destination",
      contentBlocks: [{ type: "text", id: "wrong:text", text: "Wrong destination" }],
    })).toMatchObject({ created: true, outboxStatus: null });
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

  it("local-only clear purges local turns without enqueuing a backend delete", () => {
    const fixture = newSurface("main_chat", "chat", "default");
    recordCompletedTextTurn(fixture, "turn-local-only-1", "hello", 10);
    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 90,
      deleteBackend: false,
    });
    // Local turns are purged and the generation is fenced, but nothing is
    // enqueued to delete the user's server-side chat history.
    expect(cleared.deletedTurns).toBe(1);
    expect(cleared.backendDeleteOperationId).toBeNull();
    expect(drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 91,
    })).toHaveLength(0);
    fixture.store.close();
  });

  it("canonical local-only ownership suppresses backend deletion even when a caller requests it", () => {
    const fixture = newSurface("onboarding", "session", "default");
    recordJournalTurn(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      turnId: "turn-local-onboarding",
      role: "assistant",
      surfaceKind: "onboarding",
      origin: "agent_runtime",
      status: "completed",
      content: "setup only",
      contentBlocks: [{ type: "text", id: "setup:text", text: "setup only" }],
      createdAtMs: 10,
    });
    const cleared = clearJournalConversation(fixture.store, {
      ownerId: fixture.ownerId,
      conversationId: fixture.conversationId,
      expectedGeneration: 1,
      nowMs: 90,
      deleteBackend: true,
    });

    expect(cleared.deletedTurns).toBe(1);
    expect(cleared.backendDeleteOperationId).toBeNull();
    expect(drainBackendConversationDeleteOutbox(fixture.store, {
      ownerId: fixture.ownerId,
      nowMs: 91,
    })).toEqual([]);
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
