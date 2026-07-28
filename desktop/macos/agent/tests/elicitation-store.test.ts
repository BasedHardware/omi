import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-elicitation-store-"));
  createdDirs.push(dir);
  return join(dir, "omi-agentd.sqlite3");
}

/** A session with an ACP binding, which is what an adapter request maps onto. */
function seedBoundSession(store: SqliteAgentStore, options: {
  sessionId: string;
  ownerId: string;
  adapterId: string;
  adapterNativeSessionId: string;
  bindingStatus?: "active" | "stale" | "closed";
}) {
  store.insertSession({
    sessionId: options.sessionId,
    ownerId: options.ownerId,
    status: "open",
    surfaceKind: "main_chat",
    defaultAdapterId: options.adapterId,
  } as any);
  store.insertAdapterBinding({
    sessionId: options.sessionId,
    adapterId: options.adapterId,
    bindingGeneration: 1,
    adapterNativeSessionId: options.adapterNativeSessionId,
    resumeFidelity: "none",
    status: options.bindingStatus ?? "active",
  } as any);
}

describe("adapter-native session bridge", () => {
  it("resolves the owning Omi session and owner for an adapter session", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
    });

    expect(store.sessionForAdapterNativeSession("hermes", "native-1")).toMatchObject({
      sessionId: "sess-1",
      ownerId: "owner-1",
    });
    store.close();
  });

  it("does not cross adapters or invent a session for an unknown one", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
    });

    expect(store.sessionForAdapterNativeSession("openclaw", "native-1")).toBeNull();
    expect(store.sessionForAdapterNativeSession("hermes", "native-missing")).toBeNull();
    store.close();
  });

  it("ignores a closed binding, so a stale adapter session cannot reach a live one", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
      bindingStatus: "closed",
    });

    expect(store.sessionForAdapterNativeSession("hermes", "native-1")).toBeNull();
    store.close();
  });
});

describe("elicitation dispatches do not survive a daemon restart", () => {
  it("cancels a pending elicitation whose blocked request died with the process", () => {
    const databasePath = newDatabasePath();
    const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
    });
    const dispatch = store.insertDesktopDispatch({
      ownerId: "owner-1",
      kind: "approval",
      priority: 100,
      title: "Hermes needs permission",
      decisionPrompt: "Write a file",
      sourceSessionId: "sess-1",
      payloadJson: JSON.stringify({ channel: "acp_permission" }),
      // No expiry: the existing expiry sweep cannot reach this row.
      expiresAtMs: null,
    } as any);

    const reconciliation = store.reconcileStartup();

    expect(reconciliation.cancelledElicitationDispatchIds).toEqual([dispatch.dispatchId]);
    expect(
      store.getRow("SELECT status, resolved_by FROM desktop_dispatches WHERE dispatch_id = ?", [
        dispatch.dispatchId,
      ]),
    ).toMatchObject({ status: "cancelled", resolved_by: "daemon_startup_reconciliation" });
    store.close();
  });

  it("leaves durable review dispatches pending across the same restart", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
    });
    const review = store.insertDesktopDispatch({
      ownerId: "owner-1",
      kind: "memory_candidate",
      priority: 10,
      title: "Review memory candidate",
      decisionPrompt: "Keep this memory?",
      sourceSessionId: "sess-1",
      expiresAtMs: null,
    } as any);

    const reconciliation = store.reconcileStartup();

    expect(reconciliation.cancelledElicitationDispatchIds).toEqual([]);
    expect(
      store.getRow("SELECT status FROM desktop_dispatches WHERE dispatch_id = ?", [review.dispatchId]),
    ).toMatchObject({ status: "pending" });
    store.close();
  });

  it("does not reopen an elicitation the user already answered", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    store.migrate();
    seedBoundSession(store, {
      sessionId: "sess-1",
      ownerId: "owner-1",
      adapterId: "hermes",
      adapterNativeSessionId: "native-1",
    });
    const dispatch = store.insertDesktopDispatch({
      ownerId: "owner-1",
      kind: "approval",
      priority: 100,
      title: "Hermes needs permission",
      decisionPrompt: "Write a file",
      sourceSessionId: "sess-1",
      payloadJson: JSON.stringify({ channel: "acp_permission" }),
      expiresAtMs: null,
    } as any);
    store.resolveDesktopDispatch(dispatch.dispatchId, {
      ownerId: "owner-1",
      status: "resolved",
      resolvedBy: "user",
      resolutionJson: JSON.stringify({ optionId: "once" }),
    });

    const reconciliation = store.reconcileStartup();

    expect(reconciliation.cancelledElicitationDispatchIds).toEqual([]);
    expect(
      store.getRow("SELECT status, resolved_by FROM desktop_dispatches WHERE dispatch_id = ?", [
        dispatch.dispatchId,
      ]),
    ).toMatchObject({ status: "resolved", resolved_by: "user" });
    store.close();
  });
});
