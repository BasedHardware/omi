/**
 * HTTP-based MCP server that exposes omi tools (execute_sql, semantic_search)
 * to the ACP agent. Tool calls are forwarded to Swift via stdout using the
 * same protocol as agent-bridge.
 *
 * This replaces the Agent SDK's createSdkMcpServer() with a standalone HTTP
 * server that ACP can connect to via its HTTP MCP transport.
 */

import { createServer, type IncomingMessage, type ServerResponse } from "http";
import type { ToolUseMessage, ToolResultMessage } from "./protocol.js";

// Current query mode — set before each query
let currentMode: "ask" | "act" = "act";

export function setQueryMode(mode: "ask" | "act"): void {
  currentMode = mode;
}

// Pending tool call promises — resolved when Swift sends back results
const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

let callIdCounter = 0;

function nextCallId(): string {
  return `omi-${++callIdCounter}-${Date.now()}`;
}

/** Send a JSON line to stdout (back to Swift) */
function sendToSwift(msg: ToolUseMessage): void {
  try {
    process.stdout.write(JSON.stringify(msg) + "\n");
  } catch (err) {
    process.stderr.write(`[acp-bridge] Failed to write to stdout: ${err}\n`);
  }
}

/**
 * Request tool execution from Swift and wait for the result.
 */
async function requestSwiftTool(
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  const callId = nextCallId();

  return new Promise<string>((resolve) => {
    pendingToolCalls.set(callId, { resolve });
    sendToSwift({ type: "tool_use", callId, name, input });
  });
}

/** Resolve a pending tool call with a result from Swift */
export function resolveToolCall(msg: ToolResultMessage): void {
  const pending = pendingToolCalls.get(msg.callId);
  if (pending) {
    pending.resolve(msg.result);
    pendingToolCalls.delete(msg.callId);
  } else {
    process.stderr.write(
      `Warning: no pending tool call for callId=${msg.callId}\n`
    );
  }
}

// MCP tool definitions
const TOOLS = [
  {
    name: "execute_sql",
    description: `Run SQL on the local omi.db database.
Supports: SELECT, INSERT, UPDATE, DELETE.
SELECT auto-limits to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE blocked.
Use for: app usage stats, time queries, task management, aggregations, anything structured.`,
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "SQL query to execute" },
      },
      required: ["query"],
    },
  },
  {
    name: "semantic_search",
    description: `Vector similarity search on screen history.
Use for: fuzzy conceptual queries where exact SQL keywords won't work.
e.g. "reading about machine learning", "working on design mockups"`,
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Natural language search query",
        },
        days: {
          type: "number",
          description: "Number of days to search back (default: 7)",
        },
        app_filter: {
          type: "string",
          description: "Filter results to a specific app name",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "complete_task",
    description: `Toggle a task's completion status. Syncs to backend (Firestore).
Use after finding the task with execute_sql. Pass the backendId from the action_items table.`,
    inputSchema: {
      type: "object",
      properties: {
        task_id: {
          type: "string",
          description: "The backendId of the task from action_items table",
        },
      },
      required: ["task_id"],
    },
  },
  {
    name: "delete_task",
    description: `Delete a task permanently. Syncs to backend (Firestore).
Use after finding the task with execute_sql. Pass the backendId from the action_items table.`,
    inputSchema: {
      type: "object",
      properties: {
        task_id: {
          type: "string",
          description: "The backendId of the task from action_items table",
        },
      },
      required: ["task_id"],
    },
  },
];

/** Handle a JSON-RPC request */
async function handleJsonRpc(
  body: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const id = body.id;
  const method = body.method as string;
  const params = (body.params ?? {}) as Record<string, unknown>;

  switch (method) {
    case "initialize":
      return {
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: "omi-tools", version: "1.0.0" },
        },
      };

    case "notifications/initialized":
      // No response needed for notifications
      return { jsonrpc: "2.0", id, result: {} };

    case "tools/list":
      return {
        jsonrpc: "2.0",
        id,
        result: { tools: TOOLS },
      };

    case "tools/call": {
      const toolName = params.name as string;
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (toolName === "execute_sql") {
        const query = args.query as string;
        // In ask mode, only allow SELECT queries
        if (currentMode === "ask") {
          const normalized = query.trim().toUpperCase();
          if (!normalized.startsWith("SELECT")) {
            return {
              jsonrpc: "2.0",
              id,
              result: {
                content: [
                  {
                    type: "text",
                    text: "Blocked: Only SELECT queries are allowed in Ask mode. Switch to Act mode to run UPDATE/INSERT/DELETE.",
                  },
                ],
              },
            };
          }
        }
        const result = await requestSwiftTool("execute_sql", { query });
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: result }] },
        };
      }

      if (toolName === "semantic_search") {
        const input: Record<string, unknown> = {
          query: args.query,
          days: args.days ?? 7,
        };
        if (args.app_filter) input.app_filter = args.app_filter;
        const result = await requestSwiftTool("semantic_search", input);
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: result }] },
        };
      }

      if (toolName === "complete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("complete_task", { task_id: taskId });
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: result }] },
        };
      }

      if (toolName === "delete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("delete_task", { task_id: taskId });
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: result }] },
        };
      }

      return {
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `Unknown tool: ${toolName}` },
      };
    }

    default:
      return {
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `Method not found: ${method}` },
      };
  }
}

/** Read full request body */
function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk: Buffer) => {
      data += chunk.toString();
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

/**
 * Start the HTTP MCP server on a random localhost port.
 * Returns the URL to connect to.
 */
export async function startOmiToolsServer(): Promise<string> {
  return new Promise((resolve, reject) => {
    const server = createServer(
      async (req: IncomingMessage, res: ServerResponse) => {
        // Handle MCP Streamable HTTP transport
        if (req.method === "POST") {
          try {
            const body = await readBody(req);
            const parsed = JSON.parse(body) as Record<string, unknown>;
            const result = await handleJsonRpc(parsed);
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify(result));
          } catch (err) {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(
              JSON.stringify({
                jsonrpc: "2.0",
                error: { code: -32700, message: "Parse error" },
              })
            );
          }
        } else if (req.method === "GET") {
          // Health check / SSE endpoint (not used but keep for compatibility)
          res.writeHead(200, { "Content-Type": "text/plain" });
          res.end("omi-tools MCP server");
        } else {
          res.writeHead(405);
          res.end();
        }
      }
    );

    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (addr && typeof addr === "object") {
        const url = `http://127.0.0.1:${addr.port}/`;
        process.stderr.write(`[acp-bridge] omi-tools HTTP MCP server on ${url}\n`);
        resolve(url);
      } else {
        reject(new Error("Failed to get server address"));
      }
    });

    server.on("error", reject);
  });
}
