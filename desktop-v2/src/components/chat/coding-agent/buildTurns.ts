/**
 * Pure function that derives the display turn list from the raw AgentEvent
 * stream.  Extracted from CodingAgentSession.tsx so it can be unit-tested
 * without a DOM or React context.
 */

import type { AgentEvent } from "@/hooks/useCodingAgent";
import type { ToolCall, ToolResult } from "./ToolCallBubble";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TextChunk {
  kind: "text";
  id: string;
  text: string;
}

export interface ToolSlot {
  kind: "tool";
  call: ToolCall;
  result?: ToolResult;
}

export interface ErrorSlot {
  kind: "error";
  id: string;
  message: string;
}

export type TurnItem = TextChunk | ToolSlot | ErrorSlot;

export interface Turn {
  id: string;
  role: "user" | "assistant";
  items: TurnItem[];
  /** True while events are still arriving for this turn. */
  isOpen: boolean;
}

// ---------------------------------------------------------------------------
// Monotonic counter (module-scoped, fine for a single render tree)
// ---------------------------------------------------------------------------

let _itemSeq = 0;
export function nextId(): string {
  return `item-${++_itemSeq}`;
}

/** Reset the counter — call this in test `beforeEach` for deterministic ids. */
export function resetIdCounter(): void {
  _itemSeq = 0;
}

// ---------------------------------------------------------------------------
// buildTurns
// ---------------------------------------------------------------------------

export function buildTurns(events: AgentEvent[]): Turn[] {
  const turns: Turn[] = [];

  const ensureAssistantTurn = (): Turn => {
    const last = turns[turns.length - 1];
    if (last && last.role === "assistant" && last.isOpen) return last;
    const t: Turn = { id: nextId(), role: "assistant", items: [], isOpen: true };
    turns.push(t);
    return t;
  };

  for (const ev of events) {
    if (ev.type === "user_text") {
      // Close any open assistant turn first.
      const last = turns[turns.length - 1];
      if (last && last.role === "assistant") last.isOpen = false;
      turns.push({
        id: nextId(),
        role: "user",
        items: [{ kind: "text", id: nextId(), text: ev.text }],
        isOpen: false,
      });
    } else if (ev.type === "text") {
      const turn = ensureAssistantTurn();
      const last = turn.items[turn.items.length - 1];
      if (last && last.kind === "text") {
        last.text += ev.text;
      } else {
        turn.items.push({ kind: "text", id: nextId(), text: ev.text });
      }
    } else if (ev.type === "tool_call") {
      const turn = ensureAssistantTurn();
      const slot: ToolSlot = {
        kind: "tool",
        call: { id: ev.id, tool: ev.tool, input: ev.input },
      };
      turn.items.push(slot);
    } else if (ev.type === "tool_result") {
      // Find the open slot with matching id.
      for (const turn of turns) {
        for (const item of turn.items) {
          if (item.kind === "tool" && item.call.id === ev.id) {
            item.result = { output: ev.output, isError: ev.isError };
          }
        }
      }
    } else if (ev.type === "error") {
      const turn = ensureAssistantTurn();
      turn.items.push({ kind: "error", id: nextId(), message: ev.message });
      turn.isOpen = false;
    }
  }

  return turns;
}
