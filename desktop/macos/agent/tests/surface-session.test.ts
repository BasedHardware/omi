import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { importLegacyMainChatSessions, mergeFloatingChatIntoMainChat, resolveSurfaceSession } from "../src/runtime/surface-session.js";

function newStore(): SqliteAgentStore {
  const dir = mkdtempSync(join(tmpdir(), "omi-surface-session-"));
  return new SqliteAgentStore({ stateDir: dir, reconcileOnOpen: false });
}

describe("surface_conversations", () => {
  let store: SqliteAgentStore;
  let stateDir: string;

  beforeEach(() => {
    const dir = mkdtempSync(join(tmpdir(), "omi-surface-session-"));
    stateDir = dir;
    store = new SqliteAgentStore({ stateDir: dir, reconcileOnOpen: false });
  });

  afterEach(() => {
    store.close();
    rmSync(stateDir, { recursive: true, force: true });
  });

  it("resolveSurfaceSession creates and reuses the same agent session", () => {
    const first = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
        defaultAdapterId: "acp",
      },
      () => 1,
    );
    const second = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
        defaultAdapterId: "acp",
      },
      () => 2,
    );

    expect(second.agentSessionId).toBe(first.agentSessionId);
    expect(second.conversationId).toBe(first.conversationId);
    expect(store.allRows("SELECT * FROM surface_conversations")).toHaveLength(1);
  });

  it("isolates surfaces per owner", () => {
    const ownerA = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 1,
    );
    const ownerB = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-b",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 1,
    );

    expect(ownerA.agentSessionId).not.toBe(ownerB.agentSessionId);
  });

  it("links orphan sessions by external ref instead of violating uniqueness", () => {
    const orphan = store.insertSession({
      ownerId: "owner-a",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "acp",
    });

    const resolved = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 5,
    );

    expect(resolved.agentSessionId).toBe(orphan.sessionId);
    expect(store.allRows("SELECT * FROM sessions")).toHaveLength(1);
    expect(store.allRows("SELECT * FROM surface_conversations")).toHaveLength(1);
  });

  it("importLegacyMainChatSessions links surface when session already exists by external ref", () => {
    const existing = store.insertSession({
      ownerId: "owner-a",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      defaultAdapterId: "acp",
    });

    const imported = importLegacyMainChatSessions(
      store,
      {
        ownerId: "owner-a",
        entries: [{ chatId: "default", agentSessionId: "ses_legacy_other" }],
      },
      () => 1,
    );
    expect(imported).toBe(1);

    const row = store.getRow(
      `SELECT conversation_id, agent_session_id FROM surface_conversations
       WHERE owner_id = ? AND external_ref_id = ?`,
      ["owner-a", "default"],
    );
    expect(String(row.agent_session_id)).toBe(existing.sessionId);
    expect(store.allRows("SELECT * FROM sessions")).toHaveLength(1);
  });

  it("imports legacy main-chat UserDefaults sessions once", () => {
    const imported = importLegacyMainChatSessions(
      store,
      {
        ownerId: "owner-a",
        entries: [{ chatId: "default", agentSessionId: "ses_legacy_1" }],
      },
      () => 1,
    );
    expect(imported).toBe(1);

    const resolved = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 2,
    );
    expect(resolved.agentSessionId).toBe("ses_legacy_1");
  });

  it("imports legacy sessions with distinct conversationId from agentSessionId", () => {
    importLegacyMainChatSessions(
      store,
      {
        ownerId: "owner-a",
        entries: [{ chatId: "default", agentSessionId: "ses_legacy_1" }],
      },
      () => 1,
    );
    const row = store.getRow(
      `SELECT conversation_id, agent_session_id FROM surface_conversations
       WHERE owner_id = ? AND external_ref_id = ?`,
      ["owner-a", "default"],
    );
    expect(String(row.agent_session_id)).toBe("ses_legacy_1");
    expect(String(row.conversation_id)).not.toBe("ses_legacy_1");
    expect(String(row.conversation_id)).toMatch(/^conv_/);
  });

  it("owner B does not reuse owner A conversation for the same surface", () => {
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    };
    const ownerA = resolveSurfaceSession(store, { ownerId: "owner-a", surfaceRef }, () => 1);
    const ownerB = resolveSurfaceSession(store, { ownerId: "owner-b", surfaceRef }, () => 2);
    expect(ownerA.conversationId).not.toBe(ownerB.conversationId);
    expect(ownerA.agentSessionId).not.toBe(ownerB.agentSessionId);
  });

  it("clearOwnerState invalidates active bindings without deleting surface rows", () => {
    const registry = new AdapterRegistry();
    const kernel = new AgentRuntimeKernel({ store, registry });
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner-a",
      surfaceRef: {
        surfaceKind: "service",
        externalRefKind: "service",
        externalRefId: "gmail_reader",
      },
      defaultAdapterId: "acp",
    });
    store.insertAdapterBinding({
      sessionId: resolved.agentSessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      resumeFidelity: "native",
      status: "active",
    });

    const cleared = kernel.clearOwnerState("owner-a");
    expect(cleared.invalidatedBindingIds).toHaveLength(1);
    expect(store.getRow("SELECT status FROM adapter_bindings").status).toBe("invalid");
    expect(store.allRows("SELECT * FROM surface_conversations")).toHaveLength(1);
  });

  it("mergeFloatingChatIntoMainChat copies turns into main_chat and removes floating mapping", () => {
    const floating = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "floating_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 1,
    );
    store.insertConversationTurn({
      conversationId: floating.conversationId,
      role: "user",
      surfaceKind: "floating_chat",
      content: "typed in floating bar",
      createdAtMs: 10,
      metadataJson: "{}",
    });
    store.insertConversationTurn({
      conversationId: floating.conversationId,
      role: "assistant",
      surfaceKind: "floating_chat",
      content: "floating reply",
      createdAtMs: 11,
      metadataJson: "{}",
    });

    const result = mergeFloatingChatIntoMainChat(store, { ownerId: "owner-a", chatId: "default" }, () => 20);
    expect(result.mergedTurns).toBe(2);
    expect(result.removedFloatingMapping).toBe(true);

    const main = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
      },
      () => 21,
    );
    const mainTurns = store.allRows(
      "SELECT role, content FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at_ms ASC",
      [main.conversationId],
    );
    expect(mainTurns).toEqual([
      { role: "user", content: "typed in floating bar" },
      { role: "assistant", content: "floating reply" },
    ]);
    expect(
      store.getOptionalRow(
        `SELECT conversation_id FROM surface_conversations
         WHERE owner_id = ? AND surface_kind = ?`,
        ["owner-a", "floating_chat"],
      ),
    ).toBeUndefined();
  });
});
