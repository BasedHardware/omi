import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import {
  configureDefaultExecutionProfile,
  readSessionExecutionProfile,
} from "../src/runtime/session-execution-profile.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

const roots: string[] = [];
afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function harness() {
  const root = mkdtempSync(join(tmpdir(), "omi-profile-"));
  roots.push(root);
  const path = join(root, "agent.sqlite");
  const store = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() });
  return { root, path, store, kernel };
}

describe("SessionExecutionProfile", () => {
  it("versions default preferences as next-session-only configuration", () => {
    const { store } = harness();
    const existing = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
      defaultCwd: "/tmp/original",
      modelProfile: "claude-sonnet",
    });
    const first = configureDefaultExecutionProfile(store, {
      ownerId: "owner",
      adapterId: "pi-mono",
      modelProfile: "omi-sonnet",
      workingDirectory: "/tmp/next",
      expectedPreferenceGeneration: 0,
    }, 1);
    const duplicate = configureDefaultExecutionProfile(store, {
      ownerId: "owner",
      adapterId: "pi-mono",
      modelProfile: "omi-sonnet",
      workingDirectory: "/tmp/next",
      expectedPreferenceGeneration: 1,
    }, 2);
    expect(first).toMatchObject({ generation: 1, credentialScope: "managed_cloud" });
    expect(duplicate.generation).toBe(1);
    expect(readSessionExecutionProfile(store, existing.sessionId)).toMatchObject({
      adapterId: "acp",
      workingDirectory: "/tmp/original",
    });
    expect(() => configureDefaultExecutionProfile(store, {
      ownerId: "owner",
      adapterId: "acp",
      modelProfile: "claude-sonnet",
      workingDirectory: "/tmp/newer",
      expectedPreferenceGeneration: 0,
    }, 3)).toThrow(/generation is stale/);
    store.close();
  });

  it.each([
    ["acp", "local_user"],
    ["pi-mono", "managed_cloud"],
    ["hermes", "local_user"],
    ["openclaw", "local_user"],
  ] as const)("pins %s with its declared credential scope", (adapterId, credentialScope) => {
    const { store } = harness();
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: adapterId,
      providerBoundary: credentialScope === "managed_cloud" ? "managed_cloud" : `local_user:${adapterId}`,
      modelProfile: adapterId === "openclaw" ? null : "profile-model",
    });
    expect(readSessionExecutionProfile(store, session.sessionId)).toMatchObject({
      generation: 1,
      adapterId,
      credentialScope,
      modelProfile: adapterId === "openclaw" ? null : "profile-model",
      executionRole: "coordinator",
      source: "creation",
    });
    expect(() => store.execute(
      "UPDATE session_execution_profiles SET adapter_id = 'pi-mono' WHERE session_id = ?",
      [session.sessionId],
    )).toThrow(/immutable/);
    store.close();
  });

  it("migrates only an idle session, increments generation, stales bindings, and survives restart", () => {
    const { path, store, kernel } = harness();
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
      providerBoundary: "local_user:acp",
      modelProfile: "claude-sonnet",
    });
    store.insertAdapterBinding({
      sessionId: session.sessionId,
      adapterId: "acp",
      bindingGeneration: 1,
      profileGeneration: 1,
      resumeFidelity: "native",
      status: "active",
      adapterNativeSessionId: "native-profile",
    });
    const migrated = kernel.migrateSessionExecutionProfile({
      sessionId: session.sessionId,
      ownerId: "owner",
      expectedProfileGeneration: 1,
      adapterId: "pi-mono",
      modelProfile: "omi-sonnet",
      reason: "explicit_user_migration",
    });
    expect(migrated.profile).toMatchObject({
      generation: 2,
      adapterId: "pi-mono",
      credentialScope: "managed_cloud",
      modelProfile: "omi-sonnet",
    });
    expect(migrated.staleBindingIds).toHaveLength(1);
    store.close();

    const reopened = new SqliteAgentStore({ databasePath: path, reconcileOnOpen: false });
    expect(readSessionExecutionProfile(reopened, session.sessionId)).toMatchObject({
      generation: 2,
      adapterId: "pi-mono",
      modelProfile: "omi-sonnet",
    });
    reopened.close();
  });

  it("rejects profile migration with an active run and rejects follow-up overrides", async () => {
    const { store, kernel } = harness();
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
      providerBoundary: "local_user:acp",
      modelProfile: "claude-sonnet",
    });
    store.insertRun({
      sessionId: session.sessionId,
      clientId: "trace",
      requestId: "active",
      status: "running",
      mode: "act",
      profileGeneration: 1,
    });
    expect(() => kernel.migrateSessionExecutionProfile({
      sessionId: session.sessionId,
      ownerId: "owner",
      expectedProfileGeneration: 1,
      adapterId: "pi-mono",
      reason: "unsafe",
    })).toThrow(/while a run is active/);

    await expect(kernel.sendAgentMessage({
      sessionId: session.sessionId,
      ownerId: "owner",
      clientId: "trace",
      requestId: "override",
      prompt: "continue",
      adapterId: "pi-mono",
    })).rejects.toThrow(/rejects adapter override/);
    store.close();
  });

  it("fences stale idle-session migration inside the mutation transaction", () => {
    const { store, kernel } = harness();
    const session = store.insertSession({
      ownerId: "owner",
      surfaceKind: "main_chat",
      defaultAdapterId: "acp",
    });
    expect(() => kernel.migrateSessionExecutionProfile({
      sessionId: session.sessionId,
      ownerId: session.ownerId,
      expectedProfileGeneration: 2,
      adapterId: "pi-mono",
      reason: "stale_user_request",
    })).toThrow(/generation is stale/);
    expect(readSessionExecutionProfile(store, session.sessionId)).toMatchObject({
      generation: 1,
      adapterId: "acp",
    });
    store.close();
  });
});
