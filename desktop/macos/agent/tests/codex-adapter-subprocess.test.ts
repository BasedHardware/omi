import { describe, expect, it } from "vitest";
import { chmodSync, mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { CodexRuntimeAdapter } from "../src/adapters/codex.js";
import type { AdapterAttemptContext, OutboundMessageDraft } from "../src/adapters/interface.js";

/**
 * Behavioral integration coverage for the Codex adapter with a REAL child
 * process: a stub `codex-acp` JSON-RPC server on stdio, exactly the transport
 * the production adapter spawns via OMI_CODEX_ADAPTER_COMMAND. This exercises
 * command spawn, ACP initialize/session/new/session/prompt, streaming
 * session/update translation, and terminal attempt classification.
 */
const STUB_ACP_SERVER = `
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin, terminal: false });
function send(obj) { process.stdout.write(JSON.stringify(obj) + "\\n"); }
rl.on("line", (line) => {
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  if (msg.method === "initialize") {
    send({ jsonrpc: "2.0", id: msg.id, result: { protocolVersion: 1 } });
  } else if (msg.method === "session/new") {
    send({ jsonrpc: "2.0", id: msg.id, result: { sessionId: "codex-stub-session-1" } });
  } else if (msg.method === "session/prompt") {
    send({
      jsonrpc: "2.0",
      method: "session/update",
      params: {
        sessionId: msg.params.sessionId,
        update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "codex-stub completed the task" } },
      },
    });
    send({ jsonrpc: "2.0", id: msg.id, result: { stopReason: "end_turn", usage: { inputTokens: 3, outputTokens: 5 } } });
  } else if (msg.id !== undefined) {
    send({ jsonrpc: "2.0", id: msg.id, result: null });
  }
});
`;

describe("codex adapter against a real ACP subprocess", () => {
  it("opens a session and completes an attempt through the spawned codex-acp command", async () => {
    const dir = mkdtempSync(join(tmpdir(), "codex-acp-stub-"));
    const script = join(dir, "codex-acp.js");
    writeFileSync(script, STUB_ACP_SERVER);
    chmodSync(script, 0o755);

    const adapter = new CodexRuntimeAdapter({
      command: `"${process.execPath}" "${script}"`,
    });
    try {
      await adapter.start();
      const binding = await adapter.openBinding({ sessionId: "omi-session-1", cwd: dir });
      expect(binding.adapterId).toBe("codex");
      expect(binding.adapterNativeSessionId).toBe("codex-stub-session-1");

      const events: OutboundMessageDraft[] = [];
      const context: AdapterAttemptContext = {
        sessionId: "omi-session-1",
        ownerId: "owner-1",
        requestId: "req-1",
        clientId: "client-1",
        runId: "run_1",
        attemptId: "attempt-1",
        toolCapabilityRef: "cap-1",
        binding,
        prompt: [{ type: "text", text: "Fix the failing unit tests" }],
        mode: "act",
      };
      const result = await adapter.executeAttempt(context, (event) => events.push(event), new AbortController().signal);

      expect(result.terminalStatus).toBe("succeeded");
      expect(result.text).toBe("codex-stub completed the task");
      expect(result.adapterSessionId).toBe("codex-stub-session-1");
      expect(result.inputTokens).toBe(3);
      expect(result.outputTokens).toBe(5);
      expect(events.some((event) => event.type === "text_delta")).toBe(true);
    } finally {
      await adapter.stop();
    }
  }, 20_000);
});
