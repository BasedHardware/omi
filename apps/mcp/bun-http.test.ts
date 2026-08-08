import { describe, expect, test } from "bun:test";
import { connect } from "node:net";

import {
  createBunMcpHttpHandler,
  MCP_QA_MAX_REQUEST_BODY_BYTES,
  type BunMcpFetchHandler,
} from "./bun-http";
import {
  createMcpProtocolHandler,
  MCP_PROTOCOL_VERSION,
  SYNTHESIZED_MEMORY_READ_SCOPE,
  SYNTHESIZED_MEMORY_READ_TOOL,
  type McpCredential,
  type McpProtocolPorts,
} from "./protocol";

// domain-pending(DIV-DOMCORE-001): "memory" remains the legacy read label.
// domain-pending(DIV-DOMCORE-008): the synthesized item name remains pending.

type ProtocolFixture = {
  readonly ports: McpProtocolPorts;
  readonly authenticationHeaders: Array<string | undefined>;
};

type RawHttpResponse = {
  readonly status: number;
  readonly body: string;
};

function protocolFixture(): ProtocolFixture {
  const authenticationHeaders: Array<string | undefined> = [];
  // domain-pending(DIV-DOMAPPS-001): application/app is the retained legacy
  // credential coordinate until the app-domain vocabulary is ratified.
  // domain-pending(DIV-DOMAPPS-006): the QA identity remains an exact key
  // coordinate and does not choose a replacement key-family term.
  const credential: McpCredential = {
    kind: "mcp_api_key",
    scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
    rateLimitKey: {
      prefix: "mcp",
      uid: "qa-owner",
      app_id: "qa-application",
      key_id: "qa-key-id",
    },
    cursorBindings: {
      ownerAuthorizationDigest: "qa-owner-digest",
      appAuthorizationDigest: "qa-application-digest",
      keyAuthorizationDigest: "qa-key-digest",
      graphGenerationDigest: "qa-graph-digest",
      projectionGenerationDigest: "qa-projection-digest",
      filterDigest: "qa-filter-digest",
      readModeDigest: "qa-read-mode-digest",
    },
    authentication: { qaOnly: true },
  };

  return {
    authenticationHeaders,
    ports: {
      // domain-pending(DIV-DOMX-002): this caller-boundary label is pending.
      validateOrigin: () => true,
      async authenticate({ apiKeyHeader }) {
        authenticationHeaders.push(apiKeyHeader);
        return apiKeyHeader === "qa-key" ? credential : null;
      },
      async authorize() {
        return { allowed: true, readAuthorization: { qaOnly: true } };
      },
      async rateLimit() {
        return { allowed: true };
      },
      async readPage() {
        return {
          contractVersion: "1.0.0",
          items: [{ id: "opaque-qa-item", text: "Synthesized QA text" }],
          window: { nextCursor: null },
          completeness: { state: "complete" },
          absence: { state: "not_absent" },
        };
      },
      validatePage(page) {
        return JSON.stringify(page);
      },
      async reauthorizeBeforeEmission() {
        return true;
      },
      cursor: {
        parse() {
          return { lastVisibleKey: "opaque-qa-visible-key" };
        },
        issue() {
          return "opaque-qa-cursor";
        },
      },
    },
  };
}

function requestHeaders(method: string, name?: string): Record<string, string> {
  return {
    accept: "application/json, text/event-stream",
    authorization: "qa-key",
    "content-type": "application/json",
    "mcp-method": method,
    ...(name === undefined ? {} : { "mcp-name": name }),
    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
  };
}

function rpcBody(method: string, params: Record<string, unknown>, id: string): string {
  return JSON.stringify({ jsonrpc: "2.0", id, method, params });
}

function meta(): Record<string, unknown> {
  return {
    "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
  };
}

async function withServer<T>(handler: BunMcpFetchHandler, run: (port: number) => Promise<T>): Promise<T> {
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: handler,
  });
  try {
    return await run(server.port);
  } finally {
    await server.stop(true);
  }
}

async function postRpc(
  port: number,
  method: string,
  params: Record<string, unknown>,
  id: string,
  body = rpcBody(method, params, id),
): Promise<Response> {
  return fetch(`http://127.0.0.1:${port}/mcp`, {
    method: "POST",
    headers: requestHeaders(method, method === "tools/call" ? String(params.name) : undefined),
    body,
  });
}

function rawRequest(port: number, request: string): Promise<RawHttpResponse> {
  return new Promise((resolve, reject) => {
    const socket = connect({ host: "127.0.0.1", port });
    let raw = "";
    socket.setEncoding("utf8");
    socket.setTimeout(5_000);
    socket.on("connect", () => socket.write(request));
    socket.on("data", (chunk) => {
      raw += chunk;
    });
    socket.on("timeout", () => {
      socket.destroy(new Error("raw HTTP QA request timed out"));
    });
    socket.on("error", reject);
    socket.on("end", () => {
      const boundary = raw.indexOf("\r\n\r\n");
      if (boundary < 0) {
        reject(new Error("raw HTTP QA response was malformed"));
        return;
      }
      const head = raw.slice(0, boundary);
      const status = Number(head.split("\r\n", 1)[0]?.split(" ", 3)[1]);
      resolve({ status, body: raw.slice(boundary + 4) });
    });
  });
}

function rawPost(body: string, extraHeaders: readonly string[]): string {
  return [
    "POST /mcp HTTP/1.1",
    "Host: 127.0.0.1",
    "Accept: application/json, text/event-stream",
    "Content-Type: application/json",
    `MCP-Protocol-Version: ${MCP_PROTOCOL_VERSION}`,
    "Mcp-Method: server/discover",
    "Authorization: qa-key",
    ...extraHeaders,
    `Content-Length: ${Buffer.byteLength(body, "utf8")}`,
    "Connection: close",
    "",
    body,
  ].join("\r\n");
}

describe("Bun MCP HTTP QA adapter", () => {
  test("runs discover and call through a real localhost Request/Response boundary", async () => {
    const fixture = protocolFixture();
    const handler = createBunMcpHttpHandler(createMcpProtocolHandler(fixture.ports));

    await withServer(handler, async (port) => {
      const discovered = await postRpc(port, "server/discover", { _meta: meta() }, "discover-1");
      const discovery = await discovered.json() as Record<string, unknown>;
      expect(discovered.status).toBe(200);
      expect(discovered.headers.get("content-type")).toBe("application/json");
      expect(discovered.headers.get("mcp-protocol-version")).toBe(MCP_PROTOCOL_VERSION);
      expect(discovery).toMatchObject({ jsonrpc: "2.0", id: "discover-1" });

      const called = await postRpc(port, "tools/call", {
        name: SYNTHESIZED_MEMORY_READ_TOOL,
        arguments: { limit: 1 },
        _meta: meta(),
      }, "call-1");
      const call = await called.json() as Record<string, unknown>;
      const result = call.result as Record<string, unknown>;
      const content = result.content as Array<Record<string, unknown>>;
      expect(called.status).toBe(200);
      expect(result.resultType).toBe("complete");
      expect(JSON.parse(String(content[0]?.text))).toMatchObject({
        items: [{ id: "opaque-qa-item", text: "Synthesized QA text" }],
      });
    });
  });

  test("maps malformed and oversized JSON to the protocol invalid-request response", async () => {
    const fixture = protocolFixture();
    const handler = createBunMcpHttpHandler(createMcpProtocolHandler(fixture.ports));

    await withServer(handler, async (port) => {
      const malformed = await postRpc(port, "server/discover", { _meta: meta() }, "ignored", "{");
      expect(malformed.status).toBe(400);
      expect(await malformed.json()).toMatchObject({
        jsonrpc: "2.0",
        id: null,
        error: { code: -32600, message: "Invalid Request" },
      });

      const oversized = await postRpc(
        port,
        "server/discover",
        { _meta: meta() },
        "ignored",
        `{"padding":"${"x".repeat(MCP_QA_MAX_REQUEST_BODY_BYTES)}"}`,
      );
      expect(oversized.status).toBe(400);
      expect(await oversized.json()).toMatchObject({ error: { code: -32600 } });
      expect(fixture.authenticationHeaders).toEqual([]);
    });
  });

  test("rejects Bun-coalesced duplicate Origin and Authorization headers fail-closed", async () => {
    const fixture = protocolFixture();
    const handler = createBunMcpHttpHandler(createMcpProtocolHandler(fixture.ports));
    const body = rpcBody("server/discover", { _meta: meta() }, "duplicate-1");

    await withServer(handler, async (port) => {
      const duplicateOrigin = await rawRequest(port, rawPost(body, [
        "Origin: https://trusted.example",
        "origin: https://other.example",
      ]));
      expect(duplicateOrigin.status).toBe(403);
      expect(JSON.parse(duplicateOrigin.body)).toMatchObject({ error: { code: -32600 } });

      const duplicateAuthorization = await rawRequest(port, rawPost(body, [
        "authorization: other-qa-key",
      ]));
      expect(duplicateAuthorization.status).toBe(401);
      expect(JSON.parse(duplicateAuthorization.body)).toEqual({ error: "authentication_required" });
      expect(fixture.authenticationHeaders).toEqual([undefined]);
    });
  });

  test("preserves bodyless and error responses exactly", async () => {
    const fixture = protocolFixture();
    const handler = createBunMcpHttpHandler(createMcpProtocolHandler(fixture.ports));

    await withServer(handler, async (port) => {
      const bodyless = await fetch(`http://127.0.0.1:${port}/mcp`, { method: "GET" });
      expect(bodyless.status).toBe(405);
      expect(bodyless.headers.get("content-type")).toBe("application/json");
      expect(bodyless.headers.get("mcp-protocol-version")).toBe(MCP_PROTOCOL_VERSION);
      expect(await bodyless.text()).toBe("");

      const unauthorized = await fetch(`http://127.0.0.1:${port}/mcp`, {
        method: "POST",
        headers: { ...requestHeaders("server/discover"), authorization: "wrong-qa-key" },
        body: rpcBody("server/discover", { _meta: meta() }, "unauthorized-1"),
      });
      expect(unauthorized.status).toBe(401);
      expect(await unauthorized.json()).toEqual({ error: "authentication_required" });
    });
  });
});
