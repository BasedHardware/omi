import { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import type { ToolUseMessage, ToolResultMessage } from "./protocol.js";

// Current query mode — set by handleQuery before each query
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
    process.stderr.write(`[agent-bridge] Failed to write to stdout: ${err}\n`);
  }
}

/**
 * Request tool execution from Swift and wait for the result.
 * Sends a tool_use message to stdout, creates a promise, and waits.
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

// Define OMI tools using the Agent SDK's tool() helper

const executeSqlTool = tool(
  "execute_sql",
  `Run SQL on the local omi.db database.
Supports: SELECT, INSERT, UPDATE, DELETE.
SELECT auto-limits to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE blocked.
Use for: app usage stats, time queries, task management, aggregations, anything structured.`,
  { query: z.string().describe("SQL query to execute") },
  async ({ query }) => {
    // In ask mode, only allow SELECT queries
    if (currentMode === "ask") {
      const normalized = query.trim().toUpperCase();
      if (!normalized.startsWith("SELECT")) {
        return {
          content: [
            {
              type: "text" as const,
              text: "Blocked: Only SELECT queries are allowed in Ask mode. Switch to Act mode to run UPDATE/INSERT/DELETE.",
            },
          ],
        };
      }
    }
    const result = await requestSwiftTool("execute_sql", { query });
    return { content: [{ type: "text" as const, text: result }] };
  }
);

const semanticSearchTool = tool(
  "semantic_search",
  `Vector similarity search on screen history.
Use for: fuzzy conceptual queries where exact SQL keywords won't work.
e.g. "reading about machine learning", "working on design mockups"`,
  {
    query: z.string().describe("Natural language search query"),
    days: z
      .number()
      .optional()
      .default(7)
      .describe("Number of days to search back (default: 7)"),
    app_filter: z
      .string()
      .optional()
      .describe("Filter results to a specific app name"),
  },
  async ({ query, days, app_filter }) => {
    const input: Record<string, unknown> = { query, days };
    if (app_filter) input.app_filter = app_filter;
    const result = await requestSwiftTool("semantic_search", input);
    return { content: [{ type: "text" as const, text: result }] };
  }
);

/** Create the MCP server that exposes OMI tools to the Agent SDK */
export function createOmiMcpServer() {
  return createSdkMcpServer({
    name: "omi-tools",
    tools: [executeSqlTool, semanticSearchTool],
  });
}
