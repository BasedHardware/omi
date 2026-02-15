import { query } from "@anthropic-ai/claude-agent-sdk";
import { createOmiMcpServer, resolveToolCall, setQueryMode } from "./omi-tools.js";
import type {
  InboundMessage,
  OutboundMessage,
  QueryMessage,
} from "./protocol.js";
import { createInterface } from "readline";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

// Resolve path to bundled @playwright/mcp CLI
const __dirname = dirname(fileURLToPath(import.meta.url));
const playwrightCli = join(__dirname, "..", "node_modules", "@playwright", "mcp", "cli.js");

// --- Helpers ---

function send(msg: OutboundMessage): void {
  process.stdout.write(JSON.stringify(msg) + "\n");
}

function logErr(msg: string): void {
  process.stderr.write(`[agent-bridge] ${msg}\n`);
}

// --- MCP Server (OMI tools) ---

const omiServer = createOmiMcpServer();

// --- Active query state ---

let activeAbort: AbortController | null = null;
// True when the user explicitly requested an interrupt (stop button).
// Distinguishes user-initiated stops (send partial result) from
// query-superseded aborts (no result, new query takes over).
let interruptRequested = false;

// --- Handle a query from Swift ---

async function handleQuery(msg: QueryMessage): Promise<void> {
  // Cancel any prior query
  if (activeAbort) {
    activeAbort.abort();
    activeAbort = null;
  }

  const abortController = new AbortController();
  activeAbort = abortController;
  interruptRequested = false;

  // Declare outside try so catch block can send partial result on interrupt
  let sessionId = "";
  let fullText = "";
  let costUsd = 0;

  // Track pending tool calls so we can mark them completed on interrupt
  const pendingTools: string[] = [];

  try {
    // Each query is standalone — conversation history comes via systemPrompt
    // This ensures cross-platform sync (mobile messages are included in context)
    const mode = msg.mode ?? "act";
    const isAskMode = mode === "ask";
    setQueryMode(mode);
    logErr(`Query mode: ${mode}`);

    // In ask mode, only allow read-only tools (no Write, Edit, Bash)
    const allowedTools = isAskMode
      ? ["Read", "Glob", "Grep", "WebSearch", "WebFetch"]
      : ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"];

    // In ask mode, exclude playwright (no browser actions)
    const mcpServers: Record<string, unknown> = {
      "omi-tools": omiServer,
    };
    if (!isAskMode) {
      mcpServers["playwright"] = {
        command: process.execPath,
        args: [playwrightCli],
      };
    }

    const options: Record<string, unknown> = {
      model: "claude-opus-4-6",
      abortController,
      systemPrompt: msg.systemPrompt,
      allowedTools,
      permissionMode: "bypassPermissions",
      allowDangerouslySkipPermissions: true,
      maxTurns: 15,
      cwd: msg.cwd || process.env.HOME || "/",
      mcpServers,
      includePartialMessages: true,
    };

    // Track tool_use block index → {id, name, inputChunks} for accumulating input_json_delta
    const blockTools: Map<number, { id: string; name: string; inputChunks: string[] }> = new Map();
    // Track toolUseId → name for correlating results
    const toolIdToName: Map<string, string> = new Map();

    const q = query({ prompt: msg.prompt, options: options as any });

    for await (const message of q) {
      if (abortController.signal.aborted) break;

      switch (message.type) {
        case "system":
          if ("session_id" in message) {
            sessionId = message.session_id as string;
            send({ type: "init", sessionId });
          }
          break;

        case "stream_event": {
          const event = (message as any).event;

          // Detect tool_use start from streaming (before assistant message)
          if (
            event?.type === "content_block_start" &&
            event.content_block?.type === "tool_use"
          ) {
            const name = event.content_block.name as string;
            const toolUseId = event.content_block.id as string | undefined;
            const blockIndex = event.index as number | undefined;
            pendingTools.push(name);
            if (toolUseId) {
              toolIdToName.set(toolUseId, name);
            }
            if (blockIndex !== undefined && toolUseId) {
              blockTools.set(blockIndex, { id: toolUseId, name, inputChunks: [] });
            }
            send({ type: "tool_activity", name, status: "started", toolUseId });
          }

          // Accumulate input_json_delta for tool blocks
          if (
            event?.type === "content_block_delta" &&
            event.delta?.type === "input_json_delta"
          ) {
            const blockIndex = event.index as number | undefined;
            const partial = event.delta.partial_json as string | undefined;
            if (blockIndex !== undefined && partial) {
              const block = blockTools.get(blockIndex);
              if (block) {
                block.inputChunks.push(partial);
              }
            }
          }

          // On content_block_stop, send complete input for tool blocks
          if (event?.type === "content_block_stop") {
            const blockIndex = event.index as number | undefined;
            if (blockIndex !== undefined) {
              const block = blockTools.get(blockIndex);
              if (block && block.inputChunks.length > 0) {
                try {
                  const fullJson = block.inputChunks.join("");
                  const input = JSON.parse(fullJson) as Record<string, unknown>;
                  send({
                    type: "tool_activity",
                    name: block.name,
                    status: "started",
                    toolUseId: block.id,
                    input,
                  });
                } catch {
                  // Failed to parse accumulated input — skip
                }
              }
              blockTools.delete(blockIndex);
            }
          }

          // Thinking block start
          if (
            event?.type === "content_block_start" &&
            event.content_block?.type === "thinking"
          ) {
            // Thinking block started — deltas will follow
          }

          // Thinking deltas
          if (
            event?.type === "content_block_delta" &&
            event.delta?.type === "thinking_delta"
          ) {
            const thinkingText = event.delta.thinking as string;
            if (thinkingText) {
              send({ type: "thinking_delta", text: thinkingText });
            }
          }

          // Text deltas — if tools were pending, they're now complete
          if (
            event?.type === "content_block_delta" &&
            event.delta?.type === "text_delta"
          ) {
            if (pendingTools.length > 0) {
              for (const name of pendingTools) {
                send({ type: "tool_activity", name, status: "completed" });
              }
              pendingTools.length = 0;
            }
            const text = event.delta.text as string;
            fullText += text;
            send({ type: "text_delta", text });
          }
          break;
        }

        case "assistant": {
          // Complete assistant message — extract text and tool_use blocks
          const content = (message as any).message?.content;
          if (Array.isArray(content)) {
            for (const block of content) {
              if (block.type === "text" && typeof block.text === "string") {
                // Only use if we didn't get streaming deltas
                if (!fullText) {
                  fullText = block.text;
                  send({ type: "text_delta", text: block.text });
                }
              }
              // Extract tool_use blocks with complete input (fallback if streaming didn't capture it)
              if (block.type === "tool_use" && block.id && block.name) {
                const toolUseId = block.id as string;
                const name = block.name as string;
                const input = block.input as Record<string, unknown> | undefined;
                toolIdToName.set(toolUseId, name);
                if (input && Object.keys(input).length > 0) {
                  send({ type: "tool_activity", name, status: "started", toolUseId, input });
                }
              }
            }
          }
          break;
        }

        case "user": {
          // User messages contain tool_result blocks — forward as tool_result_display
          const content = (message as any).message?.content;
          if (Array.isArray(content)) {
            for (const block of content) {
              if (block.type === "tool_result" && block.tool_use_id) {
                const toolUseId = block.tool_use_id as string;
                const name = toolIdToName.get(toolUseId) ?? "unknown";
                // Extract text output — may be string or array of content blocks
                let output = "";
                if (typeof block.content === "string") {
                  output = block.content;
                } else if (Array.isArray(block.content)) {
                  output = block.content
                    .filter((c: any) => c.type === "text")
                    .map((c: any) => c.text)
                    .join("\n");
                }
                // Truncate to ~2000 chars for display
                if (output.length > 2000) {
                  output = output.slice(0, 2000) + "\n... (truncated)";
                }
                if (output) {
                  send({ type: "tool_result_display", toolUseId, name, output });
                }
                // Mark tool as completed
                send({ type: "tool_activity", name, status: "completed", toolUseId });
              }
            }
          }
          break;
        }

        case "result": {
          // Mark any remaining pending tools as completed
          for (const name of pendingTools) {
            send({ type: "tool_activity", name, status: "completed" });
          }
          pendingTools.length = 0;

          const result = message as any;
          if (result.subtype === "success") {
            costUsd = result.total_cost_usd || 0;
            // Use result.result as final text if we didn't capture anything
            if (!fullText && result.result) {
              fullText = result.result;
            }
          } else {
            // Error result
            const errors = result.errors || [];
            send({
              type: "error",
              message: `Agent error (${result.subtype}): ${errors.join(", ")}`,
            });
          }
          break;
        }
      }
    }

    send({ type: "result", text: fullText, sessionId, costUsd });
  } catch (err: unknown) {
    if (abortController.signal.aborted) {
      if (interruptRequested) {
        // Mark any remaining pending tools as completed before sending partial result
        for (const name of pendingTools) {
          send({ type: "tool_activity", name, status: "completed" });
        }
        pendingTools.length = 0;
        // User-initiated stop: send partial result so Swift can display it
        logErr(`Query interrupted by user, sending partial result (${fullText.length} chars)`);
        send({ type: "result", text: fullText, sessionId, costUsd });
      } else {
        // Superseded by a new query — don't send result
        logErr("Query aborted (superseded by new query)");
      }
      return;
    }
    const errMsg = err instanceof Error ? err.message : String(err);
    logErr(`Query error: ${errMsg}`);
    send({ type: "error", message: errMsg });
  } finally {
    if (activeAbort === abortController) {
      activeAbort = null;
    }
  }
}

// Prevent unhandled rejections from crashing the bridge process
process.on("unhandledRejection", (reason) => {
  logErr(`Unhandled rejection: ${reason}`);
});

// --- Main: read JSON lines from stdin ---

const rl = createInterface({ input: process.stdin, terminal: false });

rl.on("line", (line: string) => {
  if (!line.trim()) return;

  let msg: InboundMessage;
  try {
    msg = JSON.parse(line) as InboundMessage;
  } catch {
    logErr(`Invalid JSON: ${line}`);
    return;
  }

  switch (msg.type) {
    case "query":
      handleQuery(msg).catch((err) => {
        logErr(`Unhandled query error: ${err}`);
        send({ type: "error", message: String(err) });
      });
      break;

    case "tool_result":
      resolveToolCall(msg);
      break;

    case "interrupt":
      logErr("Interrupt requested by user");
      interruptRequested = true;
      if (activeAbort) activeAbort.abort();
      break;

    case "stop":
      logErr("Received stop signal, exiting");
      if (activeAbort) activeAbort.abort();
      process.exit(0);
      break;

    default:
      logErr(`Unknown message type: ${(msg as any).type}`);
  }
});

rl.on("close", () => {
  logErr("stdin closed, exiting");
  if (activeAbort) activeAbort.abort();
  process.exit(0);
});

// Signal readiness
send({ type: "init", sessionId: "" });
logErr("Bridge started, waiting for queries...");
