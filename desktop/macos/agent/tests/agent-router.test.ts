import { describe, expect, it } from "vitest";
import {
  parseExplicitMention,
  resolveAgent,
  type AvailabilityMap,
} from "../src/runtime/agent-router.js";

describe("agent router — explicit mention parsing", () => {
  it("extracts named agents from free task text", () => {
    expect(parseExplicitMention("use openclaw to refactor this")).toBe("openclaw");
    expect(parseExplicitMention("ask Hermes to research X")).toBe("hermes");
    expect(parseExplicitMention("have codex write a test")).toBe("codex");
    expect(parseExplicitMention("claude code, fix the bug")).toBe("acp");
    expect(parseExplicitMention("just do the thing")).toBeUndefined();
  });
});

describe("agent router — the four demo cases", () => {
  const allConnected: AvailabilityMap = { openclaw: true, hermes: true, codex: true, "pi-mono": true };

  // Case a: explicit mention, agent connected -> routes to it.
  it("a) explicit mention + connected routes to that agent", () => {
    const plan = resolveAgent({ task: "use openclaw to build the feature", availability: allConnected });
    expect(plan.reason).toBe("explicit_mention");
    expect(plan.order[0]).toBe("openclaw");
    expect(plan.needsSetup).toBeUndefined();
  });

  // Case b: explicit mention, agent NOT connected -> needsSetup, no silent fallback.
  it("b) explicit mention + not connected signals setup, does NOT fall back silently", () => {
    const plan = resolveAgent({ task: "use openclaw to build the feature", availability: { openclaw: false } });
    expect(plan.reason).toBe("explicit_unavailable");
    expect(plan.needsSetup).toBe("openclaw");
    expect(plan.order).toHaveLength(0); // nothing runs until the user connects it
  });

  // Case c: no mention, multiple agents connected -> best-for-task, with fallbacks.
  it("c) no mention picks best agent for the task type and includes fallbacks", () => {
    const plan = resolveAgent({
      task: "research the best approach for this",
      taskType: "research",
      availability: allConnected,
    });
    expect(plan.reason).toBe("capability_match");
    expect(plan.order[0]).toBe("hermes"); // top of the research capability list
    expect(plan.order.length).toBeGreaterThan(1); // fallbacks appended
    expect(plan.order).toContain("acp"); // Claude Code always available as a fallback
  });

  // Case d: primary would fail -> the plan provides the next agent to try.
  it("d) plan exposes an ordered fallback chain for the executor to advance through", () => {
    const plan = resolveAgent({ task: "edit this code", taskType: "code_edit", availability: allConnected });
    expect(plan.order.length).toBeGreaterThanOrEqual(2);
    // Simulate the executor: primary fails, next candidate exists and differs.
    const [primary, next] = plan.order;
    expect(next).toBeDefined();
    expect(next).not.toBe(primary);
  });
});

describe("agent router — default behaviour", () => {
  it("falls back to Claude Code when nothing else is connected", () => {
    const plan = resolveAgent({ task: "do something generic", availability: {} });
    expect(plan.reason).toBe("default");
    expect(plan.order).toEqual(["acp"]);
  });

  it("never routes to an unavailable agent via capability match", () => {
    // research prefers hermes, but it's offline -> must not appear in the plan.
    const plan = resolveAgent({ task: "research this", taskType: "research", availability: { hermes: false } });
    expect(plan.order).not.toContain("hermes");
    expect(plan.order[0]).toBe("acp");
  });
});
