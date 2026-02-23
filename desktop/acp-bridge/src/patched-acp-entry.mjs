#!/usr/bin/env node
/**
 * Custom ACP entry point that patches ClaudeAcpAgent to support:
 * - Model selection via session/new params (uses setModel() after session creation)
 * - Real token usage and USD cost from SDKResultSuccess (via query.next interception)
 *
 * Used instead of the default @zed-industries/claude-agent-acp entry point.
 */

// Redirect console to stderr (same as original)
console.log = console.error;
console.info = console.error;
console.warn = console.error;
console.debug = console.error;

import { ClaudeAcpAgent, runAcp } from "@zed-industries/claude-agent-acp/dist/acp-agent.js";

// Patch newSession to:
// 1. Pass model via setModel() after session creation
// 2. Wrap query.next() to capture real cost/usage from SDKResultSuccess messages
const originalNewSession = ClaudeAcpAgent.prototype.newSession;
ClaudeAcpAgent.prototype.newSession = async function (params) {
  const result = await originalNewSession.call(this, params);

  const session = this.sessions?.[result.sessionId];

  // Wrap query.next() to intercept SDKResultSuccess and capture cost/usage.
  // The SDK result message has total_cost_usd and usage (input_tokens, output_tokens, etc.)
  // but acp-agent.js drops them and only returns { stopReason }. We capture them here
  // so that our patched prompt() can attach them to the response.
  if (session?.query) {
    const originalNext = session.query.next.bind(session.query);
    session.query.next = async function (...args) {
      const item = await originalNext(...args);
      if (
        item.value?.type === "result" &&
        item.value?.subtype === "success"
      ) {
        session._lastCostUsd = item.value.total_cost_usd;
        session._lastUsage = item.value.usage;
        session._lastModelUsage = item.value.modelUsage;
      }
      return item;
    };
  }

  return result;
};

// Patch prompt() to attach captured cost/usage to the return value.
// The ACP PromptResponse supports usage (experimental) and _meta for extras.
const originalPrompt = ClaudeAcpAgent.prototype.prompt;
ClaudeAcpAgent.prototype.prompt = async function (params) {
  const result = await originalPrompt.call(this, params);

  const session = this.sessions?.[params.sessionId];
  if (session?._lastCostUsd !== undefined) {
    // usage fields are snake_case (raw Anthropic API format)
    const u = session._lastUsage ?? {};
    const inputTokens = u.input_tokens ?? 0;
    const outputTokens = u.output_tokens ?? 0;
    const cacheRead = u.cache_read_input_tokens ?? 0;
    const cacheWrite = u.cache_creation_input_tokens ?? 0;
    const costUsd = session._lastCostUsd;

    // Total = new input + cache writes + cache reads + output
    const totalTokens = inputTokens + cacheWrite + cacheRead + outputTokens;

    console.error(
      `[patched-acp] Usage: cost=$${costUsd}, ` +
      `input=${inputTokens}, output=${outputTokens}, ` +
      `cacheWrite=${cacheWrite}, cacheRead=${cacheRead}, ` +
      `total=${totalTokens}`
    );

    const augmented = {
      ...result,
      usage: {
        inputTokens,
        outputTokens,
        cachedReadTokens: cacheRead,
        cachedWriteTokens: cacheWrite,
        totalTokens,
      },
      _meta: { costUsd },
    };
    delete session._lastCostUsd;
    delete session._lastUsage;
    delete session._lastModelUsage;
    return augmented;
  }

  return result;
};

// Run the (now patched) ACP agent
runAcp();

// Keep process alive
process.stdin.resume();
