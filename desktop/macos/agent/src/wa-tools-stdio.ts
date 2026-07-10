/**
 * Stdio-based MCP server for WhatsApp tools.
 * Tool calls are forwarded to Swift over the existing Omi bridge pipe.
 */

import { readFileSync } from "fs";
import { createConnection } from "net";
import { createInterface } from "readline";
import { createHash } from "crypto";
import { fileURLToPath } from "url";
import { resolve } from "path";

const bridgePipePath = process.env.OMI_BRIDGE_PIPE;

const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void; reject: (error: Error) => void; timeout: NodeJS.Timeout }
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
    requestId: process.env.OMI_REQUEST_ID,
    clientId: process.env.OMI_CLIENT_ID,
    sessionId: process.env.OMI_SESSION_ID,
    runId: process.env.OMI_RUN_ID,
    attemptId: process.env.OMI_ATTEMPT_ID,
    adapterSessionId: process.env.OMI_ADAPTER_SESSION_ID,
    legacyAdapterSessionId: process.env.OMI_LEGACY_ADAPTER_SESSION_ID,
  };
}

export function stableJSONStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJSONStringify).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([lhs], [rhs]) => (lhs < rhs ? -1 : lhs > rhs ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${stableJSONStringify(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function requestScopeValue(value: unknown): string | undefined {
  if (typeof value === "string") {
    return value.trim() || undefined;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return undefined;
}

export function withIdempotencyKey(
  name: string,
  input: Record<string, unknown>,
  context: Record<string, unknown>,
  requestScope: unknown
): Record<string, unknown> {
  if (name !== "wa_send_message" || typeof input.client_message_id === "string" || typeof input.dedupe_id === "string") {
    return input;
  }
  const mcpRequestId = requestScopeValue(requestScope);
  if (!mcpRequestId) {
    return input;
  }
  const scope = {
    mcpRequestId,
    requestId: context.requestId,
    clientId: context.clientId,
    sessionId: context.sessionId,
    runId: context.runId,
    attemptId: context.attemptId,
  };
  const hash = createHash("sha256")
    .update(stableJSONStringify({ scope, input }))
    .digest("hex")
    .slice(0, 32);
  return { ...input, client_message_id: `wa-tool:${hash}` };
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
              clearTimeout(pending.timeout);
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
      rejectPendingToolCalls(err);
      reject(err);
    });
    pipeConnection.on("close", () => {
      rejectPendingToolCalls(new Error("bridge pipe closed"));
      pipeConnection = null;
    });
  });
}

async function requestSwiftTool(
  name: string,
  input: Record<string, unknown>,
  requestScope: unknown
): Promise<string> {
  const callId = nextCallId();

  if (!pipeConnection) {
    return "Error: not connected to bridge";
  }

  const context = activeOmiContext();
  if (context.protocolVersion === 2 && (context.contextError || !context.requestId || !context.clientId)) {
    return `Error: missing active Omi request context for v2 tool relay${context.contextError ? `: ${context.contextError}` : ""}`;
  }

  return new Promise<string>((resolve, reject) => {
    const timeout = setTimeout(() => {
      pendingToolCalls.delete(callId);
      sendToolCancel(callId, context);
      reject(new Error(`Timed out waiting for Swift tool result for ${name}`));
    }, 30_000);
    pendingToolCalls.set(callId, { resolve, reject, timeout });
    pipeConnection!.write(JSON.stringify({
      type: "tool_use",
      callId,
      name,
      input: withIdempotencyKey(name, input, context, requestScope),
      ...context,
    }) + "\n");
  });
}

function sendToolCancel(callId: string, context: Record<string, unknown>): void {
  if (!pipeConnection) return;
  pipeConnection.write(JSON.stringify({
    type: "tool_cancel",
    callId,
    ...context,
  }) + "\n");
}

function rejectPendingToolCalls(error: Error): void {
  for (const [callId, pending] of pendingToolCalls) {
    clearTimeout(pending.timeout);
    pending.reject(error);
    pendingToolCalls.delete(callId);
  }
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
      try {
        const result = await requestSwiftTool(toolName, args, id);
        if (!isNotification) {
          send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text: result }] } });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!isNotification) {
          send({ jsonrpc: "2.0", id, error: { code: -32000, message } });
        }
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

const modulePath = fileURLToPath(import.meta.url);
const isDirectRun =
  typeof process.argv[1] === "string" &&
  resolve(process.argv[1]) === resolve(modulePath);

if (isDirectRun) {
  main().catch((err) => {
    logErr(`Fatal: ${err}`);
    process.exit(1);
  });
}
