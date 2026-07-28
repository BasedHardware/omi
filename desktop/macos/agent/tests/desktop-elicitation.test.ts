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

  it("treats a missing or non-string tool kind as not read-shaped", () => {
    expect(classifyAcpPermission(request, undefined).decision).toBe("dispatch");
    expect(classifyAcpPermission(request, 42).decision).toBe("dispatch");
  });
});

describe("ask_user normalization", () => {
  it("accepts plain string options", () => {
    const request = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { question: "Which branch?", options: ["main", "develop"] },
    });

    expect(request!.options).toEqual([
      { optionId: "main", label: "main", effect: "choice" },
      { optionId: "develop", label: "develop", effect: "choice" },
    ]);
    expect(request!.allowsFreeText).toBe(true);
  });

  it("accepts labelled options with stable ids", () => {
    const request = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { question: "Pick", options: [{ id: "b1", label: "Branch one" }] },
    });

    expect(request!.options).toEqual([{ optionId: "b1", label: "Branch one", effect: "choice" }]);
  });

  it("honours an explicit free-text opt-out", () => {
    const request = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { question: "Pick one", options: ["a", "b"], allow_free_text: false },
    });

    expect(request!.allowsFreeText).toBe(false);
  });

  it("returns null without a question", () => {
    expect(normalizeAskUser({ adapterId: "a", agentLabel: "A", args: {} })).toBeNull();
    expect(normalizeAskUser({ adapterId: "a", agentLabel: "A", args: null })).toBeNull();
  });
});

describe("dispatch kind mapping", () => {
  it("records approvals and questions as existing dispatch kinds", () => {
    const permission = normalizeAcpPermission({
      adapterId: "acp",
      agentLabel: "Omi",
      params: acpParams(),
    })!;
    const question = normalizeAskUser({
      adapterId: "acp",
      agentLabel: "Omi",
      args: { question: "Which branch?" },
    })!;

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
