#!/usr/bin/env node
// Minimal fake codex-acp ACP server for live (real-subprocess) integration
// testing. Speaks newline-delimited JSON-RPC over stdio, mirroring the subset
// of @agentclientprotocol/codex-acp that Omi's AcpRuntimeAdapter drives:
//   initialize -> session/new -> session/prompt (+ streaming session/update).
//
// It echoes selected env vars it received back in the assistant text so the
// test can prove the adapter forwarded auth/config to the real subprocess.
import { createInterface } from "node:readline";

function send(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}
function log(msg) {
  process.stderr.write(`[fake-codex-acp] ${msg}\n`);
}

const rl = createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const text = line.trim();
  if (!text) return;
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    log(`unparseable line: ${text}`);
    return;
  }
  const { id, method, params } = msg;
  switch (method) {
    case "initialize":
      send({ jsonrpc: "2.0", id, result: { protocolVersion: 1 } });
      break;
    case "session/new":
      // Assert the adapter sent an empty per-session MCP list (codex mode).
      log(`session/new mcpServers=${JSON.stringify(params?.mcpServers ?? null)}`);
      send({ jsonrpc: "2.0", id, result: { sessionId: "codex-live-session" } });
      break;
    case "session/set_model":
      // Should never be called for Codex (supportsSessionSetModel=false).
      log("UNEXPECTED session/set_model");
      send({ jsonrpc: "2.0", id, result: {} });
      break;
    case "session/prompt": {
      // Model the "no key AND no stored login" case: real codex-acp fails when
      // it tries to reach OpenAI with no credentials. (This stub can't see a
      // real ~/.codex login, so absence-of-key stands in for fully-unauthed.)
      if (!process.env.OPENAI_API_KEY && !process.env.CODEX_API_KEY) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32603, message: "Not authenticated. Run `codex login` or set OPENAI_API_KEY." },
        });
        break;
      }
      const auth = process.env.OPENAI_API_KEY ? "auth=1" : "auth=0";
      const mode = process.env.INITIAL_AGENT_MODE ?? "mode=unset";
      const noBrowser = process.env.NO_BROWSER ?? "nb=unset";
      // Stream a chunk that encodes what env the real subprocess received.
      send({
        jsonrpc: "2.0",
        method: "session/update",
        params: {
          update: {
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: `CODEX_LIVE_OK ${auth} ${mode} ${noBrowser}` },
          },
        },
      });
      send({
        jsonrpc: "2.0",
        id,
        result: { stopReason: "end_turn", usage: { inputTokens: 5, outputTokens: 6, cachedReadTokens: 1 } },
      });
      break;
    }
    case "session/cancel":
      log("cancel");
      break;
    default:
      if (id !== undefined) send({ jsonrpc: "2.0", id, result: {} });
      break;
  }
});
