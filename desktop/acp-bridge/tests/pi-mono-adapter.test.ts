import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { PiMonoAdapter } from "../src/adapters/pi-mono.js";
import type { HarnessConfig } from "../src/adapters/interface.js";
import type { OutboundMessage } from "../src/protocol.js";

function createAdapter() {
  const config: HarnessConfig = {
    passApiKey: false,
    authToken: "test-token",
  };
  const adapter = new PiMonoAdapter(config);
  const events: OutboundMessage[] = [];

  (adapter as any).sendCommand = vi.fn();

  return { adapter, events };
}

function makeTurnEndEvent(text: string, totalCost = 1.25) {
  return {
    type: "turn_end",
    message: {
      role: "assistant",
      content: [{ type: "text", text }],
      usage: {
        input: 11,
        output: 7,
        cacheRead: 3,
        cacheWrite: 2,
        totalTokens: 23,
        cost: {
          input: 0.1,
          output: 0.2,
          cacheRead: 0.3,
          cacheWrite: 0.4,
          total: totalCost,
        },
      },
    },
  };
}

describe("PiMonoAdapter prompt correlation", () => {
  it("rejects the previous prompt when a new generation supersedes it", async () => {
    const { adapter, events } = createAdapter();

    const firstPrompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "first" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    const secondPrompt = adapter.sendPrompt(
      "session-2",
      [{ type: "text", text: "second" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    await expect(firstPrompt).rejects.toThrow(
      "pi-mono prompt superseded before turn_end"
    );

    (adapter as any).handleTurnEnd(makeTurnEndEvent("second response", 2.5));

    await expect(secondPrompt).resolves.toMatchObject({
      text: "second response",
      sessionId: "session-2",
      costUsd: 2.5,
      inputTokens: 11,
      outputTokens: 7,
      cacheReadTokens: 3,
      cacheWriteTokens: 2,
    });
    expect(events).toContainEqual(
      expect.objectContaining({
        type: "result",
        text: "second response",
        sessionId: "session-2",
      })
    );
  });

  it("resolves abort before turn_end and drops the late completion", async () => {
    const { adapter, events } = createAdapter();

    const prompt = adapter.sendPrompt(
      "session-1",
      [{ type: "text", text: "abort me" }],
      [],
      "act",
      (event) => events.push(event),
      async () => ""
    );

    adapter.abort("session-1");

    await expect(prompt).resolves.toMatchObject({
      text: "",
      sessionId: "session-1",
      costUsd: 0,
      inputTokens: 0,
      outputTokens: 0,
    });

    (adapter as any).handleTurnEnd(makeTurnEndEvent("late response"));

    expect(events).toEqual([]);
    expect((adapter as any).activePromptGeneration).toBe(0);
  });

  it("drops stray turn_end events when no prompt is in flight", () => {
    const { adapter, events } = createAdapter();

    (adapter as any).eventHandler = (event: OutboundMessage) => events.push(event);
    (adapter as any).handleTurnEnd(makeTurnEndEvent("orphaned response"));

    expect(events).toEqual([]);
    expect((adapter as any).pendingRequests.size).toBe(0);
  });
});

describe("PiMonoAdapter source-level invariants", () => {
  // Source-level assertions verify security and integration invariants that
  // are hard to test via mocking (start() spawns a real subprocess). Reading
  // the source file is enough to catch regressions at review time.
  const piMonoSrc = readFileSync(
    fileURLToPath(new URL("../src/adapters/pi-mono.ts", import.meta.url)),
    "utf8"
  );

  it("passes the raw authToken as OMI_API_KEY (no `Bearer ` prefix)", () => {
    // Must assign the raw token, not a "Bearer ${...}" wrapper.
    expect(piMonoSrc).toMatch(/env\.OMI_API_KEY\s*=\s*this\.config\.authToken\s*;?/);
    // And must NOT reintroduce the old Bearer-prefixed assignment.
    expect(piMonoSrc).not.toMatch(/env\.OMI_API_KEY\s*=\s*`Bearer \$\{/);
  });

  it("always scrubs ANTHROPIC_API_KEY from the child env", () => {
    expect(piMonoSrc).toMatch(/delete\s+env\.ANTHROPIC_API_KEY\s*;?/);
  });

  it("does NOT include --no-extensions in spawn args (auto-discovery enabled)", () => {
    // Pi-mono should auto-discover extensions and MCP servers from the user's
    // machine to maximize capability. The --no-extensions flag was intentionally
    // removed; this test guards against re-adding it.
    expect(piMonoSrc).not.toMatch(/["']--no-extensions["']/);
  });
});

describe("runPiMonoMode tool_use event filtering", () => {
  // The event callback in runPiMonoMode() must filter out tool_use events
  // from the adapter before forwarding to Swift. Without this filter, Swift
  // would double-execute tools that pi-mono already handles internally
  // (built-in tools) or via the Unix socket relay (OMI extension tools).
  const indexSrc = readFileSync(
    fileURLToPath(new URL("../src/index.ts", import.meta.url)),
    "utf8"
  );

  it("filters tool_use events in the pi-mono event callback", () => {
    // The callback must check event.type === "tool_use" and return early.
    // Match the pattern: if ((event as any).type === "tool_use") return;
    expect(indexSrc).toMatch(/\.type\s*===\s*["']tool_use["']\)\s*return/);
  });

  it("still forwards non-tool_use events via send()", () => {
    // After the filter, events should still reach send().
    // The pattern is: send(event as OutboundMessage)
    expect(indexSrc).toMatch(/send\(event\s+as\s+OutboundMessage\)/);
  });
});
