import { describe, expect, it } from "vitest";

import { subagentClientEvents } from "../stream-routing.mjs";

describe("subagentClientEvents", () => {
  it("passes main-loop messages through untouched", () => {
    expect(subagentClientEvents({ type: "assistant", parent_tool_use_id: null })).toBeNull();
    expect(subagentClientEvents({ type: "stream_event" })).toBeNull();
  });

  it("surfaces subagent tool starts as prefixed tool_activity", () => {
    const fromStream = subagentClientEvents({
      type: "stream_event",
      parent_tool_use_id: "toolu_1",
      event: { type: "content_block_start", content_block: { type: "tool_use", name: "mcp__omi-tools__execute_sql" } },
    });
    expect(fromStream).toEqual([
      { type: "tool_activity", name: "subagent:mcp__omi-tools__execute_sql", status: "started" },
    ]);

    const fromAssistant = subagentClientEvents({
      type: "assistant",
      parent_tool_use_id: "toolu_1",
      message: { content: [{ type: "tool_use", name: "mcp__omi-tools__get_daily_recap" }] },
    });
    expect(fromAssistant).toEqual([
      { type: "tool_activity", name: "subagent:mcp__omi-tools__get_daily_recap", status: "started" },
    ]);
  });

  it("swallows subagent text so it never leaks into the main answer stream", () => {
    const textDelta = subagentClientEvents({
      type: "stream_event",
      parent_tool_use_id: "toolu_1",
      event: { type: "content_block_delta", delta: { type: "text_delta", text: "internal notes" } },
    });
    // Non-null empty array = "handled, emit nothing" — callers must not fall through.
    expect(textDelta).toEqual([]);

    const assistantText = subagentClientEvents({
      type: "assistant",
      parent_tool_use_id: "toolu_1",
      message: { content: [{ type: "text", text: "internal reasoning" }] },
    });
    expect(assistantText).toEqual([]);
  });
});
