import { describe, expect, it } from "vitest";
import { resolveBestAgent, isAgentSignedIn } from "../src/runtime/agent-routing.js";

const ALL = ["acp", "codex", "hermes", "openclaw"];

describe("resolveBestAgent", () => {
  it("routes on real task constraints to the agent that satisfies them", () => {
    expect(resolveBestAgent({ connected: ALL, taskText: "use claude to review this" }))
      .toMatchObject({ adapterId: "acp", reason: "you asked for Claude" });
    expect(resolveBestAgent({ connected: ALL, taskText: "do this with my openai account" }))
      .toMatchObject({ adapterId: "codex", reason: "you asked for OpenAI" });
    expect(resolveBestAgent({ connected: ALL, taskText: "keep this offline and private" }))
      .toMatchObject({ adapterId: "hermes", reason: "you asked to keep it offline/low-cost" });
    expect(resolveBestAgent({ connected: ALL, taskText: "remember this for my ongoing project" }))
      .toMatchObject({ adapterId: "hermes", reason: "you want it remembered across sessions" });
    expect(resolveBestAgent({ connected: ALL, taskText: "when done, message me on slack" }))
      .toMatchObject({ adapterId: "openclaw", reason: "you asked to be notified on a chat channel" });
  });

  it("uses the user's usual agent when no signal is present, and never picks one by default", () => {
    expect(resolveBestAgent({ connected: ALL, taskText: "fix the failing test", preferred: "codex" }))
      .toMatchObject({ adapterId: "codex", reason: "your usual agent" });
    expect(resolveBestAgent({ connected: ALL, taskText: "fix the failing test", preferred: "hermes" }))
      .toMatchObject({ adapterId: "hermes", reason: "your usual agent" });
    // No signal and no connected preference -> null (caller uses the owner's
    // default). No agent is ever picked arbitrarily.
    expect(resolveBestAgent({ connected: ["hermes", "codex"], taskText: "refactor this file" })).toBeNull();
    expect(resolveBestAgent({ connected: ALL, taskText: "refactor this file", preferred: "pi-mono" })).toBeNull();
  });

  it("prefers the user's usual agent among several that satisfy a constraint", () => {
    // Both hermes and (hypothetically) another offline agent could match; preferred wins if it does.
    expect(resolveBestAgent({ connected: ALL, taskText: "keep it offline", preferred: "hermes" }))
      .toMatchObject({ adapterId: "hermes" });
  });

  it("falls back to preference when the constraint's agent is not connected", () => {
    // Task wants offline (hermes) but hermes is not connected -> usual agent.
    expect(resolveBestAgent({ connected: ["acp", "codex"], taskText: "keep it offline", preferred: "codex" }))
      .toMatchObject({ adapterId: "codex", reason: "your usual agent" });
  });

  it("returns null when no routable coding agent is connected", () => {
    expect(resolveBestAgent({ connected: ["pi-mono"], taskText: "use the best agent" })).toBeNull();
    expect(resolveBestAgent({ connected: [], taskText: "anything" })).toBeNull();
  });

  it("falls back to another signed-in agent when the usual one is connected but not set up", () => {
    // codex is connected but not signed in -> use another agent that is.
    expect(resolveBestAgent({ connected: ALL, taskText: "fix the bug", preferred: "codex", isReady: (id) => id !== "codex" }))
      .toMatchObject({ adapterId: "acp", reason: "codex isn't set up, using this one instead" });
    expect(resolveBestAgent({ connected: ["codex", "hermes"], taskText: "fix the bug", preferred: "codex", isReady: (id) => id === "hermes" }))
      .toMatchObject({ adapterId: "hermes" });
    // Preferred not set up and nothing else is ready -> null (caller uses Omi's default).
    expect(resolveBestAgent({ connected: ["codex"], taskText: "fix the bug", preferred: "codex", isReady: () => false })).toBeNull();
  });

  it("treats acp as signed in and a missing home as not signed in for local agents", () => {
    expect(isAgentSignedIn("acp", "/nonexistent-home")).toBe(true);
    expect(isAgentSignedIn("codex", "/nonexistent-home")).toBe(false);
    expect(isAgentSignedIn("hermes", "/nonexistent-home")).toBe(false);
  });
});
