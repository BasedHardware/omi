import { describe, expect, it } from "vitest";

import { createSubagentRouter } from "../stream-routing.mjs";

const subDelta = (text) => ({
  type: "stream_event",
  parent_tool_use_id: "toolu_1",
  event: { type: "content_block_delta", delta: { type: "text_delta", text } },
});

describe("createSubagentRouter", () => {
  it("passes main-loop messages through untouched", () => {
    const route = createSubagentRouter();
    expect(route({ type: "assistant", parent_tool_use_id: null })).toBeNull();
    expect(route({ type: "stream_event" })).toBeNull();
  });

  it("surfaces subagent tool starts as prefixed tool_activity", () => {
    const route = createSubagentRouter();
    const fromStream = route({
      type: "stream_event",
      parent_tool_use_id: "toolu_1",
      event: { type: "content_block_start", content_block: { type: "tool_use", name: "mcp__omi-tools__execute_sql" } },
    });
    expect(fromStream).toEqual([
      { type: "tool_activity", name: "subagent:mcp__omi-tools__execute_sql", status: "started" },
    ]);

    const fromAssistant = route({
      type: "assistant",
      parent_tool_use_id: "toolu_1",
      message: { content: [{ type: "tool_use", name: "mcp__omi-tools__get_daily_recap" }] },
    });
    expect(fromAssistant).toEqual([
      { type: "tool_activity", name: "subagent:mcp__omi-tools__get_daily_recap", status: "started" },
    ]);
  });

  it("streams subagent text as throttled ephemeral status, never as text_delta", () => {
    let clock = 10_000;
    const route = createSubagentRouter({ throttleMs: 2500, now: () => clock });

    const first = route(subDelta("Top apps were "));
    expect(first).toEqual([{ type: "status", message: "Researching… Top apps were" }]);

    // Within the throttle window: handled, but nothing emitted.
    clock += 1000;
    expect(route(subDelta("Xcode (60) and "))).toEqual([]);

    // Past the window: one status with the rolling tail.
    clock += 2000;
    const third = route(subDelta("Safari (30)."));
    expect(third).toHaveLength(1);
    expect(third[0].type).toBe("status");
    expect(third[0].message).toContain("Xcode (60) and Safari (30).");
  });

  it("keeps the snippet bounded to a rolling tail", () => {
    let clock = 0;
    const route = createSubagentRouter({ throttleMs: 0, now: () => (clock += 1) });
    route(subDelta("x".repeat(300)));
    const events = route(subDelta("END"));
    expect(events[0].message.length).toBeLessThan(120);
    expect(events[0].message).toContain("END");
  });

  it("folds complete assistant text into the tail without forcing an emit", () => {
    let clock = 10_000;
    const route = createSubagentRouter({ throttleMs: 2500, now: () => clock });
    const events = route({
      type: "assistant",
      parent_tool_use_id: "toolu_1",
      message: { content: [{ type: "text", text: "internal reasoning" }] },
    });
    // Non-null empty array = "handled, emit nothing" — callers must not fall through.
    expect(events).toEqual([]);
  });
});
