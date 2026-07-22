// Routing for subagent-origin SDK messages (parent_tool_use_id set).
// Their internal text must never leak into the main answer stream, but their
// tool starts are the only progress signal during a delegation — surface them
// as tool_activity so the client has something to show (measured: delegated
// turns otherwise go 30-46s with zero client events).

export function subagentClientEvents(message) {
  if (!message?.parent_tool_use_id) return null; // not subagent-origin
  const events = [];
  if (message.type === "stream_event") {
    const event = message.event;
    if (event?.type === "content_block_start" && event.content_block?.type === "tool_use") {
      events.push({ type: "tool_activity", name: `subagent:${event.content_block.name}`, status: "started" });
    }
  } else if (message.type === "assistant") {
    const content = message.message?.content;
    if (Array.isArray(content)) {
      for (const block of content) {
        if (block.type === "tool_use") {
          events.push({ type: "tool_activity", name: `subagent:${block.name}`, status: "started" });
        }
      }
    }
  }
  // Non-null return means "subagent message: emit these (possibly none) and
  // do not process further" — callers must not fall through to text handling.
  return events;
}
