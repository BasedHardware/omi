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

  // Patch 1: Set model if requested
  if (params.model && session?.query?.setModel) {
    try {
      await session.query.setModel(params.model);
      console.error(`[patched-acp] Model set to: ${params.model}`);
    } catch (err) {
      console.error(`[patched-acp] setModel failed: ${err}`);
    }
  }

  // Patch 2: Wrap query.next() to intercept SDKResultSuccess and capture cost/usage.
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
        // Debug: dump full result message to inspect actual field names/values
        const debugKeys = Object.keys(item.value).filter(k => !["type", "subtype", "result", "uuid", "session_id", "permission_denials", "structured_output"].includes(k));
        const debugObj = {};
        for (const k of debugKeys) debugObj[k] = item.value[k];
        console.error(`[patched-acp] SDKResultSuccess fields: ${JSON.stringify(debugObj)}`);

        session._lastCostUsd = item.value.total_cost_usd ?? item.value.totalCostUSD;
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
    const sdkUsage = session._lastUsage ?? {};
    const modelUsage = session._lastModelUsage ?? {};

    // Try both snake_case (API) and camelCase (SDK transforms)
    const inputTokens = sdkUsage.input_tokens ?? sdkUsage.inputTokens ?? 0;
    const outputTokens = sdkUsage.output_tokens ?? sdkUsage.outputTokens ?? 0;
    const cacheRead = sdkUsage.cache_read_input_tokens ?? sdkUsage.cacheReadInputTokens ?? null;
    const cacheWrite = sdkUsage.cache_creation_input_tokens ?? sdkUsage.cacheCreationInputTokens ?? null;

    console.error(
      `[patched-acp] Usage: cost=$${session._lastCostUsd}, ` +
      `input=${inputTokens}, output=${outputTokens}, ` +
      `cacheRead=${cacheRead}, cacheWrite=${cacheWrite}, ` +
      `modelUsage=${JSON.stringify(modelUsage)}`
    );

    const augmented = {
      ...result,
      usage: {
        inputTokens,
        outputTokens,
        cachedReadTokens: cacheRead,
        cachedWriteTokens: cacheWrite,
        totalTokens: (inputTokens) + (outputTokens) + (cacheRead ?? 0) + (cacheWrite ?? 0),
      },
      _meta: { costUsd: session._lastCostUsd },
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
