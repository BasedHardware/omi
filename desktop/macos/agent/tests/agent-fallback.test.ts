import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  AGENT_FALLBACK_CHAIN_KEY,
  AGENT_FALLBACK_FROM_KEY,
  createAgentFallbackSupervisor,
  type AgentFallbackPlan,
  type AgentFallbackSpawnInput,
} from "../src/runtime/agent-fallback.js";
import {
  handleAgentControlToolCall,
  type AgentControlToolContext,
} from "../src/runtime/control-tools.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import type { AgentEvent } from "../src/runtime/types.js";
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

function runFailedEvent(runId: string, type = "run.failed"): AgentEvent {
  return {
    eventId: `event-${runId}`,
    sessionId: "session-1",
    runId,
    attemptId: "attempt-1",
    type,
    retentionClass: "standard" as AgentEvent["retentionClass"],
    visibility: "internal" as AgentEvent["visibility"],
    payloadJson: "{}",
    createdAtMs: 0,
  };
}

function planFor(overrides: Partial<AgentFallbackPlan> = {}): AgentFallbackPlan {
  return {
    ownerId: "owner",
    sessionId: "session-1",
    failedRunId: "run-1",
    clientId: "client-1",
    requestId: "req-1",
    prompt: "fix the failing test",
    failedAdapterId: "acp",
    nextAdapterId: "hermes",
    remainingChain: ["codex"],
    metadata: { [AGENT_FALLBACK_CHAIN_KEY]: ["codex"] },
    ...overrides,
  };
}

interface Recorder {
  spawns: AgentFallbackSpawnInput[];
  logs: string[];
}

function supervisorWith(
  plan: AgentFallbackPlan | null,
  options: { rejectSpawn?: boolean } = {},
): { handle: (event: AgentEvent) => void; recorder: Recorder } {
  const recorder: Recorder = { spawns: [], logs: [] };
  const handle = createAgentFallbackSupervisor({
    planForRun: () => plan,
    spawn: async (input) => {
      recorder.spawns.push(input);
      if (options.rejectSpawn) throw new Error("spawn refused");
      return {};
    },
    log: (message) => recorder.logs.push(message),
  });
  return { handle, recorder };
}

describe("agent fallback supervisor", () => {
  it("retries the failed task on the next agent in the chain", () => {
    const { handle, recorder } = supervisorWith(planFor());

    handle(runFailedEvent("run-1"));

    expect(recorder.spawns).toHaveLength(1);
    expect(recorder.spawns[0]).toMatchObject({
      adapterId: "hermes",
      defaultAdapterId: "hermes",
      prompt: "fix the failing test",
      ownerId: "owner",
      trustedUserSpawn: true,
    });
    // The retry carries the shortened chain, so the sequence terminates.
    expect(recorder.spawns[0].metadata[AGENT_FALLBACK_CHAIN_KEY]).toEqual(["codex"]);
  });

  it("names the agent that failed, so the log is not just a mystery retry", () => {
    const { handle, recorder } = supervisorWith(planFor());

    handle(runFailedEvent("run-1"));

    expect(recorder.logs.join(" ")).toContain("from=acp");
    expect(recorder.logs.join(" ")).toContain("next=hermes");
  });

  it("gives each hop its own request id so no retry replays an earlier one", () => {
    const { handle, recorder } = supervisorWith(planFor());
    handle(runFailedEvent("run-1"));
    expect(recorder.spawns[0].requestId).toBe("req-1-fallback-1");

    const second = supervisorWith(planFor({ requestId: "req-1-fallback-1" }));
    second.handle(runFailedEvent("run-2"));
    expect(second.recorder.spawns[0].requestId).toBe("req-1-fallback-2");
  });

  it("ignores everything that is not a terminal run failure", () => {
    const { handle, recorder } = supervisorWith(planFor());

    handle(runFailedEvent("run-1", "run.running"));
    handle(runFailedEvent("run-1", "run.queued"));
    handle(runFailedEvent("run-1", "attempt.failed"));

    expect(recorder.spawns).toHaveLength(0);
  });

  it("does nothing when the run has no agents left to try", () => {
    const { handle, recorder } = supervisorWith(null);

    handle(runFailedEvent("run-1"));

    expect(recorder.spawns).toHaveLength(0);
  });

  it("retries a given run only once, even on a duplicate event", () => {
    const { handle, recorder } = supervisorWith(planFor());

    handle(runFailedEvent("run-1"));
    handle(runFailedEvent("run-1"));

    expect(recorder.spawns).toHaveLength(1);
  });

  it("stops after the per-request ceiling, whatever the metadata claims", () => {
    // A hand-written chain cannot turn fallback into an unbounded loop.
    const { handle, recorder } = supervisorWith(
      planFor({ requestId: "req-1-fallback-9" }),
    );

    handle(runFailedEvent("run-1"));

    expect(recorder.spawns).toHaveLength(0);
    expect(recorder.logs.join(" ")).toContain("agent_fallback_exhausted");
  });

  it("logs and swallows a failed retry rather than throwing at the emitter", async () => {
    // Subscribers run inside the kernel's emit path; a broken fallback must not
    // take down the run that reported the failure.
    const { handle, recorder } = supervisorWith(planFor(), { rejectSpawn: true });

    expect(() => handle(runFailedEvent("run-1"))).not.toThrow();
    await Promise.resolve();
    await Promise.resolve();

    expect(recorder.logs.join(" ")).toContain("agent_fallback_failed");
  });
});

/** A kernel with the given production adapters registered as controllable fakes. */
function kernelWith(...adapterIds: string[]): AgentRuntimeKernel {
  const dir = mkdtempSync(join(tmpdir(), "omi-fallback-"));
  tempDirs.push(dir);
  const store = new SqliteAgentStore({
    databasePath: join(dir, "agent.db"),
    reconcileOnOpen: false,
  });
  openStores.push(store);
  const registry = new AdapterRegistry();
  for (const adapterId of adapterIds) {
    registry.register(adapterId, () => new FakeRuntimeAdapter(adapterId), 1);
  }
  return new AgentRuntimeKernel({
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
}

const ownerContext = (kernel: AgentRuntimeKernel): AgentControlToolContext => ({
  kernel,
  getOwnerId: () => "owner",
});

async function spawn(
  kernel: AgentRuntimeKernel,
  prompt: string,
  requestId: string,
  extra: Record<string, unknown> = {},
): Promise<Record<string, any>> {
  return JSON.parse(
    await handleAgentControlToolCall(ownerContext(kernel), "spawn_background_agent", {
      prompt,
      title: "Fallback chain",
      externalRefKind: "pill",
      externalRefId: "pill-1",
      originSurfaceKind: "floating_bar",
      requestId,
      clientId: "test-client",
      ownerId: "owner",
      ...extra,
    }),
  );
}

describe("the fallback chain survives on the run", () => {
  it("records the untried agents so a later failure can use them", async () => {
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "chain-1");

    const plan = kernel.agentFallbackPlanForRun(spawned.run.runId);

    expect(plan).not.toBeNull();
    // acp led the chain and took the task, so hermes is what remains.
    expect(plan!.nextAdapterId).toBe("hermes");
    expect(plan!.prompt).toBe("fix the failing test");
    expect(plan!.ownerId).toBe("owner");
  });

  it("shortens the chain on each hop until nothing is left", async () => {
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "chain-2");

    const first = kernel.agentFallbackPlanForRun(spawned.run.runId)!;
    expect(first.nextAdapterId).toBe("hermes");
    expect(first.remainingChain).toEqual([]);
  });

  it("records no chain when the caller named the agent itself", async () => {
    // An explicit adapterId is a decision; it must never be substituted away.
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "chain-3", {
      adapterId: "hermes",
    });

    expect(kernel.agentFallbackPlanForRun(spawned.run.runId)).toBeNull();
  });

  it("records no chain when only one agent can do the job", async () => {
    // openclaw declares supportsTools: false, so it is never a fallback.
    const kernel = kernelWith("acp", "openclaw");
    const spawned = await spawn(kernel, "fix the failing test", "chain-4");

    expect(kernel.agentFallbackPlanForRun(spawned.run.runId)).toBeNull();
  });

  it("records which agent failed, so the retry run can say what it replaced", async () => {
    // This is what makes a fallback visible instead of silent: the new run
    // itself carries the trail of agents that already failed the task.
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "trail-1");

    const plan = kernel.agentFallbackPlanForRun(spawned.run.runId)!;

    expect(plan.failedAdapterId).toBe("acp");
    expect(plan.metadata[AGENT_FALLBACK_FROM_KEY]).toEqual(["acp"]);
  });

  it("ignores a hand-written chain naming something that is not an adapter", async () => {
    // Run metadata is caller-supplied. An explicit adapterId means the control
    // tool stamps no chain of its own, so this metadata reaches the kernel
    // unchanged — and must still not be able to steer the retry.
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "hostile-1", {
      adapterId: "hermes",
      metadata: { [AGENT_FALLBACK_CHAIN_KEY]: ["definitely-not-an-adapter"] },
    });

    expect(kernel.agentFallbackPlanForRun(spawned.run.runId)).toBeNull();
  });

  it("ignores a chain naming an adapter this runtime has not registered", async () => {
    // codex is a real production adapter, but it is not connected here; a retry
    // must not be pointed at a provider the runtime cannot actually run.
    const kernel = kernelWith("acp", "hermes");
    const spawned = await spawn(kernel, "fix the failing test", "hostile-2", {
      adapterId: "hermes",
      metadata: { [AGENT_FALLBACK_CHAIN_KEY]: ["codex"] },
    });

    expect(kernel.agentFallbackPlanForRun(spawned.run.runId)).toBeNull();
  });

  it("returns no plan for a run that does not exist", () => {
    const kernel = kernelWith("acp");
    expect(kernel.agentFallbackPlanForRun("run-does-not-exist")).toBeNull();
  });
});
