#!/usr/bin/env node
/**
 * Custom ACP entry point that patches ClaudeAcpAgent to support:
 * - Model selection via session/new params (uses setModel() after session creation)
 *
 * Used instead of the default @zed-industries/claude-code-acp entry point.
 */

// Redirect console to stderr (same as original)
console.log = console.error;
console.info = console.error;
console.warn = console.error;
console.debug = console.error;

import { ClaudeAcpAgent, runAcp } from "@zed-industries/claude-agent-acp/dist/acp-agent.js";

// Patch newSession to pass model via setModel() after session creation
const originalNewSession = ClaudeAcpAgent.prototype.newSession;
ClaudeAcpAgent.prototype.newSession = async function (params) {
  const result = await originalNewSession.call(this, params);

  // If model was requested and session was created, set it
  if (params.model && this.sessions?.[result.sessionId]?.query?.setModel) {
    try {
      await this.sessions[result.sessionId].query.setModel(params.model);
      console.error(`[patched-acp] Model set to: ${params.model}`);
    } catch (err) {
      console.error(`[patched-acp] setModel failed: ${err}`);
    }
  }

  return result;
};

// Run the (now patched) ACP agent
runAcp();

// Keep process alive
process.stdin.resume();
