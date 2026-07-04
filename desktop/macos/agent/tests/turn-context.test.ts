import { describe, expect, it, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import {
  appendConversationTurn,
  importConversationTurnsBackfill,
  recordSurfaceTurn,
  listRecentConversationTurns,
} from "../src/runtime/conversation-turns.js";
import {
  assembleTurnContext,
  bindingCarriesNativeHistory,
  getVoiceSeedContext,
  shouldInjectCompletedAgentDelta,
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

  it("does not inject transcript history when binding is native-resumable", () => {
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
      nowMs: 1_700_000_000_100,
    });

    expect(assembled.prompt).not.toContain("<conversation_history>");
    expect(assembled.prompt).not.toContain("Earlier question");
    expect(assembled.prompt).toContain("# User Message");
    expect(assembled.prompt).toContain("Follow up");
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
    expect(assembled.prompt).toContain("User: Hello");
    expect(assembled.prompt).toContain("Assistant: Hi there");
  });

  it("matches completion follow-up heuristics", () => {
    expect(shouldInjectCompletedAgentDelta("is the agent done yet?")).toBe(true);
    expect(shouldInjectCompletedAgentDelta("ask an agent to build a file")).toBe(false);
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
    expect(seed).toContain("User: Hello from PTT");
    expect(seed).toContain("Omi: Hi back");
    expect(seed).toContain("User: Interrupted question");
    expect(seed).toContain("Omi (interrupted): Partial reply");
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
});
