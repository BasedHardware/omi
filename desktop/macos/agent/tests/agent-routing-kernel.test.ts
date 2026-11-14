import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ProductionAdapterId } from "../src/adapters/interface.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { FakeRuntimeAdapter } from "./kernel-fakes.js";

const tempDirs: string[] = [];
const openStores: SqliteAgentStore[] = [];

afterEach(() => {
  // Close before deleting: Windows refuses to remove a directory while the
  // SQLite file inside it is still open.
  while (openStores.length) openStores.pop()!.close();
  while (tempDirs.length) {
    const dir = tempDirs.pop()!;
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      // A leftover temp dir is the OS's problem, not a test failure.
    }
  }
});

/**
 * A kernel with a real AdapterRegistry holding the given adapter ids. Selection
 * reads capabilities from the declared matrix, not from the adapter instance,
 * so a fake registered as "openclaw" still carries OpenClaw's real limits.
 */
function kernelWith(...adapterIds: string[]): AgentRuntimeKernel {
  const dir = mkdtempSync(join(tmpdir(), "omi-routing-"));
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
  return new AgentRuntimeKernel({ store, registry });
}

const CODING_TASK = { needsTools: true } as const;

describe("kernel resolves an utterance against its registered adapters", () => {
  it("routes to the agent the user named", () => {
    const kernel = kernelWith("acp", "hermes");
    const route = kernel.resolveAgentRoute("use hermes to run the suite", CODING_TASK);

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.adapterId).toBe("hermes");
    expect(route.explicit).toBe(true);
    expect(route.explicitProvider).toBe("hermes");
  });

  it("answers with install guidance for an agent this runtime has not registered", () => {
    const kernel = kernelWith("acp", "hermes");
    const route = kernel.resolveAgentRoute("ask codex to review the diff", CODING_TASK);

    expect(route.kind).toBe("install_required");
    if (route.kind !== "install_required") return;
    expect(route.adapterId).toBe("codex");
    expect(route.guidance.commands).toEqual(["npm install -g @openai/codex"]);
  });

  it("picks the best registered agent and keeps the rest as fallback", () => {
    const kernel = kernelWith("acp", "hermes", "openclaw");
    const route = kernel.resolveAgentRoute("fix the failing test", CODING_TASK);

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.adapterId).toBe("acp");
    expect(route.chain).toContain("hermes");
    // OpenClaw declares supportsTools: false, so it is not a fallback here.
    expect(route.chain).not.toContain("openclaw");
  });

  it("runs the task on codex once codex is registered", () => {
    // The other half of the codex story: install guidance is the answer only
    // while it is absent. Registered, it is a first-class target like any other.
    const kernel = kernelWith("acp", "codex");
    const route = kernel.resolveAgentRoute("use codex to review this diff", CODING_TASK);

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.adapterId).toBe("codex");
    expect(route.explicit).toBe(true);
    expect(route.explicitProvider).toBe("codex");
    // And it still has somewhere to fall back to.
    expect(route.chain).toContain("acp");
  });

  it("treats codex as a tool-capable fallback for an unnamed task", () => {
    const kernel = kernelWith("codex", "openclaw");
    const route = kernel.resolveAgentRoute("edit these files", CODING_TASK);

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    // Codex declares toolSupport required; OpenClaw does not.
    expect(route.adapterId).toBe("codex");
    expect(route.chain).not.toContain("openclaw");
  });

  it("ignores adapters that are registered but not production adapters", () => {
    const kernel = kernelWith("fake");
    const route = kernel.resolveAgentRoute("fix the failing test", CODING_TASK);

    expect(route.kind).toBe("no_agent_available");
  });

  it("sees only what is registered, so selection tracks the live runtime", () => {
    expect(kernelWith("acp").resolveAgentRoute("use hermes for this", CODING_TASK).kind).toBe(
      "install_required",
    );
    expect(
      kernelWith("acp", "hermes").resolveAgentRoute("use hermes for this", CODING_TASK).kind,
    ).toBe("route");
  });
});
