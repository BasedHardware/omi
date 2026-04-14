/**
 * Chat service — Anthropic SDK with local tool execution.
 *
 * When the user has connected their Claude account (OAuth), chat uses the
 * Anthropic SDK directly with tools that query the local Rewind database
 * (screen captures, OCR text, app usage). This matches the Swift desktop
 * app's architecture.
 *
 * NOTE: `dangerouslyAllowBrowser: true` is required because Tauri WebViews
 * run in a browser context. The OAuth token is stored locally via
 * tauri-plugin-store and never leaves the device.
 */

import Anthropic from "@anthropic-ai/sdk";
import { searchScreenshots, getRecentScreenshots } from "@/services/rewind";
import type { ScreenshotRow } from "@/services/rewind";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ToolCallRecord {
  id: string;
  name: string;
  input: unknown;
  output?: string;
}

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

export const CHAT_TOOLS: Anthropic.Tool[] = [
  {
    name: "search_screenshots",
    description:
      "Search through the user's screen capture history using full-text search. Returns screenshots matching the query with OCR text, app name, and window title. Use this to find specific things the user saw on their screen.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: "Search query to find in screenshot OCR text, window titles, or app names",
        },
        limit: {
          type: "number",
          description: "Maximum results to return (default 10)",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "get_recent_activity",
    description:
      "Get the user's recent screen activity — what apps and windows they were using recently. Use this to answer questions about what the user was working on, their screen time, or to summarize their recent activity.",
    input_schema: {
      type: "object" as const,
      properties: {
        limit: {
          type: "number",
          description: "Number of recent screenshots to return (default 20)",
        },
      },
      required: [],
    },
  },
];

// ---------------------------------------------------------------------------
// System prompt
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT = `You are Nooto, an AI assistant integrated into the user's desktop. You have access to the user's screen capture history and can search through their recent activity.

You can help the user by:
- Searching their screen history to find information they saw earlier
- Summarizing their recent activity and screen time
- Answering questions about what they were working on
- Providing productivity insights based on their app usage patterns

When using tools, explain what you found in a natural way. Be concise and helpful.
When reporting screen time or activity, group by application and provide time estimates based on screenshot timestamps.`;

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

export function createClient(accessToken: string): Anthropic {
  return new Anthropic({
    apiKey: "unused",
    authToken: accessToken,
    dangerouslyAllowBrowser: true,
  });
}

// ---------------------------------------------------------------------------
// Tool execution
// ---------------------------------------------------------------------------

function formatScreenshots(rows: ScreenshotRow[]): string {
  if (rows.length === 0) return "No screenshots found.";
  return rows
    .map((r, i) => {
      const ts = new Date(r.timestamp).toLocaleString();
      const ocr = r.ocr_text ? `\n  Text: ${r.ocr_text.slice(0, 300)}` : "";
      return `${i + 1}. [${ts}] ${r.app_name} — ${r.window_title}${ocr}`;
    })
    .join("\n\n");
}

async function executeToolCall(name: string, input: unknown): Promise<string> {
  const args = input as Record<string, unknown>;

  switch (name) {
    case "search_screenshots": {
      const query = String(args.query ?? "");
      const limit = typeof args.limit === "number" ? args.limit : 10;
      try {
        const rows = await searchScreenshots(query, limit);
        return formatScreenshots(rows);
      } catch (err) {
        return `Error searching screenshots: ${String(err)}`;
      }
    }

    case "get_recent_activity": {
      const limit = typeof args.limit === "number" ? args.limit : 20;
      try {
        const rows = await getRecentScreenshots(limit, 0);
        return formatScreenshots(rows);
      } catch (err) {
        return `Error fetching recent activity: ${String(err)}`;
      }
    }

    default:
      return `Unknown tool: ${name}`;
  }
}

// ---------------------------------------------------------------------------
// Streaming with tool-use loop
// ---------------------------------------------------------------------------

export async function sendMessageStreaming(
  client: Anthropic,
  messages: Anthropic.MessageParam[],
  onTextDelta: (text: string) => void,
  onToolCall?: (name: string, input: unknown) => void,
  onToolResult?: (id: string, name: string, output: string) => void,
): Promise<{ fullText: string; toolCalls: ToolCallRecord[] }> {
  const allToolCalls: ToolCallRecord[] = [];
  let fullText = "";
  const currentMessages = [...messages];

  while (true) {
    const stream = client.messages.stream({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      tools: CHAT_TOOLS,
      messages: currentMessages,
    });

    for await (const event of stream) {
      if (event.type === "content_block_delta") {
        if (event.delta.type === "text_delta") {
          fullText += event.delta.text;
          onTextDelta(event.delta.text);
        }
      }
    }

    const finalMessage = await stream.finalMessage();

    if (finalMessage.stop_reason === "end_turn" || finalMessage.stop_reason === "max_tokens") {
      break;
    }

    if (finalMessage.stop_reason === "tool_use") {
      const toolUseBlocks = finalMessage.content.filter(
        (b): b is Anthropic.ToolUseBlock => b.type === "tool_use",
      );

      if (toolUseBlocks.length === 0) break;

      currentMessages.push({ role: "assistant", content: finalMessage.content });

      const toolResults: Anthropic.ToolResultBlockParam[] = [];

      for (const toolBlock of toolUseBlocks) {
        onToolCall?.(toolBlock.name, toolBlock.input);

        const output = await executeToolCall(toolBlock.name, toolBlock.input);

        onToolResult?.(toolBlock.id, toolBlock.name, output);

        allToolCalls.push({
          id: toolBlock.id,
          name: toolBlock.name,
          input: toolBlock.input,
          output,
        });

        toolResults.push({
          type: "tool_result",
          tool_use_id: toolBlock.id,
          content: output,
        });
      }

      currentMessages.push({ role: "user", content: toolResults });
      continue;
    }

    break;
  }

  return { fullText, toolCalls: allToolCalls };
}
