/**
 * Stdio-based MCP server for WhatsApp tools.
 * Tool calls are forwarded to Swift over the existing Omi bridge pipe.
 */

import { readFileSync } from "fs";
import { createConnection } from "net";
import { createInterface } from "readline";

const bridgePipePath = process.env.OMI_BRIDGE_PIPE;

const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

let callIdCounter = 0;
let pipeConnection: ReturnType<typeof createConnection> | null = null;
let pipeBuffer = "";

function nextCallId(): string {
  return `wa-${++callIdCounter}-${Date.now()}`;
}

function logErr(msg: string): void {
  process.stderr.write(`[wa-tools-stdio] ${msg}\n`);
}

function envProtocolVersion(): 2 | undefined {
  return process.env.OMI_PROTOCOL_VERSION === "2" ? 2 : undefined;
}

function activeOmiContext(): Record<string, unknown> {
  const envBase = {
    protocolVersion: envProtocolVersion(),
    adapterId: process.env.OMI_ADAPTER_ID,
  };
  if (process.env.OMI_CONTEXT_FILE) {
    try {
      const parsed = JSON.parse(readFileSync(process.env.OMI_CONTEXT_FILE, "utf8"));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return { ...envBase, ...parsed };
      }
      return { ...envBase, contextError: "OMI context file did not contain an object" };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logErr(`Failed to read OMI context file: ${message}`);
      return { ...envBase, contextError: message };
    }
  }
  return {
    ...envBase,
    ...(envProtocolVersion() === 2
      ? {}
      : {
          requestId: process.env.OMI_REQUEST_ID,
          clientId: process.env.OMI_CLIENT_ID,
          sessionId: process.env.OMI_SESSION_ID,
          runId: process.env.OMI_RUN_ID,
          attemptId: process.env.OMI_ATTEMPT_ID,
          adapterSessionId: process.env.OMI_ADAPTER_SESSION_ID,
          legacyAdapterSessionId: process.env.OMI_LEGACY_ADAPTER_SESSION_ID,
        }),
  };
}

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
      let newlineIdx;
      while ((newlineIdx = pipeBuffer.indexOf("\n")) >= 0) {
        const line = pipeBuffer.slice(0, newlineIdx);
        pipeBuffer = pipeBuffer.slice(newlineIdx + 1);
        if (!line.trim()) continue;
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
  if (context.protocolVersion === 2 && (context.contextError || !context.requestId || !context.clientId)) {
    return `Error: missing active Omi request context for v2 tool relay${context.contextError ? `: ${context.contextError}` : ""}`;
  }

  return new Promise<string>((resolve) => {
    pendingToolCalls.set(callId, { resolve });
    pipeConnection!.write(JSON.stringify({
      type: "tool_use",
      callId,
      name,
      input,
      ...context,
    }) + "\n");
  });
}

const TOOLS = [
  {
    name: "wa_list_chats",
    description: "List recent WhatsApp chats from the local synced WhatsApp store. Use this to resolve contact or group names to chat JIDs before reading or replying. Results may include contact names, WhatsApp names, phone numbers, and JIDs.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "Optional contact, group, phone, or chat-name search query." },
        limit: { type: "number" as const, description: "Maximum chats to return. Defaults to 50." },
        unread: { type: "boolean" as const, description: "Only include unread chats." },
        archived: { type: "boolean" as const, description: "Only include archived chats." },
        pinned: { type: "boolean" as const, description: "Only include pinned chats." },
      },
    },
  },
  {
    name: "wa_read_thread",
    description: "Read messages from a specific WhatsApp chat thread. Use after wa_list_chats when the user asks about a contact or wants a grounded reply.",
    inputSchema: {
      type: "object" as const,
      properties: {
        chat_jid: { type: "string" as const, description: "WhatsApp chat JID to read." },
        limit: { type: "number" as const, description: "Maximum messages to return. Defaults to 50." },
        after: { type: "string" as const, description: "Only messages after this RFC3339 timestamp or YYYY-MM-DD date." },
        before: { type: "string" as const, description: "Only messages before this RFC3339 timestamp or YYYY-MM-DD date." },
        sender_jid: { type: "string" as const, description: "Optional sender JID filter." },
        ascending: { type: "boolean" as const, description: "Return oldest messages first." },
        from_me: { type: "boolean" as const, description: "Only include messages sent by the user." },
        from_them: { type: "boolean" as const, description: "Only include messages received from others." },
      },
      required: ["chat_jid"],
    },
  },
  {
    name: "wa_search_messages",
    description: "Search synced WhatsApp messages. Use for finding contacts, context, commitments, or prior facts before answering personal questions.",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "Search query." },
        chat_jid: { type: "string" as const, description: "Optional chat JID filter." },
        sender_jid: { type: "string" as const, description: "Optional sender JID filter." },
        limit: { type: "number" as const, description: "Maximum messages to return. Defaults to 50." },
        after: { type: "string" as const, description: "Only messages after this RFC3339 timestamp or YYYY-MM-DD date." },
        before: { type: "string" as const, description: "Only messages before this RFC3339 timestamp or YYYY-MM-DD date." },
        message_type: { type: "string" as const, description: "Optional type filter: text, image, video, audio, or document." },
        has_media: { type: "boolean" as const, description: "Only include messages with media." },
      },
      required: ["query"],
    },
  },
  {
    name: "wa_send_message",
    description: "Send a WhatsApp text message. Use only after the user explicitly asks to send or reply. The recipient may be a JID, phone number, or exact contact/chat name; use wa_list_chats first when the name could be ambiguous.",
    inputSchema: {
      type: "object" as const,
      properties: {
        to: { type: "string" as const, description: "Recipient chat JID, phone number, or exact contact/chat name." },
        message: { type: "string" as const, description: "Text message to send." },
        reply_to: { type: "string" as const, description: "Optional message ID to quote/reply to." },
        reply_to_sender: { type: "string" as const, description: "Sender JID of the quoted message, required for unsynced group replies." },
        no_preview: { type: "boolean" as const, description: "Disable automatic link preview." },
        client_message_id: { type: "string" as const, description: "Optional idempotency key for deduping retries." },
        queue_for_approval: { type: "boolean" as const, description: "Queue instead of sending immediately. Phase 3 will use this for draft approval." },
      },
      required: ["to", "message"],
    },
  },
];

function send(msg: Record<string, unknown>): void {
  try {
    process.stdout.write(JSON.stringify(msg) + "\n");
  } catch (err) {
    logErr(`Failed to write to stdout: ${err}`);
  }
}

async function handleJsonRpc(body: Record<string, unknown>): Promise<void> {
  const id = body.id;
  const method = body.method as string;
  const params = (body.params ?? {}) as Record<string, unknown>;
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
            serverInfo: { name: "wa-tools", version: "1.0.0" },
          },
        });
      }
      break;
    case "notifications/initialized":
      break;
    case "tools/list":
      if (!isNotification) {
        send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
      }
      break;
    case "tools/call": {
      const toolName = params.name as string;
      const args = (params.arguments ?? {}) as Record<string, unknown>;
      if (!TOOLS.some((tool) => tool.name === toolName)) {
        if (!isNotification) {
          send({ jsonrpc: "2.0", id, error: { code: -32601, message: `Unknown tool: ${toolName}` } });
        }
        return;
      }
      const result = await requestSwiftTool(toolName, args);
      if (!isNotification) {
        send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text: result }] } });
      }
      break;
    }
    default:
      if (!isNotification) {
        send({ jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } });
      }
  }
}

async function main(): Promise<void> {
  await connectToPipe();

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

  logErr("wa-tools stdio MCP server started");
}

main().catch((err) => {
  logErr(`Fatal: ${err}`);
  process.exit(1);
});
