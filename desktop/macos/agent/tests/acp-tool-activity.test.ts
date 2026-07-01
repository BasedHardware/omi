import { describe, expect, it } from "vitest";
import { AcpRuntimeAdapter } from "../src/adapters/acp.js";

function translateHarness() {
  const adapter = new AcpRuntimeAdapter({
    nodeBin: "/node",
    acpEntry: "/acp-entry.mjs",
  });
  const events: Array<any> = [];
  const pendingTools: Array<any> = [];
  let syntheticId = 0;
  const translate = (adapter as any).translateSessionUpdate.bind(adapter);
  const nextId = () => `synthetic-${++syntheticId}`;

  return {
    events,
    pendingTools,
    translate: (update: Record<string, unknown>) => translate(
      { update },
      pendingTools,
      nextId,
      (event: any) => events.push(event),
      () => {}
    ),
  };
}

describe("AcpRuntimeAdapter tool activity translation", () => {
  it("preserves pending tool ids when text implicitly completes tools", () => {
    const harness = translateHarness();

    harness.translate({
      sessionUpdate: "tool_call",
      toolCallId: "tool-1",
      status: "pending",
      title: "Read",
      rawInput: { path: "README.md" },
    });
    harness.translate({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "done" },
    });

    expect(harness.events).toContainEqual({
      type: "tool_activity",
      name: "Read",
      status: "started",
      toolUseId: "tool-1",
      input: { path: "README.md" },
    });
    expect(harness.events).toContainEqual({
      type: "tool_activity",
      name: "Read",
      status: "completed",
      toolUseId: "tool-1",
    });
  });

  it("synthesizes stable tool ids when ACP omits toolCallId", () => {
    const harness = translateHarness();

    harness.translate({
      sessionUpdate: "tool_call",
      status: "pending",
      title: "Bash",
    });
    harness.translate({
      sessionUpdate: "tool_call_update",
      status: "completed",
      title: "Bash",
    });

    expect(harness.events).toEqual([
      {
        type: "tool_activity",
        name: "Bash",
        status: "started",
        toolUseId: "synthetic-1",
        input: undefined,
      },
      {
        type: "tool_activity",
        name: "Bash",
        status: "completed",
        toolUseId: "synthetic-1",
      },
    ]);
  });

  it("does not merge duplicate same-title starts when ACP omits toolCallId", () => {
    const harness = translateHarness();

    harness.translate({
      sessionUpdate: "tool_call",
      status: "pending",
      title: "Bash",
      rawInput: { command: "pwd" },
    });
    harness.translate({
      sessionUpdate: "tool_call",
      status: "pending",
      title: "Bash",
      rawInput: { command: "ls" },
    });
    harness.translate({
      sessionUpdate: "tool_call_update",
      status: "completed",
      title: "Bash",
    });
    harness.translate({
      sessionUpdate: "tool_call_update",
      status: "completed",
      title: "Bash",
    });

    expect(harness.events).toEqual([
      {
        type: "tool_activity",
        name: "Bash",
        status: "started",
        toolUseId: "synthetic-1",
        input: { command: "pwd" },
      },
      {
        type: "tool_activity",
        name: "Bash",
        status: "started",
        toolUseId: "synthetic-2",
        input: { command: "ls" },
      },
      {
        type: "tool_activity",
        name: "Bash",
        status: "completed",
        toolUseId: "synthetic-1",
      },
      {
        type: "tool_activity",
        name: "Bash",
        status: "completed",
        toolUseId: "synthetic-2",
      },
    ]);
  });

  it("maps ACP failed and cancelled tool updates to failed activity", () => {
    const harness = translateHarness();

    harness.translate({
      sessionUpdate: "tool_call_update",
      toolCallId: "tool-failed",
      status: "failed",
      title: "Read",
    });
    harness.translate({
      sessionUpdate: "tool_call_update",
      toolCallId: "tool-cancelled",
      status: "cancelled",
      title: "Bash",
    });

    expect(harness.events).toEqual([
      {
        type: "tool_activity",
        name: "Read",
        status: "failed",
        toolUseId: "tool-failed",
      },
      {
        type: "tool_activity",
        name: "Bash",
        status: "failed",
        toolUseId: "tool-cancelled",
      },
    ]);
  });
});
