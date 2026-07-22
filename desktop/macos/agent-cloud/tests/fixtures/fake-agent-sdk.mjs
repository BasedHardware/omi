// Scripted stand-in for @anthropic-ai/claude-agent-sdk, selected via
// OMI_AGENT_SDK_MODULE. Emits a fixed message sequence per turn so the WS e2e
// can assert the production stream-handling contract without a live model:
//   - main text arrives as stream_event deltas ("Part one. " / "Part two.")
//   - a subagent tool start + a leak canary ("SECRET-INTERNAL") arrive with
//     parent_tool_use_id set
//   - a prompt containing "SLOW" holds (no timers) until interrupt() fires,
//     then terminalizes with only the partial text
export { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";

export function query({ prompt }) {
  let interruptResolve;
  const interruptRequested = new Promise((resolve) => { interruptResolve = resolve; });
  let turnCount = 0; // survives across turns — a "COUNT" prompt reveals it, proving session continuity

  function streamText(text) {
    return { type: "stream_event", event: { type: "content_block_delta", delta: { type: "text_delta", text } } };
  }
  function resultMsg(text) {
    return { type: "result", subtype: "success", result: text, total_cost_usd: 0.001 };
  }

  async function* turnFor(text) {
    if (text === "ready") {
      // Prewarm turn — persistent sessions suppress its output.
      yield resultMsg("ok");
      return;
    }
    turnCount += 1;
    if (text.includes("COUNT")) {
      yield { type: "stream_event", event: { type: "content_block_start", content_block: { type: "text" } } };
      yield streamText(`turn:${turnCount}`);
      yield resultMsg(`turn:${turnCount}`);
      return;
    }
    yield { type: "stream_event", event: { type: "content_block_start", content_block: { type: "text" } } };
    yield streamText("Part one. ");
    yield {
      type: "stream_event",
      parent_tool_use_id: "toolu_sub_1",
      event: { type: "content_block_start", content_block: { type: "tool_use", name: "mcp__omi-tools__execute_sql" } },
    };
    yield {
      type: "stream_event",
      parent_tool_use_id: "toolu_sub_1",
      event: { type: "content_block_delta", delta: { type: "text_delta", text: "SECRET-INTERNAL" } },
    };
    yield {
      type: "assistant",
      parent_tool_use_id: "toolu_sub_1",
      message: { content: [{ type: "text", text: "SECRET-INTERNAL" }] },
    };
    if (text.includes("SLOW")) {
      console.error("[fake-sdk] holding for interrupt");
      await interruptRequested; // deterministic hold — released only by interrupt()
      console.error("[fake-sdk] resumed after interrupt");
      // The real SDK terminalizes an interrupted turn with a non-success
      // subtype (observed live) — the server must map it to an interrupted
      // partial result, not an error.
      yield { type: "result", subtype: "error_during_execution", errors: [], total_cost_usd: 0.001 };
      return;
    }
    yield streamText("Part two.");
    yield { type: "assistant", message: { content: [{ type: "text", text: "Part one. Part two." }] } };
    yield resultMsg("Part one. Part two.");
  }

  const iterator = (async function* () {
    yield { type: "system", session_id: "fake-session-1" };
    if (prompt && typeof prompt[Symbol.asyncIterator] === "function") {
      for await (const userMsg of prompt) {
        const content = userMsg?.message?.content;
        yield* turnFor(typeof content === "string" ? content : "");
      }
    } else {
      yield* turnFor(String(prompt));
    }
  })();

  iterator.interrupt = async () => { console.error("[fake-sdk] interrupt() called"); interruptResolve(); };
  iterator.close = async () => { interruptResolve(); };
  return iterator;
}
