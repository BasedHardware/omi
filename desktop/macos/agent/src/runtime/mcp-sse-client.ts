/**
 * MCP client over the HTTP+SSE transport, which a minority of published servers
 * still use — roughly 1 in 20 remotes in the MCP registry, Wix among them.
 *
 * Unlike Streamable HTTP it is two channels: a long-lived GET that the server
 * writes every reply to, and a POST endpoint the server names in its first
 * `endpoint` event. POSTing a request to the stream URL — what a Streamable
 * HTTP client does — is a 404, so these servers need their own client.
 *
 * The stream is also the transport's only reply channel, so a drop used to
 * fail the server for the rest of the session with nothing in chat the wiser.
 * A drop is now repaired with bounded backoff (see
 * DEFAULT_SSE_RECONNECT_DELAYS_MS) before the server is marked down with an
 * error that reaches the model.
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
 * Backoff before each reconnect attempt after a live stream drops. Three
 * tries — roughly 21s worst case — covers a server restart or a proxy blip;
 * past that the server is marked down with a clear error instead of the
 * session silently losing it forever. Injectable so tests run fast.
 */
export const DEFAULT_SSE_RECONNECT_DELAYS_MS: readonly number[] = [1_000, 5_000, 15_000];

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
  private ready: Promise<void> | null = null;

  /**
   * What a request actually waits on: the live stream's endpoint. Replaced by
   * the monitor on the first connect and on every drop, so requests issued
   * while a drop is being repaired wait for the repair instead of failing
   * against the dead stream — bounded by the caller's own timeout.
   */
  private gate: Promise<void> = Promise.resolve();
  private gateReady: () => void = () => {};
  private gateFailed: (error: Error) => void = () => {};
  /** The consume loop of the currently-live stream; resolves when it ends. */
  private currentRun: Promise<void> = Promise.resolve();
  private initialized: Promise<void> | null = null;
  private readonly reconnectDelaysMs: readonly number[];

  constructor(
    private readonly url: string,
    private readonly configuredHeaders: Readonly<Record<string, string>> = {},
    private readonly fetchImpl: typeof fetch = fetch,
    reconnectDelaysMs: readonly number[] = DEFAULT_SSE_RECONNECT_DELAYS_MS,
  ) {
    super();
    this.reconnectDelaysMs = reconnectDelaysMs;
  }

  /// The server's configured headers verbatim; an Authorization value carries its own scheme.
  private authHeaders(): Record<string, string> {
    return { ...this.configuredHeaders };
  }

  dispose(): void {
    this.abort.abort();
    // A request parked on the gate — waiting for a first endpoint or for a
    // repair — must fail now, not wait out the backoff.
    this.gateFailed(new Error("MCP client disposed"));
    this.failAll(new Error("MCP client disposed"));
  }

  private failAll(error: Error): void {
    for (const waiter of this.pending.values()) waiter.reject(error);
    this.pending.clear();
  }

  /**
   * Waits until a stream with a POST endpoint is live (or rejects once the
   * server is marked down).
   */
  private open(): Promise<void> {
    this.ready ??= settled(this.connectAndMonitor());
    return this.gate;
  }

  private replaceGate(): void {
    this.gate = new Promise<void>((resolve, reject) => {
      this.gateReady = resolve;
      this.gateFailed = reject;
    });
    // A gate with no awaiting request — the client disposed mid-repair — must
    // not become an unhandled rejection; real awaiters still see the error.
    this.gate.catch(() => {});
  }

  /** One GET plus the wait for the endpoint event; leaves the stream being read. */
  private async connectStream(): Promise<void> {
    const response = await this.fetchImpl(this.url, {
      method: "GET",
      headers: { Accept: "text/event-stream", ...this.authHeaders() },
      signal: this.abort.signal,
    });
    if (!response.ok) {
      throw new Error(`MCP server responded ${response.status} opening the event stream`);
    }
    if (!response.body) throw new Error("MCP server returned an empty event stream");
    let endpointSettled: (error?: Error) => void;
    let endpointDone = false;
    const endpoint = new Promise<void>((resolve, reject) => {
      endpointSettled = (error?: Error) => {
        endpointDone = true;
        if (error) reject(error);
        else resolve();
      };
    });
    const timer = setTimeout(
      () => endpointSettled(new Error("MCP server never sent an SSE endpoint event")),
      ENDPOINT_TIMEOUT_MS,
    );
    timer.unref?.();
    // Starts immediately; `currentRun` ends when this stream does. A stream
    // that ends before naming an endpoint must still settle the wait —
    // otherwise this connect would hang past its own timeout.
    this.currentRun = this.consume(response.body, endpointSettled!).finally(() => {
      clearTimeout(timer);
      if (!endpointDone) {
        endpointSettled(new Error("MCP event stream closed before the server named an endpoint"));
      }
    });
    await endpoint;
  }

  /** Connect, then repair the stream with bounded backoff every time it drops. */
  private async connectAndMonitor(): Promise<void> {
    this.replaceGate();
    await this.connectStream();
    this.gateReady();
    for (;;) {
      try {
        await this.currentRun;
      } catch {
        // A consume error is a stream drop like any other.
      }
      if (this.abort.signal.aborted) return;
      // In-flight requests can no longer be answered on the dead stream.
      this.failAll(new Error("MCP event stream closed"));
      // New requests wait for the repair instead of racing the dead stream.
      this.replaceGate();
      try {
        await this.reconnectWithBackoff();
        this.gateReady();
      } catch (err) {
        this.gateFailed(err instanceof Error ? err : new Error(String(err)));
        // Exhausted: this rejects `ready`, marking the server down for the
        // session with the reconnect error on every future request.
        throw err;
      }
    }
  }

  private async reconnectWithBackoff(): Promise<void> {
    let lastError: Error | undefined;
    for (const delay of this.reconnectDelaysMs) {
      await this.sleep(delay);
      if (this.abort.signal.aborted) return;
      try {
        await this.connectStream();
        process.stderr.write(`[mcp-sse] ${this.url}: event stream restored\n`);
        return;
      } catch (err) {
        lastError = err instanceof Error ? err : new Error(String(err));
      }
    }
    throw new Error(
      `MCP event stream dropped and ${this.reconnectDelaysMs.length} reconnect attempts failed ` +
        `(last error: ${lastError?.message ?? "unknown"}); the server is down for this session`,
    );
  }

  /** Abort-aware sleep: dispose() must not wait out a backoff window. */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, ms);
      timer.unref?.();
      this.abort.signal.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
    });
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
