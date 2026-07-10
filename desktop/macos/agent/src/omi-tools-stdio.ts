/**
 * Stdio-based MCP server for omi tools (execute_sql, semantic_search).
 * This script is spawned as a subprocess by the ACP agent.
 * It reads JSON-RPC requests from stdin and writes responses to stdout.
 *
 * Tool calls are forwarded to the parent agent process via a named pipe
 * (passed as OMI_BRIDGE_PIPE env var), which then forwards them to Swift.
 */

import { createInterface } from "readline";
import { createConnection } from "net";
import { readFileSync, writeFileSync } from "fs";
import { isAgentControlToolName } from "./runtime/control-tools.js";
import { loadSkillInstructions } from "./runtime/node-tools.js";
import {
  buildToolAvailabilitySnapshot,
  mcpToolDefinitionsForAdapter,
  normalizeOmiToolName,
  toolManifestEntry,
  toolsForAdapter,
} from "./runtime/omi-tool-manifest.js";
import { PROTOCOL_VERSION } from "./protocol.js";

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

function activeOmiContext(): Record<string, unknown> {
  const envBase = {
    protocolVersion: PROTOCOL_VERSION,
    adapterId: process.env.OMI_ADAPTER_ID,
  };
  if (process.env.OMI_CONTEXT_FILE) {
    try {
      const parsed = JSON.parse(readFileSync(process.env.OMI_CONTEXT_FILE, "utf8"));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return {
          ...envBase,
          ...parsed,
        };
      }
      return {
        ...envBase,
        contextError: "OMI context file did not contain an object",
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logErr(`Failed to read OMI context file: ${message}`);
      return {
        ...envBase,
        contextError: message,
      };
    }
  }
  return {
    ...envBase,
    requestId: process.env.OMI_REQUEST_ID,
    clientId: process.env.OMI_CLIENT_ID,
    sessionId: process.env.OMI_SESSION_ID,
    runId: process.env.OMI_RUN_ID,
    attemptId: process.env.OMI_ATTEMPT_ID,
    surfaceKind: process.env.OMI_SURFACE_KIND,
    externalRefKind: process.env.OMI_EXTERNAL_REF_KIND,
    externalRefId: process.env.OMI_EXTERNAL_REF_ID,
    adapterSessionId: process.env.OMI_ADAPTER_SESSION_ID,
  };
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

  const context = activeOmiContext();
  if (context.contextError || !context.requestId || !context.clientId) {
    return `Error: missing active Omi request context for tool relay${context.contextError ? `: ${context.contextError}` : ""}`;
  }

  return new Promise<string>((resolve) => {
    pendingToolCalls.set(callId, { resolve });
    const msg = JSON.stringify({
      type: "tool_use",
      callId,
      name,
      input,
      ...context,
    });
    pipeConnection!.write(msg + "\n");
  });
}

// --- MCP tool definitions ---

const isOnboarding = process.env.OMI_ONBOARDING === "true";
const hasScreenContext = process.env.OMI_SCREEN_CONTEXT === "true";

// Tool order is owned by the canonical manifest projection.
const ADVERTISED_TOOLS = toolsForAdapter("omi-tools-stdio", { onboarding: isOnboarding, screenContext: hasScreenContext });
const ADVERTISED_CANONICAL_TOOL_NAMES = new Set(ADVERTISED_TOOLS.map((tool) => tool.name));
// Filter tools based on session type: onboarding sessions get onboarding tools,
// regular sessions exclude them
const TOOLS = mcpToolDefinitionsForAdapter("omi-tools-stdio", { onboarding: isOnboarding, screenContext: hasScreenContext });

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
      const normalizedTool = normalizeOmiToolName("omi-tools-stdio", params.name as string);
      const toolName = normalizedTool.canonicalName;
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (!ADVERTISED_CANONICAL_TOOL_NAMES.has(toolName)) {
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            error: { code: -32601, message: `Unknown tool: ${params.name as string}` },
          });
        }
        return;
      }

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
      } else if (toolName === "get_daily_recap") {
        const daysAgo = (args.days_ago as number) ?? 1;
        const result = await requestSwiftTool("get_daily_recap", { days_ago: daysAgo });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "search_tasks") {
        const input: Record<string, unknown> = { query: args.query };
        if (args.include_completed) input.include_completed = args.include_completed;
        const result = await requestSwiftTool("search_tasks", input);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "complete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("complete_task", { task_id: taskId });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "delete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("delete_task", { task_id: taskId });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "load_skill") {
        const name = (args.name as string || "").trim();
        const content = await loadSkillInstructions(name);

        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: {
              content: [{
                type: "text",
                text: content,
              }],
            },
          });
        }
      } else if (isAgentControlToolName(toolName)) {
        // Runtime control tools are handled by the Node parent/kernel. They
        // still travel over the relay so MCP clients use the same tool path.
        const result = await requestSwiftTool(toolName, args);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (
        toolName === "check_permission_status" ||
        toolName === "request_permission" ||
        toolName === "scan_files" ||
        toolName === "set_user_preferences" ||
        toolName === "ask_followup" ||
        toolName === "complete_onboarding" ||
        toolName === "save_knowledge_graph"
      ) {
        // Onboarding tools — forward directly to Swift
        const result = await requestSwiftTool(toolName, args);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (
        toolName === "get_conversations" ||
        toolName === "search_conversations" ||
        toolName === "get_memories" ||
        toolName === "search_memories" ||
        toolName === "get_action_items" ||
        toolName === "create_action_item" ||
        toolName === "update_action_item" ||
        toolName === "check_calendar_availability"
      ) {
        // Backend RAG tools — forward to Swift which calls Python backend
        const result = await requestSwiftTool(toolName, args);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolManifestEntry(toolName)?.executor.kind === "swiftTool") {
        const entry = toolManifestEntry(toolName)!;
        const result = await requestSwiftTool(entry.executor.executorName ?? entry.name, args);
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

  const snapshot = buildToolAvailabilitySnapshot("omi-tools-stdio", { onboarding: isOnboarding });
  if (process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH) {
    try {
      writeFileSync(process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH, `${JSON.stringify(snapshot, null, 2)}\n`);
    } catch (err) {
      logErr(`Failed to write tool availability snapshot: ${err instanceof Error ? err.message : err}`);
    }
  }
  logErr(
    `omi-tools stdio MCP server started adapter=omi-tools-stdio advertisedToolCount=${snapshot.advertisedToolCount} advertisedTools=${snapshot.advertisedToolNames.join(",")}`,
  );
}

main().catch((err) => {
  logErr(`Fatal: ${err}`);
  process.exit(1);
});
