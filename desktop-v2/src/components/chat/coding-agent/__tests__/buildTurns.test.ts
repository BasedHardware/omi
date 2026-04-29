/**
 * Unit tests for buildTurns — the pure reducer that converts a flat
 * AgentEvent array into a structured Turn list for the Coding Agent UI.
 *
 * No DOM, no React, no Tauri — plain logic tests.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { buildTurns, resetIdCounter } from "../buildTurns";
import type { AgentEvent } from "@/hooks/useCodingAgent";

// Reset the monotonic counter before each test so id values are predictable
// and tests are order-independent.
beforeEach(() => {
  resetIdCounter();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function text(t: string): AgentEvent {
  return { type: "text", text: t };
}

function toolCall(id: string, tool = "bash", input: unknown = { command: "ls" }): AgentEvent {
  return { type: "tool_call", tool, input, id };
}

function toolResult(id: string, output: string, isError = false): AgentEvent {
  return { type: "tool_result", id, output, isError };
}

function error(message: string): AgentEvent {
  return { type: "error", message };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("buildTurns", () => {
  it("returns an empty array for an empty event list", () => {
    expect(buildTurns([])).toEqual([]);
  });

  it("maps a single text event to one open assistant turn with one text chunk", () => {
    const turns = buildTurns([text("Hello!")]);

    expect(turns).toHaveLength(1);
    const [turn] = turns;
    expect(turn.role).toBe("assistant");
    expect(turn.isOpen).toBe(true);
    expect(turn.items).toHaveLength(1);

    const item = turn.items[0];
    expect(item.kind).toBe("text");
    if (item.kind === "text") {
      expect(item.text).toBe("Hello!");
    }
  });

  it("concatenates consecutive text events into a single text chunk", () => {
    const turns = buildTurns([text("Hello"), text(", "), text("world!")]);

    expect(turns).toHaveLength(1);
    expect(turns[0].items).toHaveLength(1);
    const item = turns[0].items[0];
    expect(item.kind).toBe("text");
    if (item.kind === "text") {
      expect(item.text).toBe("Hello, world!");
    }
  });

  it("correlates tool_call + tool_result by id into a single ToolSlot", () => {
    const events: AgentEvent[] = [
      text("About to run:"),
      toolCall("tc-1", "bash", { command: "echo hi" }),
      toolResult("tc-1", "hi\n"),
    ];

    const turns = buildTurns(events);

    expect(turns).toHaveLength(1);
    const items = turns[0].items;
    // text chunk + tool slot
    expect(items).toHaveLength(2);

    const slot = items[1];
    expect(slot.kind).toBe("tool");
    if (slot.kind === "tool") {
      expect(slot.call.id).toBe("tc-1");
      expect(slot.call.tool).toBe("bash");
      expect(slot.result?.output).toBe("hi\n");
      expect(slot.result?.isError).toBe(false);
    }
  });

  it("correlates a tool_result to the correct slot even when multiple tool_calls are present", () => {
    const events: AgentEvent[] = [
      toolCall("tc-A", "read", { path: "/foo" }),
      toolCall("tc-B", "bash", { command: "echo 1" }),
      toolResult("tc-B", "1\n"),
      toolResult("tc-A", "file contents"),
    ];

    const turns = buildTurns(events);
    const items = turns[0].items;

    const slotA = items.find((i) => i.kind === "tool" && i.call.id === "tc-A");
    const slotB = items.find((i) => i.kind === "tool" && i.call.id === "tc-B");

    expect(slotA?.kind).toBe("tool");
    expect(slotB?.kind).toBe("tool");
    if (slotA?.kind === "tool") expect(slotA.result?.output).toBe("file contents");
    if (slotB?.kind === "tool") expect(slotB.result?.output).toBe("1\n");
  });

  it("replaces an earlier result when two tool_result events share the same id", () => {
    // Unusual but must not duplicate the slot.
    const events: AgentEvent[] = [
      toolCall("tc-dup", "bash", { command: "echo 1" }),
      toolResult("tc-dup", "first"),
      toolResult("tc-dup", "second"),
    ];

    const turns = buildTurns(events);
    const slots = turns[0].items.filter((i) => i.kind === "tool");

    // Still only one slot — no duplication.
    expect(slots).toHaveLength(1);
    if (slots[0].kind === "tool") {
      expect(slots[0].result?.output).toBe("second");
    }
  });

  it("adds an error slot and closes the turn when an error event arrives", () => {
    const events: AgentEvent[] = [
      text("Starting..."),
      error("Extension error: permission denied"),
    ];

    const turns = buildTurns(events);

    expect(turns).toHaveLength(1);
    const turn = turns[0];
    expect(turn.isOpen).toBe(false);

    const errorItem = turn.items.find((i) => i.kind === "error");
    expect(errorItem).toBeDefined();
    if (errorItem?.kind === "error") {
      expect(errorItem.message).toBe("Extension error: permission denied");
    }
  });

  it("starts a new assistant turn after an error closes the previous one", () => {
    // Once a turn is closed (isOpen=false), new assistant events must open a fresh turn.
    const events: AgentEvent[] = [
      error("boom"),
      text("Recovered"),
    ];

    const turns = buildTurns(events);

    // Two turns: first closed by error, second opened for the text.
    expect(turns).toHaveLength(2);
    expect(turns[0].isOpen).toBe(false);
    expect(turns[1].isOpen).toBe(true);
    const textItem = turns[1].items[0];
    expect(textItem.kind).toBe("text");
    if (textItem.kind === "text") {
      expect(textItem.text).toBe("Recovered");
    }
  });

  it("ignores tool_result events with unknown ids", () => {
    const events: AgentEvent[] = [
      toolCall("tc-known", "bash", { command: "echo 1" }),
      toolResult("tc-unknown", "should be ignored"),
    ];

    const turns = buildTurns(events);
    const slot = turns[0].items[0];
    expect(slot.kind).toBe("tool");
    if (slot.kind === "tool") {
      expect(slot.result).toBeUndefined();
    }
  });
});
