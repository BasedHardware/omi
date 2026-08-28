/**
 * Minimal MCP client over Streamable HTTP for user-added remote servers.
 * Speaks just enough of the protocol for tool use: initialize handshake,
 * tools/list, tools/call. Accepts plain-JSON and SSE-framed responses.
 */

export interface McpRemoteTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

interface JsonRpcResponse {
  result?: unknown;
  error?: { code?: number; message?: string };
}

const PROTOCOL_VERSION = "2025-06-18";

function parseBody(contentType: string, body: string): JsonRpcResponse {
  if (contentType.includes("text/event-stream")) {
    // The response to a POSTed request arrives as SSE data lines; the last
    // complete JSON-RPC message with a result/error is the response.
    let last: JsonRpcResponse | undefined;
    for (const line of body.split("\n")) {
      if (!line.startsWith("data:")) continue;
      try {
        const parsed = JSON.parse(line.slice(5).trim()) as JsonRpcResponse;
        if (parsed && (parsed.result !== undefined || parsed.error !== undefined)) last = parsed;
      } catch {
        // partial or non-JSON frame — skip
      }
    }
    if (!last) throw new Error("no JSON-RPC response in SSE stream");
    return last;
  }
  return JSON.parse(body) as JsonRpcResponse;
}

export class McpHttpClient {
  private sessionId: string | undefined;
  private initialized = false;
  private requestId = 0;

  constructor(
    private readonly url: string,
    private readonly token?: string,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": PROTOCOL_VERSION,
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      ...(this.sessionId ? { "Mcp-Session-Id": this.sessionId } : {}),
    };
  }

  private async rpc(method: string, params: Record<string, unknown>, notification = false): Promise<unknown> {
    const payload: Record<string, unknown> = { jsonrpc: "2.0", method, params };
    if (!notification) payload.id = ++this.requestId;
    const response = await this.fetchImpl(this.url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    const newSession = response.headers.get("mcp-session-id");
    if (newSession) this.sessionId = newSession;
    if (notification) return undefined;
    if (!response.ok) {
      throw new Error(`MCP server responded ${response.status} for ${method}`);
    }
    const parsed = parseBody(response.headers.get("content-type") ?? "", await response.text());
    if (parsed.error) {
      throw new Error(`MCP error for ${method}: ${parsed.error.message ?? parsed.error.code}`);
    }
    return parsed.result;
  }

  private async ensureInitialized(): Promise<void> {
    if (this.initialized) return;
    await this.rpc("initialize", {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: "omi-desktop", version: "1.0.0" },
    });
    try {
      await this.rpc("notifications/initialized", {}, true);
    } catch {
      // Some servers reject the notification but still serve requests.
    }
    this.initialized = true;
  }

  async listTools(): Promise<McpRemoteTool[]> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/list", {})) as { tools?: unknown };
    if (!Array.isArray(result?.tools)) return [];
    return result.tools.flatMap((tool) => {
      const { name, description, inputSchema } = (tool ?? {}) as Record<string, unknown>;
      if (typeof name !== "string" || !name) return [];
      return [
        {
          name,
          description: typeof description === "string" ? description : "",
          inputSchema:
            inputSchema && typeof inputSchema === "object"
              ? (inputSchema as Record<string, unknown>)
              : { type: "object", properties: {} },
        },
      ];
    });
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/call", { name, arguments: args })) as {
      content?: Array<{ type?: string; text?: string }>;
      isError?: boolean;
    };
    const text = (result?.content ?? [])
      .filter((block) => block?.type === "text" && typeof block.text === "string")
      .map((block) => block.text)
      .join("\n");
    if (result?.isError) {
      throw new Error(text || `MCP tool ${name} reported an error`);
    }
    return text || JSON.stringify(result ?? {});
  }
}
