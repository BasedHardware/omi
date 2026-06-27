import { createServer, createConnection, type Socket } from "node:net";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { unlinkSync } from "node:fs";
import { describe, expect, it, beforeEach, afterEach } from "vitest";

/**
 * Integration tests for the tool_result relay mechanism.
 *
 * The relay works as follows:
 * 1. pi-mono-extension connects to a Unix socket and sends {"type":"tool_use", callId, name, input}
 * 2. agent receives it, forwards to Swift via stdout, creates a pending promise
 * 3. Swift executes the tool and sends {"type":"tool_result", callId, clientId, requestId, result} back via stdin
 * 4. agent's resolveToolCall() resolves the pending promise, writing back to the socket client
 *
 * These tests verify that the relay mechanism correctly routes tool_result
 * messages back to the original socket client for ALL 13 Omi tools.
 */

// Minimal implementation of the relay components extracted from index.ts
const pendingToolCalls = new Map<string, { resolve: (result: string) => void }>();
let capturedStdoutMessages: any[] = [];

function toolCallPendingKey(input: { callId: string; clientId?: string; requestId?: string }): string {
  return input.clientId && input.requestId
    ? `scoped\0${input.clientId}\0${input.requestId}\0${input.callId}`
    : `legacy\0${input.callId}`;
}

function resolveToolCall(msg: { callId: string; result: string; clientId?: string; requestId?: string }): void {
  const key = toolCallPendingKey(msg);
  const pending = pendingToolCalls.get(key);
  if (pending) {
    pending.resolve(msg.result);
    pendingToolCalls.delete(key);
  }
}

function simulateSend(msg: any): void {
  capturedStdoutMessages.push(msg);
}

describe("Tool relay: resolveToolCall routing", () => {
  beforeEach(() => {
    pendingToolCalls.clear();
    capturedStdoutMessages = [];
  });

  it("routes tool_result to pending promise and removes from map", () => {
    let resolved = "";
    pendingToolCalls.set(toolCallPendingKey({ callId: "call-1", clientId: "client-1", requestId: "req-1" }), {
      resolve: (r) => { resolved = r; },
    });

    resolveToolCall({ callId: "call-1", clientId: "client-1", requestId: "req-1", result: "success data" });

    expect(resolved).toBe("success data");
    expect(pendingToolCalls.has(toolCallPendingKey({ callId: "call-1", clientId: "client-1", requestId: "req-1" }))).toBe(false);
  });

  it("ignores tool_result for unknown callId (no crash)", () => {
    // Should not throw
    resolveToolCall({ callId: "unknown-id", result: "data" });
    expect(pendingToolCalls.size).toBe(0);
  });

  it("handles multiple concurrent tool calls", () => {
    const results: Record<string, string> = {};

    pendingToolCalls.set(toolCallPendingKey({ callId: "call-A", clientId: "client-1", requestId: "req-A" }), { resolve: (r) => { results["A"] = r; } });
    pendingToolCalls.set(toolCallPendingKey({ callId: "call-B", clientId: "client-1", requestId: "req-B" }), { resolve: (r) => { results["B"] = r; } });
    pendingToolCalls.set(toolCallPendingKey({ callId: "call-C", clientId: "client-2", requestId: "req-C" }), { resolve: (r) => { results["C"] = r; } });

    // Resolve out of order
    resolveToolCall({ callId: "call-B", clientId: "client-1", requestId: "req-B", result: "result-B" });
    resolveToolCall({ callId: "call-A", clientId: "client-1", requestId: "req-A", result: "result-A" });
    resolveToolCall({ callId: "call-C", clientId: "client-2", requestId: "req-C", result: "result-C" });

    expect(results).toEqual({ A: "result-A", B: "result-B", C: "result-C" });
    expect(pendingToolCalls.size).toBe(0);
  });

  it("keeps reused call ids isolated by client and request", () => {
    const results: Record<string, string> = {};
    pendingToolCalls.set(toolCallPendingKey({ callId: "call-1", clientId: "client-A", requestId: "req-A" }), {
      resolve: (r) => { results["A"] = r; },
    });
    pendingToolCalls.set(toolCallPendingKey({ callId: "call-1", clientId: "client-B", requestId: "req-B" }), {
      resolve: (r) => { results["B"] = r; },
    });

    resolveToolCall({ callId: "call-1", clientId: "client-B", requestId: "req-B", result: "result-B" });

    expect(results).toEqual({ B: "result-B" });
    expect(pendingToolCalls.has(toolCallPendingKey({ callId: "call-1", clientId: "client-A", requestId: "req-A" }))).toBe(true);
  });
});

describe("Tool relay: Unix socket end-to-end", () => {
  let server: ReturnType<typeof createServer>;
  let sockPath: string;

  beforeEach(() => {
    pendingToolCalls.clear();
    capturedStdoutMessages = [];
    sockPath = join(tmpdir(), `test-omi-relay-${process.pid}-${Date.now()}.sock`);
    try { unlinkSync(sockPath); } catch { /* ignore */ }
  });

  afterEach(() => {
    return new Promise<void>((resolve) => {
      if (server) {
        server.close(() => {
          try { unlinkSync(sockPath); } catch { /* ignore */ }
          resolve();
        });
      } else {
        resolve();
      }
    });
  });

  /**
   * Creates a Unix socket server that mimics the agent relay:
   * - Receives tool_use from client
   * - Forwards to "Swift" (captured in capturedStdoutMessages)
   * - Creates pending promise that writes tool_result back to client
   */
  function startRelay(): Promise<void> {
    return new Promise((resolve) => {
      server = createServer((client: Socket) => {
        let buffer = "";
        client.on("data", (data: Buffer) => {
          buffer += data.toString();
          let idx;
          while ((idx = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 1);
            if (!line.trim()) continue;

            const msg = JSON.parse(line);
            if (msg.type === "tool_use") {
              // Forward to "Swift"
              simulateSend({
                type: "tool_use",
                callId: msg.callId,
                name: msg.name,
                input: msg.input,
                clientId: msg.clientId,
                requestId: msg.requestId,
              });

              // Create pending promise
              pendingToolCalls.set(toolCallPendingKey(msg), {
                resolve: (result: string) => {
                  client.write(
                    JSON.stringify({
                      type: "tool_result",
                      callId: msg.callId,
                      result,
                    }) + "\n"
                  );
                },
              });
            }
          }
        });
      });
      server.listen(sockPath, () => resolve());
    });
  }

  /** Connect a client and send a tool_use, return the tool_result */
  function sendToolUse(
    name: string,
    input: Record<string, unknown>,
    callId?: string,
    scope = { clientId: "client-1", requestId: `req-${name}` }
  ): Promise<{ callId: string; result: string }> {
    const id = callId ?? `call-${name}-${Date.now()}`;
    return new Promise((resolve, reject) => {
      const client = createConnection(sockPath, () => {
        client.write(
          JSON.stringify({ type: "tool_use", callId: id, name, input, ...scope }) + "\n"
        );
      });

      let buffer = "";
      client.on("data", (data: Buffer) => {
        buffer += data.toString();
        const idx = buffer.indexOf("\n");
        if (idx >= 0) {
          const response = JSON.parse(buffer.slice(0, idx));
          client.end();
          resolve(response);
        }
      });

      client.on("error", reject);

      // Simulate Swift responding after a short delay
      setTimeout(() => {
        const pending = capturedStdoutMessages.find(
          (m) => m.callId === id
        );
        if (pending) {
          resolveToolCall({
            callId: id,
            ...scope,
            result: `Mock result for ${name}`,
          });
        }
      }, 50);
    });
  }

  // Test all 14 Omi tools through the relay
  const OMI_TOOLS = [
    { name: "execute_sql", input: { query: "SELECT COUNT(*) FROM screenshots" } },
    { name: "semantic_search", input: { query: "terminal", days: 7 } },
    { name: "get_daily_recap", input: { days_ago: 1 } },
    { name: "search_tasks", input: { query: "test" } },
    { name: "complete_task", input: { task_id: "test-id-123" } },
    { name: "delete_task", input: { task_id: "test-id-456" } },
    { name: "get_conversations", input: { limit: 2 } },
    { name: "search_conversations", input: { query: "meeting" } },
    { name: "get_memories", input: { limit: 5 } },
    { name: "search_memories", input: { query: "work" } },
    { name: "get_action_items", input: { limit: 5 } },
    { name: "create_action_item", input: { description: "Test item" } },
    { name: "update_action_item", input: { action_item_id: "test-id", completed: true } },
    { name: "capture_screen", input: {} },
  ];

  for (const tool of OMI_TOOLS) {
    it(`relays tool_result for ${tool.name}`, async () => {
      await startRelay();

      const response = await sendToolUse(tool.name, tool.input);

      // Verify the relay forwarded tool_use to "Swift"
      const forwarded = capturedStdoutMessages.find((m) => m.name === tool.name);
      expect(forwarded).toBeDefined();
      expect(forwarded!.type).toBe("tool_use");
      expect(forwarded!.name).toBe(tool.name);
      expect(forwarded!.input).toEqual(tool.input);

      // Verify the tool_result was routed back to the client
      expect(response.type).toBe("tool_result");
      expect(response.result).toBe(`Mock result for ${tool.name}`);
    });
  }

  it("handles rapid sequential tool calls without mixing results", async () => {
    await startRelay();

    const promises = OMI_TOOLS.slice(0, 5).map((tool, i) =>
      sendToolUse(tool.name, tool.input, `rapid-${i}`)
    );

    const results = await Promise.all(promises);

    for (let i = 0; i < results.length; i++) {
      expect(results[i].type).toBe("tool_result");
      expect(results[i].callId).toBe(`rapid-${i}`);
      expect(results[i].result).toBe(`Mock result for ${OMI_TOOLS[i].name}`);
    }
  });
});
