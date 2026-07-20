import { describe, expect, it } from "vitest";
import {
  AGENT_INSTALL_INFO,
  classifyTask,
  detectExplicitAgent,
  installCommandFor,
  isRetryableAgentFailure,
  nextInChain,
  planFailover,
  resolveSpokenAgent,
  selectAgent,
  type AgentId,
} from "../src/runtime/agent-selector.js";

describe("failover", () => {
  const chain: AgentId[] = ["codex", "acp", "pi-mono"];

  it("retries on startup/execution errors, not on user-actionable ones", () => {
    expect(isRetryableAgentFailure("codex exec exited with code 1")).toBe(true);
    expect(isRetryableAgentFailure("adapter failed to start")).toBe(true);
    expect(isRetryableAgentFailure("user cancelled")).toBe(false);
    expect(isRetryableAgentFailure("authentication required")).toBe(false);
    expect(isRetryableAgentFailure("quota exceeded")).toBe(false);
  });

  it("plans the next agent with a transparent message", () => {
    const plan = planFailover(chain, "codex", "codex exec failed");
    expect(plan?.next).toBe("acp");
    expect(plan?.message).toContain("Codex");
    expect(plan?.message).toContain("Claude Code");
  });

  it("stops on a user-actionable error", () => {
    expect(planFailover(chain, "codex", "authentication required")).toBeNull();
  });

  it("stops when the chain is exhausted", () => {
    expect(planFailover(chain, "pi-mono", "some error")).toBeNull();
  });
});

describe("resolveSpokenAgent — STT-robust name matching", () => {
  const cases: Array<[string, AgentId]> = [
    ["codex", "codex"],
    ["code x", "codex"],
    ["codecs", "codex"],
    ["code decks", "codex"],
    ["hermes", "hermes"],
    ["her mees", "hermes"],
    ["hermies", "hermes"],
    ["openclaw", "openclaw"],
    ["open claw", "openclaw"],
    ["open flaw", "openclaw"],
    ["open clause", "openclaw"],
    ["claw", "openclaw"],
    ["claude code", "acp"],
    ["cloud code", "acp"],
    ["omi", "pi-mono"],
  ];
  for (const [spoken, expected] of cases) {
    it(`maps "${spoken}" -> ${expected}`, () => {
      const match = resolveSpokenAgent(spoken);
      expect(match?.agent).toBe(expected);
    });
  }

  it("returns null for non-agent words", () => {
    expect(resolveSpokenAgent("")).toBeNull();
    expect(resolveSpokenAgent("banana")).toBeNull();
    expect(resolveSpokenAgent("the weather today")).toBeNull();
  });

  it("reports a confidence in [0,1]", () => {
    const exact = resolveSpokenAgent("codex");
    expect(exact?.confidence).toBe(1);
    const fuzzy = resolveSpokenAgent("code decks");
    expect(fuzzy && fuzzy.confidence > 0 && fuzzy.confidence <= 1).toBe(true);
  });
});

describe("classifyTask", () => {
  it("routes coding tasks to codebase_edit", () => {
    expect(classifyTask("refactor the auth function and fix the bug")).toBe("codebase_edit");
    expect(classifyTask("implement a new endpoint in the repo")).toBe("codebase_edit");
  });
  it("routes shell/exec tasks to shell_ops", () => {
    expect(classifyTask("run npm install and build the project")).toBe("shell_ops");
    expect(classifyTask("deploy the docker container")).toBe("shell_ops");
  });
  it("routes messaging tasks to messaging", () => {
    expect(classifyTask("reply to the whatsapp message from mom")).toBe("messaging");
    expect(classifyTask("respond to that telegram")).toBe("messaging");
  });
  it("routes long-running tasks to long_autonomous", () => {
    expect(classifyTask("keep working on this overnight")).toBe("long_autonomous");
    expect(classifyTask("monitor the site every hour on a schedule")).toBe("long_autonomous");
  });
  it("routes research tasks to research", () => {
    expect(classifyTask("research the best vector databases and gather info")).toBe("research");
  });
  it("falls back to general", () => {
    expect(classifyTask("what's the weather like")).toBe("general");
  });
});

describe("detectExplicitAgent", () => {
  it("detects each agent by name", () => {
    expect(detectExplicitAgent("use codex to fix this")).toBe("codex");
    expect(detectExplicitAgent("have hermes handle it")).toBe("hermes");
    expect(detectExplicitAgent("ask openclaw to do it")).toBe("openclaw");
    expect(detectExplicitAgent("tell open claw to run it")).toBe("openclaw");
    expect(detectExplicitAgent("ask omi about my day")).toBe("pi-mono");
  });
  it("prefers the longest matching alias", () => {
    // "claude" and "claude code" both match -> Claude Code wins
    expect(detectExplicitAgent("use claude code for this refactor")).toBe("acp");
    expect(detectExplicitAgent("just ask claude")).toBe("acp");
  });
  it("returns undefined when no agent is named", () => {
    expect(detectExplicitAgent("fix the login bug")).toBeUndefined();
  });
  it("does not false-match substrings", () => {
    // "code" is not an alias; must not resolve to an agent by itself
    expect(detectExplicitAgent("write some code")).toBeUndefined();
  });
});

describe("selectAgent — explicit mention", () => {
  it("uses the explicitly named agent when connected and puts it first in the chain", () => {
    const out = selectAgent({
      taskText: "use codex to refactor the parser",
      available: ["acp", "codex", "pi-mono"],
    });
    expect(out.kind).toBe("selected");
    if (out.kind !== "selected") return;
    expect(out.primary).toBe("codex");
    expect(out.explicit).toBe(true);
    expect(out.chain[0]).toBe("codex");
    expect(out.chain).toContain("acp");
    expect(out.chain).toContain("pi-mono");
  });

  it("returns needs_install (never reroutes) when the named agent is not connected", () => {
    const out = selectAgent({
      taskText: "ask hermes to summarize my week",
      available: ["acp", "pi-mono"],
    });
    expect(out.kind).toBe("needs_install");
    if (out.kind !== "needs_install") return;
    expect(out.agent).toBe("hermes");
    expect(out.installCommand).toContain("hermes-agent.nousresearch.com");
    expect(out.docsUrl).toBe(AGENT_INSTALL_INFO.hermes?.docsUrl);
  });
});

describe("selectAgent — best fit + fallback chain", () => {
  it("picks a code agent for a coding task, Omi AI last", () => {
    const out = selectAgent({
      taskText: "implement a retry wrapper in the repo",
      available: ["pi-mono", "acp", "codex"],
    });
    if (out.kind !== "selected") throw new Error("expected selected");
    // acp and codex both score 3 for codebase_edit; DEFAULT_PRIORITY puts acp first
    expect(out.primary).toBe("acp");
    expect(out.chain[out.chain.length - 1]).toBe("pi-mono");
  });

  it("prefers Codex for shell/exec work", () => {
    const out = selectAgent({ taskText: "run the migration script in the terminal", available: ["acp", "codex"] });
    if (out.kind !== "selected") throw new Error("expected selected");
    expect(out.primary).toBe("codex"); // shell_ops: codex 3 > acp 2
  });

  it("prefers a multi-channel agent for messaging", () => {
    const out = selectAgent({ taskText: "reply to the telegram from sam", available: ["acp", "hermes"] });
    if (out.kind !== "selected") throw new Error("expected selected");
    expect(out.primary).toBe("hermes"); // messaging: hermes 3 > acp 0
  });

  it("prefers a long-running agent for overnight work", () => {
    const out = selectAgent({ taskText: "keep monitoring the feed overnight", available: ["acp", "openclaw"] });
    if (out.kind !== "selected") throw new Error("expected selected");
    expect(out.primary).toBe("openclaw"); // long_autonomous: openclaw 3 > acp 2
  });

  it("honors the user default only as a tiebreak", () => {
    const out = selectAgent({
      taskText: "add a unit test to the repo",
      available: ["acp", "codex"],
      userDefault: "codex",
    });
    if (out.kind !== "selected") throw new Error("expected selected");
    expect(out.primary).toBe("codex"); // tie at 3 -> user default wins
  });

  it("falls back to Omi AI when nothing is connected", () => {
    const out = selectAgent({ taskText: "fix the bug", available: [] });
    if (out.kind !== "selected") throw new Error("expected selected");
    expect(out.primary).toBe("pi-mono");
    expect(out.chain).toEqual(["pi-mono"]);
  });
});

describe("installCommandFor", () => {
  it("returns per-OS commands", () => {
    expect(installCommandFor("codex", "darwin")).toBe("npm install -g @openai/codex");
    expect(installCommandFor("codex", "win32")).toBe("npm install -g @openai/codex");
    expect(installCommandFor("openclaw", "darwin")).toContain("openclaw.ai/install.sh");
    expect(installCommandFor("openclaw", "win32")).toContain("install.ps1");
    expect(installCommandFor("hermes", "linux")).toContain("install.sh");
    expect(installCommandFor("acp", "darwin")).toBe("npm install -g @anthropic-ai/claude-code");
  });
  it("returns undefined for the built-in Omi AI", () => {
    expect(installCommandFor("pi-mono", "darwin")).toBeUndefined();
  });
});

describe("nextInChain", () => {
  it("advances to the next agent on failure", () => {
    const chain: AgentId[] = ["codex", "acp", "pi-mono"];
    expect(nextInChain(chain, "codex")).toBe("acp");
    expect(nextInChain(chain, "acp")).toBe("pi-mono");
  });
  it("returns undefined when the chain is exhausted", () => {
    expect(nextInChain(["codex", "acp"], "acp")).toBeUndefined();
    expect(nextInChain(["codex"], "hermes")).toBeUndefined();
  });
});
