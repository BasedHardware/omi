/**
 * Stdio-based MCP server for omi tools (execute_sql, semantic_search).
 * This script is spawned as a subprocess by the ACP agent.
 * It reads JSON-RPC requests from stdin and writes responses to stdout.
 *
 * Tool calls are forwarded to the parent acp-bridge process via a named pipe
 * (passed as OMI_BRIDGE_PIPE env var), which then forwards them to Swift.
 */

import { createInterface } from "readline";
import { createConnection } from "net";

// Current query mode
let currentMode: "ask" | "act" = process.env.OMI_QUERY_MODE === "ask" ? "ask" : "act";

// Connection to parent bridge for tool forwarding
const bridgePipePath = process.env.OMI_BRIDGE_PIPE;

// Pending tool calls — resolved when parent sends back results via pipe
const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

let callIdCounter = 0;

function nextCallId(): string {
  return `omi-${++callIdCounter}-${Date.now()}`;
}

function logErr(msg: string): void {
  process.stderr.write(`[omi-tools-stdio] ${msg}\n`);
}

// --- Communication with parent bridge ---

let pipeConnection: ReturnType<typeof createConnection> | null = null;
let pipeBuffer = "";

function connectToPipe(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!bridgePipePath) {
      logErr("No OMI_BRIDGE_PIPE set, tool calls will fail");
      resolve();
      return;
    }

    pipeConnection = createConnection(bridgePipePath, () => {
      logErr(`Connected to bridge pipe: ${bridgePipePath}`);
      resolve();
    });

    pipeConnection.on("data", (data: Buffer) => {
      pipeBuffer += data.toString();
      // Process complete lines
      let newlineIdx;
      while ((newlineIdx = pipeBuffer.indexOf("\n")) >= 0) {
        const line = pipeBuffer.slice(0, newlineIdx);
        pipeBuffer = pipeBuffer.slice(newlineIdx + 1);
        if (line.trim()) {
          try {
            const msg = JSON.parse(line) as {
              type: string;
              callId: string;
              result: string;
            };
            if (msg.type === "tool_result" && msg.callId) {
              const pending = pendingToolCalls.get(msg.callId);
              if (pending) {
                pending.resolve(msg.result);
                pendingToolCalls.delete(msg.callId);
              }
            }
          } catch {
            logErr(`Failed to parse pipe message: ${line.slice(0, 200)}`);
          }
        }
      }
    });

    pipeConnection.on("error", (err) => {
      logErr(`Pipe error: ${err.message}`);
      reject(err);
    });
  });
}

async function requestSwiftTool(
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  const callId = nextCallId();

  if (!pipeConnection) {
    return "Error: not connected to bridge";
  }

  return new Promise<string>((resolve) => {
    pendingToolCalls.set(callId, { resolve });
    const msg = JSON.stringify({ type: "tool_use", callId, name, input });
    pipeConnection!.write(msg + "\n");
  });
}

// --- MCP tool definitions ---

const TOOLS = [
  {
    name: "execute_sql",
    description: `Run SQL on the local omi.db database.
Supports: SELECT, INSERT, UPDATE, DELETE.
SELECT auto-limits to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE blocked.
Use for: app usage stats, time queries, task management, aggregations, anything structured.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "SQL query to execute" },
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
      type: "object" as const,
      properties: {
        query: {
          type: "string" as const,
          description: "Natural language search query",
        },
        days: {
          type: "number" as const,
          description: "Number of days to search back (default: 7)",
        },
        app_filter: {
          type: "string" as const,
          description: "Filter results to a specific app name",
        },
      },
      required: ["query"],
    },
  },
];

// --- JSON-RPC handling ---

function send(msg: Record<string, unknown>): void {
  try {
    process.stdout.write(JSON.stringify(msg) + "\n");
  } catch (err) {
    logErr(`Failed to write to stdout: ${err}`);
  }
}

async function handleJsonRpc(
  body: Record<string, unknown>
): Promise<void> {
  const id = body.id;
  const method = body.method as string;
  const params = (body.params ?? {}) as Record<string, unknown>;

  // Notifications (no id) don't get responses
  const isNotification = id === undefined || id === null;

  switch (method) {
    case "initialize":
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          result: {
            protocolVersion: "2024-11-05",
            capabilities: { tools: {} },
            serverInfo: { name: "omi-tools", version: "1.0.0" },
          },
        });
      }
      break;

    case "notifications/initialized":
      // No response needed
      break;

    case "tools/list":
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          result: { tools: TOOLS },
        });
      }
      break;

    case "tools/call": {
      const toolName = params.name as string;
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (toolName === "execute_sql") {
        const query = args.query as string;
        if (currentMode === "ask") {
          const normalized = query.trim().toUpperCase();
          if (!normalized.startsWith("SELECT")) {
            if (!isNotification) {
              send({
                jsonrpc: "2.0",
                id,
                result: {
                  content: [
                    {
                      type: "text",
                      text: "Blocked: Only SELECT queries are allowed in Ask mode.",
                    },
                  ],
                },
              });
            }
            return;
          }
        }
        const result = await requestSwiftTool("execute_sql", { query });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "semantic_search") {
        const input: Record<string, unknown> = {
          query: args.query,
          days: args.days ?? 7,
        };
        if (args.app_filter) input.app_filter = args.app_filter;
        const result = await requestSwiftTool("semantic_search", input);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Unknown tool: ${toolName}` },
        });
      }
      break;
    }

    default:
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Method not found: ${method}` },
        });
      }
  }
}

// --- Main ---

async function main(): Promise<void> {
  // Connect to parent bridge pipe for tool forwarding
  await connectToPipe();

  // Read JSON-RPC from stdin
  const rl = createInterface({ input: process.stdin, terminal: false });

  rl.on("line", (line: string) => {
    if (!line.trim()) return;
    try {
      const msg = JSON.parse(line) as Record<string, unknown>;
      handleJsonRpc(msg).catch((err) => {
        logErr(`Error handling request: ${err}`);
      });
    } catch {
      logErr(`Invalid JSON: ${line.slice(0, 200)}`);
    }
  });

  rl.on("close", () => {
    process.exit(0);
  });

  logErr("omi-tools stdio MCP server started");
}

main().catch((err) => {
  logErr(`Fatal: ${err}`);
  process.exit(1);
});
