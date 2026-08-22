import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  handleAgentControlToolCall,
  type AgentControlToolContext,
} from "../src/runtime/control-tools.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { FakeRuntimeAdapter } from "./kernel-fakes.js";

const tempDirs: string[] = [];
const openStores: SqliteAgentStore[] = [];

afterEach(() => {
  while (openStores.length) openStores.pop()!.close();
  while (tempDirs.length) {
    try {
      rmSync(tempDirs.pop()!, { recursive: true, force: true });
    } catch {
      // Windows may still hold the SQLite handle; temp cleanup is the OS's job.
    }
  }
});

interface Harness {
  kernel: AgentRuntimeKernel;
  adapters: Map<string, FakeRuntimeAdapter>;
}

/** A kernel with several production adapters registered, each a controllable fake. */
function harnessWith(...adapterIds: string[]): Harness {
  const dir = mkdtempSync(join(tmpdir(), "omi-continuation-"));
  tempDirs.push(dir);
  const store = new SqliteAgentStore({
    databasePath: join(dir, "agent.db"),
    reconcileOnOpen: false,
  });
  openStores.push(store);

  const registry = new AdapterRegistry();
  const adapters = new Map<string, FakeRuntimeAdapter>();
  for (const adapterId of adapterIds) {
    const adapter = new FakeRuntimeAdapter(adapterId);
    adapters.set(adapterId, adapter);
    registry.register(adapterId, () => adapter, 1);
  }

  const kernel = new AgentRuntimeKernel({
    store,
    registry,
    toolCapabilityProfileForSession: (sessionId) => {
      const profile = readSessionExecutionProfile(store, sessionId);
      return {
        ...profile,
        adapterId: adapterIds.includes(profile.adapterId) ? profile.adapterId : adapterIds[0],
      };
    },
  });
  return { kernel, adapters };
}

const ownerContext = (kernel: AgentRuntimeKernel): AgentControlToolContext => ({
  kernel,
  getOwnerId: () => "owner",
});

const parse = (result: string): Record<string, any> => JSON.parse(result);

async function spawn(
  kernel: AgentRuntimeKernel,
  prompt: string,
  requestId: string,
): Promise<Record<string, any>> {
  return parse(
    await handleAgentControlToolCall(ownerContext(kernel), "spawn_background_agent", {
      prompt,
      title: "Continuation test",
      externalRefKind: "pill",
      externalRefId: "pill-1",
      originSurfaceKind: "floating_bar",
      requestId,
      clientId: "test-client",
      ownerId: "owner",
    }),
  );
}

async function follow(
  kernel: AgentRuntimeKernel,
  sessionId: string,
  prompt: string,
): Promise<Record<string, any>> {
  return parse(
    await handleAgentControlToolCall(ownerContext(kernel), "send_agent_message", {
      sessionId,
      prompt,
      originSurfaceKind: "floating_bar",
      clientId: "test-client",
      ownerId: "owner",
    }),
  );
}

describe("install guidance on the continuation path", () => {
  it("answers a follow-up naming an uninstalled agent with install help", async () => {
    // Without this, "now try it with codex" continued silently on the session's
    // own agent and the user never learned why nothing changed.
    const { kernel } = harnessWith("acp", "hermes");
    const spawned = await spawn(kernel, "start the task", "continue-1");

    const replied = await follow(kernel, spawned.session.sessionId, "now try it with codex");

    expect(replied.agentUnavailable).toBeDefined();
    expect(replied.agentUnavailable.adapterId).toBe("codex");
    expect(replied.agentUnavailable.commands).toEqual(["npm install -g @openai/codex"]);
    expect(replied.agentUnavailable.message).toContain("npm install -g @openai/codex");
  });

  it("leaves an ordinary follow-up alone", async () => {
    const { kernel } = harnessWith("acp", "hermes");
    const spawned = await spawn(kernel, "start the task", "continue-2");

    const replied = await follow(kernel, spawned.session.sessionId, "keep going");

    expect(replied.agentUnavailable).toBeUndefined();
  });

  it("does not reroute a session to a different connected agent", async () => {
    // A session's adapter is fixed for its lifetime — every continuation is
    // resolved within that session's own provider boundary. Naming a *connected*
    // agent in a follow-up must therefore report nothing and change nothing;
    // switching agents is a new spawn, not a message.
    const { kernel } = harnessWith("acp", "hermes");
    const spawned = await spawn(kernel, "start the task", "continue-3");

    const replied = await follow(kernel, spawned.session.sessionId, "now use hermes instead");

    expect(replied.agentUnavailable).toBeUndefined();
  });
});

describe("spawn acceptance is not adapter execution", () => {
  it("returns a receipt before the adapter can fail", async () => {
    // Pins the constraint that decides where cross-agent fallback can live:
    // spawnBackgroundAgent creates the durable run and returns, then runs the
    // adapter asynchronously (`void execution` in kernel-runs.ts). An adapter
    // that cannot open a binding therefore fails AFTER the tool has answered,
    // so a spawn-time retry loop can never observe it. Falling back to another
    // agent has to react to the terminal run event instead.
    const { kernel, adapters } = harnessWith("acp", "hermes");
    adapters.get("acp")!.failNextOpenError = new Error("acp adapter unavailable");

    const spawned = await spawn(kernel, "fix the failing test", "receipt-1");

    expect(spawned.ok).toBe(true);
    expect(spawned.run).toBeDefined();
    expect(spawned.session).toBeDefined();
  });
});
