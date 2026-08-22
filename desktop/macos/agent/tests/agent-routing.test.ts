import { describe, expect, it } from "vitest";
import {
  adapterCapabilitiesFor,
  type ProductionAdapterId,
} from "../src/adapters/interface.js";
import { routeAgentRequest } from "../src/runtime/agent-routing.js";
import type { AdapterCandidate } from "../src/runtime/adapter-scoring.js";

function connected(...adapterIds: ProductionAdapterId[]): AdapterCandidate[] {
  return adapterIds.map((adapterId) => ({
    adapterId,
    capabilities: adapterCapabilitiesFor(adapterId),
  }));
}

/** Most delegated work is coding work, which calls tools. */
const CODING_TASK = { needsTools: true } as const;

describe("agent routing", () => {
  // Nik's test 1: name an agent, that agent runs it.
  it("runs the task on the agent the user named", () => {
    const route = routeAgentRequest({
      utterance: "use hermes to run the test suite",
      connected: connected("acp", "hermes", "openclaw"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.adapterId).toBe("hermes");
    expect(route.explicit).toBe(true);
    // This is the field DesktopIntentRouter reads; nothing populated it before.
    expect(route.explicitProvider).toBe("hermes");
  });

  // Nik's test 2: several connected, pick the best, keep the rest as fallback.
  it("picks the best agent and keeps the others as fallback", () => {
    const route = routeAgentRequest({
      utterance: "fix the failing test",
      connected: connected("acp", "hermes", "openclaw"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.explicit).toBe(false);
    expect(route.adapterId).toBe(route.chain[0]);
    expect(route.chain.length).toBeGreaterThan(1);
    // OpenClaw cannot use tools, so it is not a fallback for a coding task.
    expect(route.chain).not.toContain("openclaw");
  });

  it("keeps a named agent at the head of its own fallback chain", () => {
    const route = routeAgentRequest({
      utterance: "hermes, refactor this module",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.chain[0]).toBe("hermes");
    expect(route.chain).toContain("acp");
  });

  // Nik's test 3: name an agent that isn't connected, get help installing it.
  it("offers install guidance for an agent that is not connected", () => {
    const route = routeAgentRequest({
      utterance: "get codex to review this diff",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("install_required");
    if (route.kind !== "install_required") return;
    expect(route.adapterId).toBe("codex");
    expect(route.guidance.commands).toEqual(["npm install -g @openai/codex"]);
    expect(route.guidance.message).toContain("npm install -g @openai/codex");
    expect(route.guidance.docsUrl).toBe("https://github.com/agentclientprotocol/codex-acp");
  });

  it("does not silently substitute another agent for an uninstalled one", () => {
    // The old behaviour: "use codex" ran on Claude Code and nobody was told.
    const route = routeAgentRequest({
      utterance: "use codex for this",
      connected: connected("acp"),
      requirements: CODING_TASK,
    });

    expect(route.kind).not.toBe("route");
  });

  it("leaves routing untouched when no agent is named", () => {
    const route = routeAgentRequest({
      utterance: "summarize what changed today",
      connected: connected("acp", "hermes"),
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    // Null keeps the kernel's existing provider checks on their current path.
    expect(route.explicitProvider).toBeNull();
    expect(route.adapterId).toBe("acp");
  });

  it("says so when the named agent is connected but cannot do the job", () => {
    const route = routeAgentRequest({
      utterance: "use openclaw to edit these files",
      connected: connected("acp", "openclaw"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.requestedButIneligible).toMatchObject({ adapterId: "openclaw" });
    expect(route.requestedButIneligible?.missing).toContain("tool support");
    expect(route.adapterId).toBe("acp");
    // It failed the requirement, so it must not go to the kernel as requested.
    expect(route.explicitProvider).toBeNull();
  });

  it("reports when nothing connected can run the task", () => {
    const route = routeAgentRequest({
      utterance: "edit these files",
      connected: connected("openclaw"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("no_agent_available");
    if (route.kind !== "no_agent_available") return;
    expect(route.reasons.join(" ")).toContain("openclaw");
  });

  it("reports when no agents are connected at all", () => {
    const route = routeAgentRequest({ utterance: "do the thing", connected: [] });

    expect(route.kind).toBe("no_agent_available");
    if (route.kind !== "no_agent_available") return;
    expect(route.reasons).toEqual(["no agents are connected"]);
  });

  it("honours a ruled-out agent instead of routing to it", () => {
    const route = routeAgentRequest({
      utterance: "fix this, but don't use hermes",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.explicit).toBe(false);
    expect(route.adapterId).toBe("acp");
  });

  it("keeps a ruled-out agent out of the fallback chain as well", () => {
    // Selecting elsewhere is not enough: falling back to Hermes after acp fails
    // would run the exact agent the user excluded.
    const route = routeAgentRequest({
      utterance: "fix this, but don't use hermes",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.chain).not.toContain("hermes");
    expect(route.chain).toEqual(["acp"]);
  });

  it("reports when every connected agent was ruled out", () => {
    const route = routeAgentRequest({
      utterance: "fix this without hermes and not claude code",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("no_agent_available");
    if (route.kind !== "no_agent_available") return;
    expect(route.reasons.join(" ")).toContain("ruled out");
  });

  it("lets a later request override an earlier exclusion", () => {
    const route = routeAgentRequest({
      utterance: "don't use hermes, actually use hermes",
      connected: connected("acp", "hermes"),
      requirements: CODING_TASK,
    });

    expect(route.kind).toBe("route");
    if (route.kind !== "route") return;
    expect(route.adapterId).toBe("hermes");
  });
});
