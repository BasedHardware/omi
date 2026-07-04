import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { importLegacyMainChatSessions, resolveSurfaceSession } from "../src/runtime/surface-session.js";

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
