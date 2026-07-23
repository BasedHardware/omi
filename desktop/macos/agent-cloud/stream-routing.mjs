// Routing for subagent-origin SDK messages (parent_tool_use_id set).
// Their text must never enter the main answer stream (text_delta/result), but
// delegated turns are the longest silent stretches a client sees (measured
// 30-46s pre-heartbeat; generic heartbeats after). The router surfaces two
// progress signals:
//   - tool starts as tool_activity (as before)
//   - a throttled, ephemeral `status` snippet of the text the subagent is
//     writing, so the wait shows real progress instead of "Still working…".
// Status events are presentation-only: callers never append them to fullText
// or the saved transcript.

const SNIPPET_MAX = 90;

export function createSubagentRouter({ throttleMs = 2500, now = Date.now } = {}) {
  let tail = "";
  let lastTextEmitAt = 0;

  return function route(message) {
    if (!message?.parent_tool_use_id) return null; // not subagent-origin
    const events = [];

    if (message.type === "stream_event") {
      const event = message.event;
      if (event?.type === "content_block_start" && event.content_block?.type === "tool_use") {
        events.push({ type: "tool_activity", name: `subagent:${event.content_block.name}`, status: "started" });
      }
      if (event?.type === "content_block_delta" && event.delta?.type === "text_delta") {
        tail = (tail + event.delta.text).slice(-SNIPPET_MAX);
        const t = now();
        const snippet = tail.replace(/\s+/g, " ").trim();
        if (t - lastTextEmitAt >= throttleMs && snippet) {
          lastTextEmitAt = t;
          events.push({ type: "status", message: `Researching… ${snippet}` });
        }
      }
    } else if (message.type === "assistant") {
      const content = message.message?.content;
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block.type === "tool_use") {
            events.push({ type: "tool_activity", name: `subagent:${block.name}`, status: "started" });
          }
          // Complete assistant text repeats what deltas already streamed —
          // fold it into the tail without forcing an extra emit.
          if (block.type === "text" && typeof block.text === "string") {
            tail = (tail + block.text).slice(-SNIPPET_MAX);
          }
        }
      }
    }
    // Non-null return means "subagent message: emit these (possibly none) and
    // do not process further" — callers must not fall through to text handling.
    return events;
  };
}
