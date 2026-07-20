import { describe, expect, it, vi } from "vitest";
import {
  asRoutableAgentId,
  buildAvailabilitySnapshot,
  DispatchAttemptError,
  inferTaskType,
  isDispatchRetryable,
  planQueryDispatch,
} from "../src/runtime/dispatch-routing.js";
import { executeWithFallback } from "../src/runtime/agent-fallback.js";
import type { RoutableAgentId } from "../src/runtime/agent-router.js";

const allLocalConnected = buildAvailabilitySnapshot({ piMono: true, hermes: true, openclaw: true, codex: true });

describe("dispatch-routing — snapshot & guards", () => {
  it("marks acp always available and reflects local flags", () => {
    const snap = buildAvailabilitySnapshot({ piMono: false, hermes: true, openclaw: false, codex: false });
    expect(snap).toEqual({ acp: true, "pi-mono": false, hermes: true, openclaw: false, codex: false });
  });

  it("narrows adapterId strings safely", () => {
    expect(asRoutableAgentId("openclaw")).toBe("openclaw");
    expect(asRoutableAgentId("nonsense")).toBeUndefined();
    expect(asRoutableAgentId(undefined)).toBeUndefined();
  });

  it("treats activation failures as retryable but not the active-context guard", () => {
    expect(isDispatchRetryable(new Error("OpenClaw is not available."))).toBe(true);
    expect(isDispatchRetryable(new Error("Request context already active for clientId/requestId"))).toBe(false);
  });

  it("infers a coarse task type from the prompt", () => {
    expect(inferTaskType("refactor this function")).toBe("code_edit");
    expect(inferTaskType("research the tradeoffs")).toBe("research");
    expect(inferTaskType("deploy the app")).toBe("quick_command");
    expect(inferTaskType("build")).toBe("quick_command");
    expect(inferTaskType("deploy")).toBe("quick_command");
    expect(inferTaskType("hello there")).toBe("general");
  });
});

describe("dispatch-routing — planQueryDispatch", () => {
  it("honors a structured adapterId (Swift UI pick) as primary, with fallbacks", () => {
    const plan = planQueryDispatch({ adapterId: "openclaw", prompt: "anything" }, allLocalConnected);
    expect(plan.reason).toBe("explicit_mention");
    expect(plan.order[0]).toBe("openclaw");
    expect(plan.order.length).toBeGreaterThan(1);
  });

  it("routes by task text when no structured adapter is set", () => {
    const plan = planQueryDispatch({ prompt: "use hermes to research this" }, allLocalConnected);
    expect(plan.order[0]).toBe("hermes");
    expect(plan.reason).toBe("explicit_mention");
  });

  it("signals setup (no order) when the chosen agent is not connected", () => {
    const plan = planQueryDispatch({ adapterId: "codex", prompt: "x" }, { ...allLocalConnected, codex: false });
    expect(plan.reason).toBe("explicit_unavailable");
    expect(plan.needsSetup).toBe("codex");
    expect(plan.order).toHaveLength(0);
  });

  it("falls to Claude Code when nothing is mentioned or connected", () => {
    const plan = planQueryDispatch({ prompt: "just do it" }, buildAvailabilitySnapshot({ piMono: false, hermes: false, openclaw: false, codex: false }));
    expect(plan.reason).toBe("default");
    expect(plan.order).toEqual(["acp"]);
  });
});

// Mirrors the exact index.ts live-dispatch composition:
//   plan = planQueryDispatch(query, snapshot)
//   executeWithFallback(plan.order, runOne = activate + handleQuery)
describe("dispatch-routing — live dispatch composition", () => {
  async function simulateDispatch(
    query: { adapterId?: string; prompt: string },
    snapshot = allLocalConnected,
    opts: {
      failActivation?: Set<RoutableAgentId>;
      runFails?: Map<RoutableAgentId, { retryable: boolean }>;
    } = {}
  ) {
    const plan = planQueryDispatch(query, snapshot);
    if (plan.needsSetup) return { plan, guidedSetup: plan.needsSetup as RoutableAgentId };
    const handled: RoutableAgentId[] = [];
    const outcome = await executeWithFallback(plan.order as RoutableAgentId[], {
      runOne: async (agent) => {
        // Mirrors index.ts runOne: activate, then facade.handleQuery outcome.
        if (opts.failActivation?.has(agent)) throw new Error(`${agent} is not available.`);
        const runFail = opts.runFails?.get(agent);
        if (runFail) throw new DispatchAttemptError(`${agent} run failed`, runFail.retryable);
        handled.push(agent); // stands in for a successful facade.handleQuery
      },
      isRetryable: (error) =>
        error instanceof DispatchAttemptError ? error.retryable : isDispatchRetryable(error),
      log: () => {},
    });
    return { plan, outcome, handled };
  }

  it("a) explicit mention + connected -> runs that agent", async () => {
    const r = await simulateDispatch({ prompt: "use openclaw to build it" });
    expect(r.outcome?.ok).toBe(true);
    expect(r.handled).toEqual(["openclaw"]);
  });

  it("b) explicit mention + not connected -> guided setup, nothing runs", async () => {
    const snap = { ...allLocalConnected, openclaw: false };
    const r = await simulateDispatch({ prompt: "use openclaw to build it" }, snap);
    expect(r.guidedSetup).toBe("openclaw");
    expect(r.outcome).toBeUndefined();
  });

  it("c) no mention + several connected -> best-for-task runs", async () => {
    const r = await simulateDispatch({ prompt: "research the tradeoffs here" });
    expect(r.outcome?.ok).toBe(true);
    // research capability list is hermes-first
    expect(r.handled[0]).toBe("hermes");
  });

  it("d) primary can't activate -> fallback advances to the next agent", async () => {
    const r = await simulateDispatch(
      { adapterId: "openclaw", prompt: "edit this" },
      allLocalConnected,
      { failActivation: new Set<RoutableAgentId>(["openclaw"]) }
    );
    expect(r.outcome?.ok).toBe(true);
    expect(r.outcome?.agent).not.toBe("openclaw");
    // openclaw was attempted then a different agent handled it
    expect(r.handled.length).toBe(1);
    expect(r.handled[0]).not.toBe("openclaw");
  });

  it("e) primary RUN fails retryably -> fallback advances to the next agent", async () => {
    const r = await simulateDispatch(
      { adapterId: "openclaw", prompt: "edit this" },
      allLocalConnected,
      { runFails: new Map([["openclaw", { retryable: true }]]) }
    );
    expect(r.outcome?.ok).toBe(true);
    expect(r.outcome?.agent).not.toBe("openclaw");
    expect(r.handled[0]).not.toBe("openclaw");
  });

  it("f) primary RUN fails NON-retryably -> surfaced immediately, no fallback", async () => {
    const r = await simulateDispatch(
      { adapterId: "openclaw", prompt: "edit this" },
      allLocalConnected,
      { runFails: new Map([["openclaw", { retryable: false }]]) }
    );
    expect(r.outcome?.ok).toBe(false);
    expect(r.handled).toHaveLength(0); // nothing else was tried
    expect(r.outcome?.attempts).toHaveLength(1);
  });
});
