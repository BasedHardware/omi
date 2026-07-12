import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { importLegacyMainChatSessions, resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { listJournalTurns, recordJournalTurn } from "../src/runtime/conversation-journal.js";

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

  it("pins an explicit creation profile atomically and ignores later selections", () => {
    const surfaceRef = {
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "directed-provider",
    };
    const created = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef,
      defaultAdapterId: "acp",
      modelProfile: "created-model",
      defaultCwd: "/tmp/created",
    }, () => 1);
    const existing = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef,
      defaultAdapterId: "pi-mono",
      modelProfile: "must-not-apply",
      defaultCwd: "/tmp/must-not-apply",
    }, () => 2);

    expect(existing.agentSessionId).toBe(created.agentSessionId);
    expect(store.getRow(
      `SELECT adapter_id, model_profile, working_directory
       FROM session_execution_profiles WHERE session_id = ? AND generation = 1`,
      [created.agentSessionId],
    )).toEqual({
      adapter_id: "acp",
      model_profile: "created-model",
      working_directory: "/tmp/created",
    });
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

  it("shares one canonical session and conversation when realtime voice resolves before main chat", () => {
    const voice = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "acp",
    }, () => 1);
    const main = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
      defaultAdapterId: "pi-mono",
    }, () => 2);

    expect(main).toEqual(voice);
    expect(store.allRows(
      `SELECT surface_kind, conversation_id, agent_session_id
       FROM surface_conversations ORDER BY surface_kind ASC`,
    )).toEqual([
      { surface_kind: "main_chat", conversation_id: voice.conversationId, agent_session_id: voice.agentSessionId },
      { surface_kind: "realtime_voice", conversation_id: voice.conversationId, agent_session_id: voice.agentSessionId },
    ]);
  });

  it("shares main, floating, and realtime aliases while preserving task/workstream boundaries", () => {
    const main = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "default" },
    }, () => 1);
    const floating = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "floating_chat", externalRefKind: "chat", externalRefId: "default" },
    }, () => 2);
    const voice = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "default" },
    }, () => 3);
    const task = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "task_chat", externalRefKind: "task", externalRefId: "default" },
    }, () => 4);
    const workstream = resolveSurfaceSession(store, {
      ownerId: "owner-a",
      surfaceRef: { surfaceKind: "workstream", externalRefKind: "workstream", externalRefId: "default" },
    }, () => 5);

    expect(floating).toEqual(main);
    expect(voice).toEqual(main);
    expect(task.conversationId).not.toBe(main.conversationId);
    expect(workstream.conversationId).not.toBe(main.conversationId);
    expect(task.agentSessionId).not.toBe(main.agentSessionId);
    expect(workstream.agentSessionId).not.toBe(main.agentSessionId);

    recordJournalTurn(store, {
      ownerId: "owner-a",
      conversationId: voice.conversationId,
      turnId: "voice-visible-everywhere",
      role: "user",
      surfaceKind: "realtime_voice",
      origin: "realtime_voice",
      status: "completed",
      content: "Shared voice turn",
      contentBlocks: [{ type: "text", id: "voice:text", text: "Shared voice turn" }],
      delivery: "backend",
      createdAtMs: 10,
    });
    expect(listJournalTurns(store, {
      ownerId: "owner-a",
      conversationId: main.conversationId,
    }).turns).toEqual([expect.objectContaining({ turnId: "voice-visible-everywhere" })]);
    expect(listJournalTurns(store, {
      ownerId: "owner-a",
      conversationId: task.conversationId,
    }).turns).toEqual([]);
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

  it("does not rewrite an imported session profile during surface resolution", () => {
    importLegacyMainChatSessions(
      store,
      {
        ownerId: "owner-a",
        entries: [{ chatId: "default", agentSessionId: "ses_legacy_1" }],
      },
      () => 1,
    );

    const resolved = resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
        defaultAdapterId: "pi-mono",
      },
      () => 2,
    );

    expect(resolved.agentSessionId).toBe("ses_legacy_1");
    const session = store.getRow(
      "SELECT default_adapter_id, provider_boundary FROM sessions WHERE session_id = ?",
      [resolved.agentSessionId],
    );
    expect(String(session.default_adapter_id)).toBe("acp");
    expect(String(session.provider_boundary)).toBe("local_user:acp");
  });

  it("does not rewrite a main-chat provider boundary after execution starts", () => {
    const resolved = resolveSurfaceSession(
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
    store.insertRun({
      sessionId: resolved.agentSessionId,
      clientId: "client-a",
      requestId: "request-a",
      status: "queued",
      mode: "ask",
      inputJson: "{}",
    });

    resolveSurfaceSession(
      store,
      {
        ownerId: "owner-a",
        surfaceRef: {
          surfaceKind: "main_chat",
          externalRefKind: "chat",
          externalRefId: "default",
        },
        defaultAdapterId: "pi-mono",
      },
      () => 2,
    );

    const session = store.getRow(
      "SELECT default_adapter_id, provider_boundary FROM sessions WHERE session_id = ?",
      [resolved.agentSessionId],
    );
    expect(String(session.default_adapter_id)).toBe("acp");
    expect(String(session.provider_boundary)).toBe("local_user:acp");
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

});
