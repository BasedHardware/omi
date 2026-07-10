import { describe, expect, it, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import {
  appendConversationTurn,
  advanceBindingTurnDelivery,
  importConversationTurnsBackfill,
  recordSurfaceTurn,
  listRecentConversationTurns,
} from "../src/runtime/conversation-turns.js";
import {
  assembleTurnContext,
  bindingCarriesNativeHistory,
  getVoiceSeedContext,
  getVoiceSeedSnapshot,
  isExplicitAgentControlToolTurn,
  isLeafWorkerSurface,
  leafWorkerExecutionBoundary,
  shouldInjectCoordinatorRoute,
  shouldInjectCompletedAgentDelta,
  turnSourceAttribution,
  VOICE_SEED_MAX_CHARACTERS,
} from "../src/runtime/turn-context.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";

function newStore(): { store: SqliteAgentStore; stateDir: string } {
  const stateDir = mkdtempSync(join(tmpdir(), "omi-turn-context-"));
  return {
    stateDir,
    store: new SqliteAgentStore({ stateDir, reconcileOnOpen: false }),
  };
}

describe("turn-context", () => {
  let cleanupDir: string | undefined;

  afterEach(() => {
    if (cleanupDir) {
      rmSync(cleanupDir, { recursive: true, force: true });
      cleanupDir = undefined;
    }
  });

  it("gives floating-pill workers a leaf-only execution boundary", () => {
    const surfaceRef = { surfaceKind: "floating_bar", externalRefKind: "pill", externalRefId: "pill-1" };
    expect(isLeafWorkerSurface(surfaceRef)).toBe(true);
    expect(leafWorkerExecutionBoundary(surfaceRef)).toContain("cannot create more agents");
  });

  it("keeps main-chat coordinators able to create background work", () => {
    const surfaceRef = { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "chat-1" };
    expect(isLeafWorkerSurface(surfaceRef)).toBe(false);
    expect(leafWorkerExecutionBoundary(surfaceRef)).toBeNull();
  });

  it("does not inject undelivered transcript delta when native binding has seen all turns", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-turn-context";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    appendConversationTurn(store, {
      conversationId: resolved.conversationId,
      role: "user",
      surfaceKind: "main_chat",
      content: "Earlier question",
      createdAtMs: 1_700_000_000_000,
    });
    appendConversationTurn(store, {
      conversationId: resolved.conversationId,
      role: "assistant",
      surfaceKind: "main_chat",
      content: "Earlier answer",
      createdAtMs: 1_700_000_000_001,
    });

    const assembled = assembleTurnContext({
      store,
      services: {
        persistDesktopContextPacket: (input) => ({
          packet: {
            packetId: "ctx_test",
            redactedPreviewJson: { objective: input.objective },
          },
        }),
        routeDesktopIntent: () => ({ intent: "new_run", explanation: "test" }),
        listSessions: () => [],
        inspectArtifacts: () => [],
      },
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "Follow up",
      imagePresent: false,
      bindingCarriesNativeHistory: bindingCarriesNativeHistory({
        status: "active",
        resumeFidelity: "native",
        adapterNativeSessionId: "adapter-native-1",
      }),
      lastDeliveredTurnCreatedAtMs: 1_700_000_000_001,
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).not.toContain("# Recent turns from other surfaces");
    expect(assembled.prompt).not.toContain("<conversation_history>");
    expect(assembled.prompt).not.toContain("Earlier question");
    expect(assembled.prompt).toContain("# User Message");
    expect(assembled.prompt).toContain("Follow up");
  });

  it("injects voice turns once into warm native binding delta", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-native-voice-delta";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    appendConversationTurn(store, {
      conversationId: resolved.conversationId,
      role: "user",
      surfaceKind: "main_chat",
      content: "Typed question",
      createdAtMs: 1_700_000_000_000,
    });
    appendConversationTurn(store, {
      conversationId: resolved.conversationId,
      role: "assistant",
      surfaceKind: "main_chat",
      content: "Typed answer",
      createdAtMs: 1_700_000_000_001,
    });
    const binding = store.insertAdapterBinding({
      sessionId: resolved.agentSessionId,
      adapterId: "pi-mono",
      bindingGeneration: 1,
      adapterNativeSessionId: "native-warm-1",
      resumeFidelity: "native",
      status: "active",
      lastDeliveredTurnCreatedAtMs: 1_700_000_000_001,
    });

    recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "Hello from PTT",
      assistantText: "Hi back from voice",
      origin: "realtime_voice",
      nowMs: 1_700_000_000_010,
    });

    const services = {
      persistDesktopContextPacket: (input: { objective: string }) => ({
        packet: {
          packetId: "ctx_test",
          redactedPreviewJson: { objective: input.objective },
        },
      }),
      routeDesktopIntent: () => ({ intent: "new_run" as const, explanation: "test" }),
      listSessions: () => [],
      inspectArtifacts: () => [],
    };

    const first = assembleTurnContext({
      store,
      services,
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "Follow up after voice",
      imagePresent: false,
      bindingCarriesNativeHistory: bindingCarriesNativeHistory(binding),
      lastDeliveredTurnCreatedAtMs: binding.lastDeliveredTurnCreatedAtMs,
      nowMs: 1_700_000_000_020,
    });

    expect(first.prompt).toContain("# Recent turns from other surfaces");
    expect(first.prompt).toContain("Hello from PTT");
    expect(first.prompt).toContain("Hi back from voice");
    expect(first.prompt).not.toContain("Typed question");

    advanceBindingTurnDelivery(store, binding.bindingId, resolved.conversationId, 1_700_000_000_021);
    const updatedBinding = store.getRow(
      "SELECT last_delivered_turn_created_at_ms FROM adapter_bindings WHERE binding_id = ?",
      [binding.bindingId],
    );
    const second = assembleTurnContext({
      store,
      services,
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "Another follow up",
      imagePresent: false,
      bindingCarriesNativeHistory: bindingCarriesNativeHistory(binding),
      lastDeliveredTurnCreatedAtMs: Number(updatedBinding.last_delivered_turn_created_at_ms),
      nowMs: 1_700_000_000_030,
    });

    expect(second.prompt).not.toContain("# Recent turns from other surfaces");
    expect(second.prompt).not.toContain("Hello from PTT");
  });

  it("injects bounded transcript tail for fresh bindings", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-fresh-binding";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    importConversationTurnsBackfill(store, {
      conversationId: resolved.conversationId,
      turns: [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi there" },
      ],
      nowMs: () => 1_700_000_000_000,
    });

    const assembled = assembleTurnContext({
      store,
      services: {
        persistDesktopContextPacket: (input) => ({
          packet: {
            packetId: "ctx_test",
            redactedPreviewJson: { objective: input.objective },
          },
        }),
        routeDesktopIntent: () => ({ intent: "new_run", explanation: "test" }),
        listSessions: () => [],
        inspectArtifacts: () => [],
      },
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "Next",
      imagePresent: false,
      bindingCarriesNativeHistory: false,
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).toContain("<conversation_history>");
    expect(assembled.prompt).toContain("[live:typed] User: Hello");
    expect(assembled.prompt).toContain("[live:typed] Assistant: Hi there");
  });

  it("does not duplicate transcript in context packet and history tail", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-dedupe";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    appendConversationTurn(store, {
      conversationId: resolved.conversationId,
      role: "user",
      surfaceKind: "main_chat",
      content: "Prior typed turn",
      createdAtMs: 1_700_000_000_000,
    });

    const assembled = assembleTurnContext({
      store,
      services: {
        persistDesktopContextPacket: (input) => ({
          packet: {
            packetId: "ctx_dedupe",
            redactedPreviewJson: { objective: input.objective, snippetCount: input.snippets.length },
          },
        }),
        routeDesktopIntent: () => ({ intent: "new_run", explanation: "test" }),
        listSessions: () => [],
        inspectArtifacts: () => [],
      },
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "Follow up",
      imagePresent: false,
      bindingCarriesNativeHistory: false,
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).toContain("# Context Packet");
    expect(assembled.prompt).toContain("<conversation_history>");
    expect(assembled.prompt).toContain("Prior typed turn");
    const occurrences = assembled.prompt.split("Prior typed turn").length - 1;
    expect(occurrences).toBe(1);
  });

  it("labels voice turns with live:voice attribution", () => {
    const turn = {
      conversationId: "conv-1",
      turnId: "turn-1",
      role: "user" as const,
      surfaceKind: "main_chat",
      content: "Hello",
      createdAtMs: 1,
      metadataJson: JSON.stringify({ origin: "realtime_voice" }),
    };
    expect(turnSourceAttribution(turn)).toBe("[live:voice]");
  });

  it("matches completion follow-up heuristics", () => {
    expect(shouldInjectCompletedAgentDelta("is the agent done yet?")).toBe(true);
    expect(shouldInjectCompletedAgentDelta("ask an agent to build a file")).toBe(false);
  });

  it("skips coordinator route when the user explicitly names spawn_agent", () => {
    expect(isExplicitAgentControlToolTurn("Use spawn_agent now to start a visible background agent.")).toBe(true);
    expect(shouldInjectCoordinatorRoute("Use spawn_agent now to start a visible background agent.")).toBe(false);
    expect(shouldInjectCoordinatorRoute("ask an agent to build a file")).toBe(true);
  });

  it("does not inject coordinator route for explicit spawn_agent turns", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-spawn-route";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    const spawnQuery =
      "Use spawn_agent now to start a visible background agent. Objective: track marker GAUNTLET-TEST-SPAWN and wait silently.";

    const assembled = assembleTurnContext({
      store,
      services: {
        persistDesktopContextPacket: (input) => ({
          packet: {
            packetId: "ctx_spawn",
            redactedPreviewJson: { objective: input.objective },
          },
        }),
        routeDesktopIntent: () => ({
          intent: "delegate",
          explanation: "The request appears to require long-running or specialist work.",
        }),
        listSessions: () => [],
        inspectArtifacts: () => [],
      },
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: spawnQuery,
      imagePresent: false,
      bindingCarriesNativeHistory: false,
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).not.toContain("[Desktop Coordinator Route Context]");
    expect(assembled.prompt).not.toContain("# Context Packet");
    expect(assembled.prompt).toContain("# User Message");
    expect(assembled.prompt).toContain(spawnQuery);
  });

  it("still injects coordinator route for delegated work without explicit tool names", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-delegate-route";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);

    const assembled = assembleTurnContext({
      store,
      services: {
        persistDesktopContextPacket: (input) => ({
          packet: {
            packetId: "ctx_delegate",
            redactedPreviewJson: { objective: input.objective },
          },
        }),
        routeDesktopIntent: () => ({
          intent: "delegate",
          explanation: "The request appears to require long-running or specialist work.",
        }),
        listSessions: () => [],
        inspectArtifacts: () => [],
      },
      ownerId,
      sessionId: resolved.agentSessionId,
      conversationId: resolved.conversationId,
      surfaceRef,
      userText: "ask an agent to build me a single page html iphone facts page",
      imagePresent: false,
      bindingCarriesNativeHistory: false,
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).toContain("[Desktop Coordinator Route Context]");
    expect(assembled.prompt).toContain("routeIntent=delegate");
  });

  it("projects voice seed context with one sanitizer and cap policy", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-voice-seed";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "Hello from PTT",
      assistantText: "Hi back",
      origin: "realtime_voice",
      nowMs: 1_700_000_000_000,
    });
    recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "Interrupted question",
      assistantText: "Partial reply",
      origin: "realtime_voice",
      interrupted: true,
      nowMs: 1_700_000_000_001,
    });

    const seed = getVoiceSeedContext(store, resolved.conversationId);
    expect(seed).toContain("[live:voice] User: Hello from PTT");
    expect(seed).toContain("[live:voice] Omi: Hi back");
    expect(seed).toContain("[live:voice] User: Interrupted question");
    expect(seed).toContain("[live:voice] Omi (interrupted): Partial reply");
    expect(seed.length).toBeLessThanOrEqual(VOICE_SEED_MAX_CHARACTERS + 64);
  });

  it("dedupes voice surface turns by idempotency key", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-voice-dedupe";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const first = recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "Same turn",
      assistantText: "Same reply",
      origin: "realtime_voice",
      idempotencyKey: "turn-42",
      nowMs: 1_700_000_000_000,
    });
    const second = recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "Same turn",
      assistantText: "Same reply",
      origin: "realtime_voice",
      idempotencyKey: "turn-42",
      nowMs: 1_700_000_000_100,
    });

    expect(first.recorded).toBe(true);
    expect(second.recorded).toBe(false);
    expect(second.duplicate).toBe(true);
    const turns = listRecentConversationTurns(store, first.conversationId, 10);
    expect(turns.filter((turn) => turn.role === "user")).toHaveLength(1);
    expect(turns.filter((turn) => turn.role === "assistant")).toHaveLength(1);
  });

  it("projects every rapid PTT user turn before the final assistant reply", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-rapid-ptt";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);

    for (const [index, text] of ["one two three", "A B C", "R G B"].entries()) {
      recordSurfaceTurn(store, {
        ownerId,
        surfaceRef,
        userText: text,
        assistantText: index === 2 ? "Red, green, blue." : "",
        origin: "realtime_voice",
        interrupted: index < 2,
        idempotencyKey: `realtime_voice:turn-${index}:user`,
        nowMs: 1_700_000_000_000 + index,
      });
    }
    const duplicate = recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText: "A B C",
      assistantText: "",
      origin: "realtime_voice",
      idempotencyKey: "realtime_voice:turn-1:user",
      nowMs: 1_700_000_000_020,
    });

    expect(duplicate.duplicate).toBe(true);
    const turns = listRecentConversationTurns(store, resolved.conversationId, 10);
    expect(turns.map((turn) => [turn.role, turn.content])).toEqual([
      ["user", "one two three"],
      ["user", "A B C"],
      ["user", "R G B"],
      ["assistant", "Red, green, blue."],
    ]);
    const seed = getVoiceSeedContext(store, resolved.conversationId);
    expect(seed).toContain("User: one two three");
    expect(seed).toContain("User: A B C");
    expect(seed).toContain("User: R G B");
    expect(seed).toContain("Omi: Red, green, blue.");
  });

  it("keeps the full retained rapid PTT burst in the Gemini replacement seed", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-long-rapid-ptt";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);

    for (let index = 0; index < 32; index += 1) {
      recordSurfaceTurn(store, {
        ownerId,
        surfaceRef,
        userText: `rapid transcript ${index}`,
        assistantText: index < 31 ? `partial reply ${index}` : "final reply",
        origin: "realtime_voice",
        interrupted: index < 31,
        idempotencyKey: `rapid-${index}`,
        nowMs: 1_700_000_000_000 + index * 2,
      });
    }

    const seed = getVoiceSeedContext(store, resolved.conversationId);
    expect(seed).toContain("User: rapid transcript 0");
    expect(seed).toContain("Omi (interrupted): partial reply 0");
    expect(seed).toContain("User: rapid transcript 31");
    expect(seed).toContain("Omi: final reply");
    expect(seed.length).toBeLessThanOrEqual(VOICE_SEED_MAX_CHARACTERS + 64);
  });

  it("spends an over-budget voice seed on the newest turns", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-over-budget-voice-seed";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);

    for (const [index, marker] of ["OLDEST-DROP-ME", "middle-one", "middle-two", "NEWEST-KEEP-ME"].entries()) {
      recordSurfaceTurn(store, {
        ownerId,
        surfaceRef,
        userText: `${marker} ${"x".repeat(100)}`,
        assistantText: "",
        origin: "realtime_voice",
        idempotencyKey: `budget-${index}`,
        nowMs: 1_700_000_000_000 + index,
      });
    }

    const seed = getVoiceSeedContext(store, resolved.conversationId, {
      maxTurns: 64,
      maxCharacters: 180,
    });
    expect(seed).toContain("NEWEST-KEEP-ME");
    expect(seed).not.toContain("OLDEST-DROP-ME");
  });

  it("includes floating spawn handoff in voice seed and dedupes by idempotency key", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const ownerId = "owner-spawn-handoff";
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(store, { ownerId, surfaceRef }, () => 1_700_000_000_000);
    const userText = "Build me a Penguin Facts HTML page";
    const assistantText = 'I started a background agent titled "Penguin Facts Page" for that.';
    const first = recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText,
      assistantText,
      origin: "floating_spawn",
      idempotencyKey: "floating_spawn:pill-abc",
      nowMs: 1_700_000_000_000,
    });
    const second = recordSurfaceTurn(store, {
      ownerId,
      surfaceRef,
      userText,
      assistantText,
      origin: "floating_spawn",
      idempotencyKey: "floating_spawn:pill-abc",
      nowMs: 1_700_000_000_100,
    });

    expect(first.recorded).toBe(true);
    expect(second.recorded).toBe(false);
    expect(second.duplicate).toBe(true);

    const seed = getVoiceSeedContext(store, resolved.conversationId);
    expect(seed).toContain("User: Build me a Penguin Facts HTML page");
    expect(seed).toContain('Omi: I started a background agent titled "Penguin Facts Page" for that.');
    const snapshot = getVoiceSeedSnapshot(store, resolved.conversationId);
    expect(snapshot.context).toBe(seed);
    expect(snapshot.idempotencyKeys).toEqual(["floating_spawn:pill-abc"]);
  });

  it("does not reconcile an idempotency key when its user row is truncated", () => {
    const { store, stateDir } = newStore();
    cleanupDir = stateDir;
    store.migrate();
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const resolved = resolveSurfaceSession(
      store,
      { ownerId: "owner-truncated-seed", surfaceRef },
      () => 1_700_000_000_000,
    );
    recordSurfaceTurn(store, {
      ownerId: "owner-truncated-seed",
      surfaceRef,
      userText: "the user transcription must survive",
      assistantText: "assistant ".repeat(30),
      origin: "realtime_voice",
      idempotencyKey: "partial-turn",
      nowMs: 1_700_000_000_000,
    });

    const truncated = getVoiceSeedSnapshot(store, resolved.conversationId, {
      maxTurns: 64,
      maxCharacters: 80,
    });
    expect(truncated.context).toContain("Omi:");
    expect(truncated.context).not.toContain("the user transcription must survive");
    expect(truncated.idempotencyKeys).not.toContain("partial-turn");

    const complete = getVoiceSeedSnapshot(store, resolved.conversationId);
    expect(complete.context).toContain("the user transcription must survive");
    expect(complete.idempotencyKeys).toContain("partial-turn");
  });
});
