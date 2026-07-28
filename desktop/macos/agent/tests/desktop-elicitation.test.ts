import { describe, expect, it } from "vitest";
import {
  classifyAcpPermission,
  dispatchKindFor,
  normalizeAcpPermission,
  normalizeAskUser,
} from "../src/runtime/desktop-elicitation.js";

function acpParams(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    sessionId: "sess_external_1",
    toolCall: {
      toolCallId: "tool_1",
      title: "Run a shell command",
      kind: "execute",
      rawInput: { command: "rm -rf build/" },
      locations: [{ path: "/Users/dev/omi" }],
    },
    options: [
      { optionId: "once", name: "Allow once", kind: "allow_once" },
      { optionId: "always", name: "Allow always", kind: "allow_always" },
      { optionId: "no", name: "Deny", kind: "reject_once" },
    ],
    ...overrides,
  };
}

describe("ACP permission normalization", () => {
  it("preserves option identity and human labels", () => {
    const request = normalizeAcpPermission({
      adapterId: "hermes",
      agentLabel: "Hermes",
      params: acpParams(),
    });

    expect(request).not.toBeNull();
    expect(request!.mode).toBe("permission");
    expect(request!.externalSessionId).toBe("sess_external_1");
    expect(request!.options.map((option) => option.optionId)).toEqual(["once", "always", "no"]);
    expect(request!.options.map((option) => option.label)).toEqual([
      "Allow once",
      "Allow always",
      "Deny",
    ]);
    expect(request!.options.map((option) => option.effect)).toEqual([
      "allow_once",
      "allow_always",
      "reject_once",
    ]);
  });

  it("surfaces the command and location so the card can state what it approves", () => {
    const request = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Omi",
      params: acpParams(),
    });

    expect(request!.prompt).toBe("Run a shell command");
    expect(request!.subject).toBe("rm -rf build/");
    expect(request!.context).toBe("/Users/dev/omi");
  });

  it("never allows free text, because ACP responses may only echo an optionId", () => {
    const request = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Omi",
      params: acpParams(),
    });

    expect(request!.allowsFreeText).toBe(false);
  });

  it("returns null when no usable option is offered", () => {
    expect(
      normalizeAcpPermission({
        adapterId: "acp",
        agentLabel: "Omi",
        params: acpParams({ options: [] }),
      }),
    ).toBeNull();
    expect(
      normalizeAcpPermission({
        adapterId: "acp",
        agentLabel: "Omi",
        params: acpParams({ options: [{ name: "no id", kind: "allow_once" }] }),
      }),
    ).toBeNull();
  });

  it("survives a malformed payload from an untrusted external adapter", () => {
    expect(normalizeAcpPermission({ adapterId: "x", agentLabel: "X", params: null })).toBeNull();
    expect(normalizeAcpPermission({ adapterId: "x", agentLabel: "X", params: "nope" })).toBeNull();

    const partial = normalizeAcpPermission({
      adapterId: "x",
      agentLabel: "X",
      params: { options: [{ optionId: "a" }] },
    });
    expect(partial!.options[0]).toEqual({ optionId: "a", label: "a", effect: "choice" });
    expect(partial!.subject).toBeNull();
    expect(partial!.context).toBeNull();
    expect(partial!.externalSessionId).toBeNull();
  });

  it("does not repeat the same path as both subject and context", () => {
    // Shape taken from a live Claude Code file-write permission, which reports
    // the identical path in rawInput and locations.
    const request = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Claude Code",
      params: acpParams({
        toolCall: {
          title: "Write /tmp/notes.txt",
          kind: "edit",
          rawInput: { file_path: "/tmp/notes.txt" },
          locations: [{ path: "/tmp/notes.txt" }],
        },
      }),
    });

    expect(request!.subject).toBe("/tmp/notes.txt");
    expect(request!.context).toBeNull();
  });

  it("keeps the location when it says something the subject does not", () => {
    const request = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Claude Code",
      params: acpParams({
        toolCall: {
          title: "Run a command",
          kind: "execute",
          rawInput: { command: "npm test" },
          locations: [{ path: "/Users/dev/omi" }],
        },
      }),
    });

    expect(request!.subject).toBe("npm test");
    expect(request!.context).toBe("/Users/dev/omi");
  });

  it("falls back to serialized raw input rather than approving an unnamed action", () => {
    const request = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Omi",
      params: acpParams({
        toolCall: { title: "Do a thing", rawInput: { pattern: "**/*.ts", limit: 5 } },
      }),
    });

    expect(request!.subject).toBe('{"pattern":"**/*.ts","limit":5}');
  });
});

describe("ACP auto-resolution rule", () => {
  const request = normalizeAcpPermission({
    adapterId: "acp",
    agentLabel: "Omi",
    params: acpParams(),
  })!;

  it("auto-allows a one-time grant on a read-shaped tool", () => {
    for (const kind of ["read", "search", "think"]) {
      const decision = classifyAcpPermission(request, kind);
      expect(decision.decision).toBe("auto");
      expect(decision).toMatchObject({ optionId: "once" });
    }
  });

  it("asks the user for anything that mutates, executes, or leaves the machine", () => {
    for (const kind of ["edit", "delete", "move", "execute", "fetch", "switch_mode", "other"]) {
      expect(classifyAcpPermission(request, kind).decision).toBe("dispatch");
    }
  });

  it("asks the user when a read-shaped tool only offers a remembered grant", () => {
    const permanentOnly = normalizeAcpPermission({
      adapterId: "hermes",
      agentLabel: "Hermes",
      params: acpParams({
        options: [{ optionId: "always", name: "Allow always", kind: "allow_always" }],
      }),
    })!;

    const decision = classifyAcpPermission(permanentOnly, "read");
    expect(decision.decision).toBe("dispatch");
    expect(decision.reason).toContain("no one-time allow");
  });

  it("never gates asking the user behind a permission to ask", () => {
    // The agent calling ask_user must not produce a permission card about
    // ask_user: that is two cards for one question, and the first is noise.
    for (const name of ["ask_user", "mcp__omi-tools__ask_user", "mcp__omi_tools__ask_user"]) {
      const decision = classifyAcpPermission(request, "other", name);
      expect(decision.decision).toBe("auto");
      expect(decision).toMatchObject({ optionId: "once" });
    }
  });

  it("still gates every other tool that happens to share the prefix", () => {
    for (const name of ["mcp__omi-tools__execute_sql", "ask_user_details", "write_file"]) {
      expect(classifyAcpPermission(request, "other", name).decision).toBe("dispatch");
    }
  });

  it("prefers a one-time grant so asking never accumulates a remembered one", () => {
    const permanentOnly = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Claude Code",
      params: acpParams({
        options: [{ optionId: "always", name: "Always Allow", kind: "allow_always" }],
      }),
    })!;

    // Only a permanent option is offered, so it is used — the effect being
    // authorized is the question itself, which is harmless to remember.
    expect(classifyAcpPermission(permanentOnly, "other", "ask_user")).toMatchObject({
      decision: "auto",
      optionId: "always",
    });
  });

  it("treats a missing or non-string tool kind as not read-shaped", () => {
    expect(classifyAcpPermission(request, undefined).decision).toBe("dispatch");
    expect(classifyAcpPermission(request, 42).decision).toBe("dispatch");
  });
});

describe("ask_user normalization", () => {
  it("accepts plain string options", () => {
    const [request] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { questions: [{ question: "Which branch?", options: ["main", "develop"] }] },
    });

    expect(request.options).toEqual([
      { optionId: "main", label: "main", effect: "choice" },
      { optionId: "develop", label: "develop", effect: "choice" },
    ]);
    expect(request.allowsFreeText).toBe(true);
  });

  it("accepts labelled options with stable ids", () => {
    const [request] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { questions: [{ question: "Pick", options: [{ id: "b1", label: "Branch one" }] }] },
    });

    expect(request.options).toEqual([{ optionId: "b1", label: "Branch one", effect: "choice" }]);
  });

  it("honours an explicit free-text opt-out per question", () => {
    const requests = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [
          { question: "Pick one", options: ["a", "b"], allow_free_text: false },
          { question: "And a name?" },
        ],
      },
    });

    // Free text is a per-question property: opting one out must not carry to
    // the rest of the set.
    expect(requests.map((request) => request.allowsFreeText)).toEqual([false, true]);
  });

  it("turns one call into one request per question, in the order asked", () => {
    const requests = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [
          { question: "Which stack?", options: ["Next.js", "SwiftUI"] },
          { question: "What name?" },
          { question: "Host where?", options: ["Vercel", "Fly"] },
        ],
      },
    });

    expect(requests.map((request) => request.prompt)).toEqual([
      "Which stack?",
      "What name?",
      "Host where?",
    ]);
    expect(requests.every((request) => request.mode === "question")).toBe(true);
    expect(requests.every((request) => request.channel === "omi_ask_user")).toBe(true);
  });

  it("drops a blank option instead of losing the question it belongs to", () => {
    // Observed live: a model padded a free-text question with options: [""].
    // Rejecting the call for it discarded all four questions the user was
    // about to be asked.
    const requests = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: {
        questions: [
          { question: "Which stack?", options: [""], allow_free_text: true },
          { question: "Host where?", options: ["Vercel", "", "Fly"] },
        ],
      },
    });

    expect(requests).toHaveLength(2);
    expect(requests[0].options).toEqual([]);
    expect(requests[0].allowsFreeText).toBe(true);
    expect(requests[1].options.map((option) => option.label)).toEqual(["Vercel", "Fly"]);
  });

  it("drops an entry that asks nothing rather than carding an empty question", () => {
    const requests = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { questions: [{ question: "   " }, { question: "Real question?" }, {}] },
    });

    expect(requests.map((request) => request.prompt)).toEqual(["Real question?"]);
  });

  it("returns nothing without questions", () => {
    expect(normalizeAskUser({ adapterId: "a", agentLabel: "A", args: {} })).toEqual([]);
    expect(normalizeAskUser({ adapterId: "a", agentLabel: "A", args: null })).toEqual([]);
    expect(normalizeAskUser({ adapterId: "a", agentLabel: "A", args: { questions: [] } })).toEqual([]);
  });
});

describe("the relay does not put a clock on a question", () => {
  it("gives ask_user no deadline, under every name the relay sees", async () => {
    const { relayToolTimeoutMs, RELAY_TOOL_TIMEOUT_MS } = await import(
      "../src/runtime/desktop-elicitation.js"
    );

    // These are the exact shapes that arrive on the relay: bare, and MCP
    // prefixed by each server-name spelling in use.
    for (const name of ["ask_user", "mcp__omi-tools__ask_user", "mcp__omi_tools__ask_user"]) {
      expect(relayToolTimeoutMs(name), name).toBeNull();
    }

    // A person reading a question and deciding routinely takes longer than the
    // relay's two-minute budget; expiring it discards an answer the user is
    // still in the middle of giving.
    expect(RELAY_TOOL_TIMEOUT_MS).toBe(120_000);
  });

  it("leaves every other tool on the relay deadline", async () => {
    const { relayToolTimeoutMs, RELAY_TOOL_TIMEOUT_MS } = await import(
      "../src/runtime/desktop-elicitation.js"
    );

    for (const name of [
      "execute_sql",
      "mcp__omi_tools__get_memories",
      "spawn_agent",
      "ask_user_details",
      "",
    ]) {
      expect(relayToolTimeoutMs(name), name).toBe(RELAY_TOOL_TIMEOUT_MS);
    }
  });
});

describe("dispatch kind mapping", () => {
  it("records approvals and questions as existing dispatch kinds", () => {
    const permission = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Omi",
      params: acpParams(),
    })!;
    const [question] = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { questions: [{ question: "Which branch?" }] },
    });

    expect(dispatchKindFor(permission)).toBe("approval");
    expect(dispatchKindFor(question)).toBe("routing_choice");
  });
});

describe("ask_user is discoverable without being named", () => {
  it("tells the model when to reach for it, not just what it is", async () => {
    const { mcpToolDefinitionsForAdapter } = await import("../src/runtime/omi-tool-manifest.js");
    const askUser = mcpToolDefinitionsForAdapter("omi-tools-stdio", {}).find(
      (tool) => tool.name === "ask_user",
    );

    expect(askUser).toBeDefined();
    // MCP tool definitions carry `description` only — promptGuidelines are not
    // projected — so a description that omits the trigger conditions leaves the
    // tool firing only when a user names it out loud.
    const description = askUser!.description.toLowerCase();
    expect(description).toContain("ambiguous");
    expect(description).toContain("instead of guessing");
    expect(description).toContain("ask_followup");
  });

  it("is offered to the surfaces that can render the card", async () => {
    const { toolNamesForAdapter } = await import("../src/runtime/omi-tool-manifest.js");
    expect(toolNamesForAdapter("omi-tools-stdio")).toContain("ask_user");
  });
});
