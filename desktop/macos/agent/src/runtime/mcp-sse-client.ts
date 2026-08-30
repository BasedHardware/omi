/**
 * MCP client over the HTTP+SSE transport, which a minority of published servers
 * still use — roughly 1 in 20 remotes in the MCP registry, Wix among them.
 *
 * Unlike Streamable HTTP it is two channels: a long-lived GET that the server
 * writes every reply to, and a POST endpoint the server names in its first
 * `endpoint` event. POSTing a request to the stream URL — what a Streamable
 * HTTP client does — is a 404, so these servers need their own client.
 */

import { McpClient, MCP_CLIENT_INFO, MCP_PROTOCOL_VERSION } from "./mcp-client.js";

export type { McpRemoteTool } from "./mcp-client.js";

interface JsonRpcMessage {
  id?: number;
  result?: unknown;
  error?: { code?: number; message?: string };
}

/** How long to wait for the server to name its POST endpoint before giving up. */
const ENDPOINT_TIMEOUT_MS = 10_000;

/**
 * Cap on a single unterminated frame. A 200 response that streams something
 * other than SSE never yields a blank line, and the buffer would otherwise grow
 * for as long as the body does.
 */
const MAX_STREAM_BUFFER = 4 * 1024 * 1024;

/**
 * Marks a promise we hold onto as handled. A stored promise that rejects with no
 * awaiter yet — a client disposed before its first call — is an unhandled
 * rejection, which crashes the host under Node's default policy.
 */
function settled<T>(promise: Promise<T>): Promise<T> {
  promise.catch(() => {});
  return promise;
}

export class McpSseClient extends McpClient {
  private readonly pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (error: Error) => void }
  >();
  private readonly abort = new AbortController();
  private postURL: string | undefined;
  private requestId = 0;
  private opened: Promise<void> | null = null;
  private initialized: Promise<void> | null = null;

  constructor(
    private readonly url: string,
    private readonly configuredHeaders: Readonly<Record<string, string>> = {},
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    super();
  }

  /// The server's configured headers verbatim; an Authorization value carries its own scheme.
  private authHeaders(): Record<string, string> {
    return { ...this.configuredHeaders };
  }

  dispose(): void {
    this.abort.abort();
    this.failAll(new Error("MCP client disposed"));
  }

  private failAll(error: Error): void {
    for (const waiter of this.pending.values()) waiter.reject(error);
    this.pending.clear();
  }

  /**
   * Opens the event stream and resolves once the server has named its POST
   * endpoint. The stream itself keeps being read for the life of the client.
   */
  private open(): Promise<void> {
    this.opened ??= settled(new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("MCP server never sent an SSE endpoint event")),
        ENDPOINT_TIMEOUT_MS,
      );
      timer.unref?.();
      const settle = (error?: Error) => {
        clearTimeout(timer);
        error ? reject(error) : resolve();
      };

      this.fetchImpl(this.url, {
        method: "GET",
        headers: { Accept: "text/event-stream", ...this.authHeaders() },
        signal: this.abort.signal,
      })
        .then(async (response) => {
          if (!response.ok) {
            throw new Error(`MCP server responded ${response.status} opening the event stream`);
          }
          if (!response.body) throw new Error("MCP server returned an empty event stream");
          await this.consume(response.body, settle);
          // The stream ended: no further reply can arrive on it.
          settle(new Error("MCP event stream closed"));
          this.failAll(new Error("MCP event stream closed"));
        })
        .catch((err: unknown) => {
          const error = err instanceof Error ? err : new Error(String(err));
          settle(error);
          this.failAll(error);
        });
    }));
    return this.opened;
  }

  /** Reads SSE frames off the stream, routing each `message` to its waiter. */
  private async consume(
    body: ReadableStream<Uint8Array>,
    onEndpoint: (error?: Error) => void,
  ): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      // SSE terminates a line with CRLF, LF, or a bare CR. Normalizing on the way
      // in is what makes the blank-line split below correct: a CRLF server's frame
      // separator is "\r\n\r\n", which contains no "\n\n" at all, so splitting on
      // the raw text found no frames and the stream read as one that never spoke.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n|\r/g, "\n");
      if (buffer.length > MAX_STREAM_BUFFER) {
        throw new Error("MCP event stream sent an oversized frame");
      }
      // Anything after the last blank line is a partial frame awaiting the next chunk.
      let split = buffer.indexOf("\n\n");
      while (split !== -1) {
        this.handleFrame(buffer.slice(0, split), onEndpoint);
        buffer = buffer.slice(split + 2);
        split = buffer.indexOf("\n\n");
      }
    }
  }

  private handleFrame(frame: string, onEndpoint: (error?: Error) => void): void {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      else if (line.startsWith("data:")) data.push(line.slice("data:".length).trim());
    }
    const payload = data.join("\n");
    if (!payload) return;

    if (event === "endpoint") {
      // Servers name it relative to the stream ("/messages?sessionId=…").
      try {
        this.postURL = new URL(payload, this.url).toString();
        onEndpoint();
      } catch {
        onEndpoint(new Error(`MCP server sent an unusable endpoint: ${payload}`));
      }
      return;
    }
    if (event !== "message") return;

    let message: JsonRpcMessage;
    try {
      message = JSON.parse(payload) as JsonRpcMessage;
    } catch {
      return; // a frame we cannot read is not a reply we can route
    }
    if (typeof message.id !== "number") return; // server notification
    const waiter = this.pending.get(message.id);
    if (!waiter) return;
    this.pending.delete(message.id);
    if (message.error) {
      waiter.reject(new Error(String(message.error.message ?? message.error.code ?? "MCP error")));
    } else {
      waiter.resolve(message.result);
    }
  }

  /**
   * POSTs a message to the endpoint the server named. A request's reply comes
   * back on the event stream, never in the POST response, which is a bare 202.
   */
  private async send(payload: Record<string, unknown>): Promise<void> {
    await this.open();
    if (!this.postURL) throw new Error("MCP server has no message endpoint");
    const response = await this.fetchImpl(this.postURL, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this.authHeaders() },
      body: JSON.stringify(payload),
      signal: this.abort.signal,
    });
    if (!response.ok) {
      throw new Error(`MCP server responded ${response.status} for ${String(payload.method)}`);
    }
  }

  protected async rpc(method: string, params: Record<string, unknown>): Promise<unknown> {
    const id = ++this.requestId;
    // Guarded before the send: a client disposed while opening the stream
    // rejects this waiter before anything is awaiting it.
    const reply = settled(
      new Promise<unknown>((resolve, reject) => {
        this.pending.set(id, { resolve, reject });
      }),
    );
    try {
      await this.send({ jsonrpc: "2.0", id, method, params });
    } catch (err) {
      this.pending.delete(id);
      throw err;
    }
    return reply;
  }

  protected ensureInitialized(): Promise<void> {
    this.initialized ??= settled((async () => {
      this.recordCapabilities(
        await this.rpc("initialize", {
          protocolVersion: MCP_PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: MCP_CLIENT_INFO,
        }),
      );
      await this.send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
    })().catch((err: unknown) => {
      this.initialized = null; // a failed handshake must be retryable
      throw err;
    }));
    return this.initialized;
  }
}
