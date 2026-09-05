/**
 * MCP client over Streamable HTTP for user-added remote servers: every message
 * is POSTed to one URL, and the reply comes back as JSON or as an SSE-framed
 * body on that same response. Servers whose URL is a long-lived event stream
 * instead speak the older HTTP+SSE transport — see McpSseClient.
 */

import { McpClient, MCP_CLIENT_INFO, MCP_PROTOCOL_VERSION } from "./mcp-client.js";

export type { McpRemoteTool } from "./mcp-client.js";

interface JsonRpcResponse {
  result?: unknown;
  error?: { code?: number; message?: string };
}

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

export class McpHttpClient extends McpClient {
  private sessionId: string | undefined;
  private initialized = false;
  private requestId = 0;

  constructor(
    private readonly url: string,
    private readonly authHeaders: Readonly<Record<string, string>> = {},
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    super();
  }

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
      // The server's configured headers verbatim: an Authorization value carries its own
      // scheme, and rebuilding one as `Bearer <value>` corrupted every non-Bearer scheme.
      ...this.authHeaders,
      ...(this.sessionId ? { "Mcp-Session-Id": this.sessionId } : {}),
    };
  }

  protected async rpc(
    method: string,
    params: Record<string, unknown>,
    notification = false,
  ): Promise<unknown> {
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

  protected async ensureInitialized(): Promise<void> {
    if (this.initialized) return;
    this.recordCapabilities(
      await this.rpc("initialize", {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: MCP_CLIENT_INFO,
      }),
    );
    try {
      await this.rpc("notifications/initialized", {}, true);
    } catch {
      // Some servers reject the notification but still serve requests.
    }
    this.initialized = true;
  }
}
