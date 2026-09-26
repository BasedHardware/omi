import { createServer, type Server } from "http";
import { AddressInfo } from "net";

import { afterEach, describe, expect, it } from "vitest";

import { McpSseClient } from "../src/runtime/mcp-sse-client.js";

/**
 * A minimal HTTP+SSE MCP server: GET /sse holds the stream open and names the
 * POST endpoint, POST /messages answers 202 and writes the reply to the stream.
 */
function startServer(options: { endpointEvent?: boolean; crlf?: boolean } = {}): Promise<{
  server: Server;
  url: string;
  posts: string[];
}> {
  const posts: string[] = [];
  let stream: import("http").ServerResponse | undefined;

  const server = createServer((req, res) => {
    if (req.method === "GET") {
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      stream = res;
      if (options.endpointEvent !== false) {
        const eol = options.crlf ? "\r\n" : "\n";
        res.write(`event: endpoint${eol}data: /messages?sessionId=abc${eol}${eol}`);
      }
      return;
    }
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      posts.push(body);
      res.writeHead(202).end();
      const message = JSON.parse(body) as { id?: number; method?: string };
      if (message.id === undefined) return;
      const result =
        message.method === "tools/list"
          ? { tools: [{ name: "add", description: "adds", inputSchema: { type: "object" } }] }
          : message.method === "tools/call"
            ? { content: [{ type: "text", text: "7" }] }
            : {};
      // Split across two writes so the client must reassemble a partial frame.
      const eol = options.crlf ? "\r\n" : "\n";
      const frame = `event: message${eol}data: ${JSON.stringify({ jsonrpc: "2.0", id: message.id, result })}${eol}${eol}`;
      stream?.write(frame.slice(0, 12));
      setTimeout(() => stream?.write(frame.slice(12)), 10);
    });
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as AddressInfo;
      resolve({ server, url: `http://127.0.0.1:${port}/sse`, posts });
    });
  });
}

let running: Server | undefined;
afterEach(() => running?.close());

/**
 * A fake HTTP+SSE server for reconnect scenarios. Each GET is a connection;
 * the tools/list reply names its tool after the connection that served it, so
 * a reply from the reconnected stream is distinguishable from the first one.
 */
function startReconnectingServer(
  options: { dropAfterToolsReply?: boolean; dropAfterEndpoint?: boolean; failSubsequentGets?: boolean } = {},
): Promise<{ server: Server; url: string; connections: () => number }> {
  let connections = 0;
  let stream: import("http").ServerResponse | undefined;

  const server = createServer((req, res) => {
    if (req.method === "GET") {
      connections += 1;
      if (options.failSubsequentGets && connections > 1) {
        res.writeHead(503).end();
        return;
      }
      res.writeHead(200, { "Content-Type": "text/event-stream" });
      stream = res;
      res.write(`event: endpoint\ndata: /messages?sessionId=s${connections}\n\n`);
      if (options.dropAfterEndpoint) setTimeout(() => res.destroy(), 30);
      return;
    }
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      res.writeHead(202).end();
      const message = JSON.parse(body) as { id?: number; method?: string };
      if (message.id === undefined) return;
      const result =
        message.method === "tools/list"
          ? { tools: [{ name: `add${connections}`, description: "adds", inputSchema: { type: "object" } }] }
          : {};
      const frame = `event: message\ndata: ${JSON.stringify({ jsonrpc: "2.0", id: message.id, result })}\n\n`;
      stream?.write(frame);
      if (options.dropAfterToolsReply && message.method === "tools/list") {
        setTimeout(() => stream?.destroy(), 30);
      }
    });
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as AddressInfo;
      resolve({ server, url: `http://127.0.0.1:${port}/sse`, connections: () => connections });
    });
  });
}

async function waitFor(predicate: () => boolean, timeoutMs = 3000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("waitFor: condition never became true");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

describe("McpSseClient", () => {
  // Driving one of these as Streamable HTTP POSTs to the stream URL, which the
  // server answers 404 — the whole server reads as unreachable.
  it("posts to the endpoint the server names and reads replies off the stream", async () => {
    const { server, url, posts } = await startServer();
    running = server;
    const client = new McpSseClient(url);

    const tools = await client.listTools();
    expect(tools).toEqual([{ name: "add", description: "adds", inputSchema: { type: "object" } }]);
    expect(await client.callTool("add", { a: 3, b: 4 })).toBe("7");

    // Every message went to /messages, never to the stream URL.
    expect(posts).toHaveLength(4);
    expect(JSON.parse(posts[0]).method).toBe("initialize");
    expect(JSON.parse(posts[1]).method).toBe("notifications/initialized");
    client.dispose();
  });

  // SSE terminates a line with CRLF as readily as LF, and a CRLF frame separator
  // ("\r\n\r\n") contains no "\n\n" — splitting the raw text found no frames at
  // all, so a working server read as one that never spoke.
  it("parses a server that terminates its lines with CRLF", async () => {
    const { server, url } = await startServer({ crlf: true });
    running = server;
    const client = new McpSseClient(url);
    expect((await client.listTools()).map((t) => t.name)).toEqual(["add"]);
    expect(await client.callTool("add", { a: 3, b: 4 })).toBe("7");
    client.dispose();
  });

  // A server that opens a stream but never names an endpoint would otherwise
  // leave discovery hanging until the caller's own timeout.
  it("fails rather than hangs when no endpoint event arrives", async () => {
    const { server, url } = await startServer({ endpointEvent: false });
    running = server;
    const client = new McpSseClient(url);
    setTimeout(() => client.dispose(), 50);
    await expect(client.listTools()).rejects.toThrow();
  });

  // A dropped stream used to fail the server for the rest of the session with
  // nothing in chat the wiser; the client must repair it with bounded backoff.
  it("reconnects with backoff when the live stream drops", async () => {
    const { server, url, connections } = await startReconnectingServer({ dropAfterToolsReply: true });
    running = server;
    const client = new McpSseClient(url, {}, fetch, [20, 20, 20]);
    try {
      expect((await client.listTools()).map((tool) => tool.name)).toEqual(["add1"]);
      await waitFor(() => connections() >= 2);
      // The reconnected stream serves new requests; the tool name proves the
      // reply came from the second connection.
      expect((await client.listTools()).map((tool) => tool.name)).toEqual(["add2"]);
    } finally {
      client.dispose();
    }
  });

  // Repair attempts are bounded: past them the server is marked down with a
  // clear error on every call, not a silent hang or a permanent retry.
  it("marks the server down with a clear error once reconnect attempts are exhausted", async () => {
    const { server, url } = await startReconnectingServer({
      dropAfterEndpoint: true,
      failSubsequentGets: true,
    });
    running = server;
    const client = new McpSseClient(url, {}, fetch, [20, 20, 20]);
    try {
      let lastError: Error | undefined;
      const deadline = Date.now() + 3000;
      while (Date.now() < deadline) {
        try {
          await client.listTools();
        } catch (err) {
          lastError = err instanceof Error ? err : new Error(String(err));
        }
        if (lastError?.message.includes("server is down")) break;
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
      expect(lastError?.message).toMatch(/3 reconnect attempts failed/);
      expect(lastError?.message).toMatch(/server is down for this session/);
      // The state is sticky: new calls fail fast with the same clear error.
      await expect(client.listTools()).rejects.toThrow(/server is down for this session/);
    } finally {
      client.dispose();
    }
  });
});
