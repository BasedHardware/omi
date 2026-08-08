import { describe, expect, test } from "bun:test";

import {
  createMcpProtocolHandler,
  MCP_PROTOCOL_VERSION,
  SYNTHESIZED_MEMORY_READ_RATE_POLICY,
  SYNTHESIZED_MEMORY_READ_SCOPE,
  SYNTHESIZED_MEMORY_READ_TOOL,
  type McpCredential,
  type McpProtocolPorts,
} from "./protocol";

type Counters = {
  authenticate: number;
  authorize: number;
  rateLimit: number;
  cursorParse: number;
  cursorIssue: number;
  readPage: number;
  validatePage: number;
  order: string[];
};

type FixtureOptions = {
  authenticated?: boolean;
  scopes?: readonly string[];
  authorize?: boolean;
  rateAllowed?: boolean;
  cursorFailure?: boolean;
  validPage?: boolean;
};

function fixture(options: FixtureOptions = {}): { ports: McpProtocolPorts; counters: Counters } {
  const counters: Counters = {
    authenticate: 0,
    authorize: 0,
    rateLimit: 0,
    cursorParse: 0,
    cursorIssue: 0,
    readPage: 0,
    validatePage: 0,
    order: [],
  };
  const credential: McpCredential = {
    scopes: options.scopes ?? [SYNTHESIZED_MEMORY_READ_SCOPE],
    rateLimitIdentity: "credential-rate-identity",
    cursorBindings: {
      ownerAuthorizationDigest: "sha256:owner_digest_only",
      appAuthorizationDigest: "sha256:app_digest_only",
      keyAuthorizationDigest: "sha256:key_digest_only",
      graphGenerationDigest: "sha256:graph_digest_only",
      projectionGenerationDigest: "sha256:projection_digest_only",
      filterDigest: "sha256:filter_digest_only",
      readModeDigest: "sha256:read_mode_digest_only",
    },
    authentication: { internalOnly: true },
  };
  const page = {
    contractVersion: "1.0.0",
    items: [{ id: "opaque-item-1", text: "Synthesized result", citations: [], provenance: [] }],
    window: { nextCursor: null },
    completeness: { state: "complete" },
    absence: { state: "not_absent" },
  };

  return {
    counters,
    ports: {
      async authenticate() {
        counters.authenticate += 1;
        counters.order.push("authenticate");
        return options.authenticated === false ? null : credential;
      },
      async authorize() {
        counters.authorize += 1;
        counters.order.push("authorize");
        return options.authorize === false ? { allowed: false } : { allowed: true, readAuthorization: { internalOnly: true } };
      },
      async rateLimit(input) {
        counters.rateLimit += 1;
        counters.order.push(`rateLimit:${input.declaredPolicy}`);
        return options.rateAllowed === false ? { allowed: false, retryAfterSeconds: 3 } : { allowed: true };
      },
      async readPage(input) {
        counters.readPage += 1;
        counters.order.push(`readPage:${input.afterVisibleKey ?? "start"}`);
        return {
          ...page,
          window: { nextCursor: input.issueCursor("opaque-visible-key-2") },
        };
      },
      validatePage(value) {
        counters.validatePage += 1;
        counters.order.push("validatePage");
        return options.validPage !== false && value !== null && typeof value === "object";
      },
      cursor: {
        parse(input) {
          counters.cursorParse += 1;
          counters.order.push(`cursorParse:${input.cursor}`);
          if (options.cursorFailure || input.cursor === "bad-cursor") {
            throw new Error("invalid cursor");
          }
          return { lastVisibleKey: "opaque-visible-key-1" };
        },
        issue(input) {
          counters.cursorIssue += 1;
          counters.order.push(`cursorIssue:${input.lastVisibleKey}`);
          return `signed:${input.lastVisibleKey}`;
        },
      },
    },
  };
}

function callRequest(arguments_: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    jsonrpc: "2.0",
    id: "request-1",
    method: "tools/call",
    params: { name: SYNTHESIZED_MEMORY_READ_TOOL, arguments: arguments_ },
  };
}

function rpcBody(response: { body?: unknown }): Record<string, unknown> {
  expect(response.body).toBeDefined();
  return response.body as Record<string, unknown>;
}

function errorCode(response: { body?: unknown }): number {
  return ((rpcBody(response).error as Record<string, unknown>).code) as number;
}

describe("protocol-native synthesized MCP handler", () => {
  test("A1 authenticates before body dispatch and rejects unauthenticated input", async () => {
    const { ports, counters } = fixture({ authenticated: false });
    const handler = createMcpProtocolHandler(ports);

    const response = await handler.handleHttp({ body: callRequest() });

    expect(response.status).toBe(401);
    expect(counters).toMatchObject({ authenticate: 1, authorize: 0, rateLimit: 0, readPage: 0 });

    const malformedCredential = fixture();
    malformedCredential.ports.authenticate = async () => ({ scopes: SYNTHESIZED_MEMORY_READ_SCOPE } as never);
    const malformedResponse = await createMcpProtocolHandler(malformedCredential.ports).handleHttp({ body: callRequest() });
    expect(malformedResponse.status).toBe(401);
    expect(malformedCredential.counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });
  });

  test("A2 gives tools/list and tools/call the same scope and grant gate", async () => {
    const missingScope = fixture({ scopes: [] });
    const missingScopeHandler = createMcpProtocolHandler(missingScope.ports);

    const list = await missingScopeHandler.handleHttp({
      body: { jsonrpc: "2.0", id: "list-1", method: "tools/list" },
    });
    const call = await missingScopeHandler.handleHttp({ body: callRequest() });

    expect(((rpcBody(list).result as Record<string, unknown>).tools as unknown[])).toEqual([]);
    expect(errorCode(call)).toBe(-32003);
    expect(missingScope.counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });

    const missingGrant = fixture({ authorize: false });
    const missingGrantHandler = createMcpProtocolHandler(missingGrant.ports);
    const deniedList = await missingGrantHandler.handleHttp({
      body: { jsonrpc: "2.0", id: "list-2", method: "tools/list" },
    });
    const deniedCall = await missingGrantHandler.handleHttp({ body: callRequest() });

    expect(((rpcBody(deniedList).result as Record<string, unknown>).tools as unknown[])).toEqual([]);
    expect(errorCode(deniedCall)).toBe(-32003);
    expect(missingGrant.counters).toMatchObject({ authorize: 2, rateLimit: 0, readPage: 0 });

    const malformedDecision = fixture();
    malformedDecision.ports.authorize = async () => ({ allowed: "false" } as never);
    const malformedDecisionHandler = createMcpProtocolHandler(malformedDecision.ports);
    const malformedList = await malformedDecisionHandler.handleHttp({
      body: { jsonrpc: "2.0", id: "list-3", method: "tools/list" },
    });
    const malformedCall = await malformedDecisionHandler.handleHttp({ body: callRequest() });
    expect(((rpcBody(malformedList).result as Record<string, unknown>).tools as unknown[])).toEqual([]);
    expect(errorCode(malformedCall)).toBe(-32003);
  });

  test("A4 applies the declared per-credential policy before any page read", async () => {
    const { ports, counters } = fixture({ rateAllowed: false });
    const handler = createMcpProtocolHandler(ports);

    const response = await handler.handleHttp({ body: callRequest() });

    expect(errorCode(response)).toBe(-32029);
    expect(counters.readPage).toBe(0);
    expect(counters.order).toEqual([
      "authenticate",
      "authorize",
      `rateLimit:${SYNTHESIZED_MEMORY_READ_RATE_POLICY}`,
    ]);
  });

  test("A5 accepts only the injected strict page projection and serializes no raw fields", async () => {
    const accepted = fixture();
    const acceptedHandler = createMcpProtocolHandler(accepted.ports);
    const response = await acceptedHandler.handleHttp({ body: callRequest() });
    const result = rpcBody(response).result as Record<string, unknown>;
    const content = (result.content as Array<Record<string, unknown>>)[0];
    const projection = JSON.parse(content.text as string) as Record<string, unknown>;

    expect(projection.items).toBeDefined();
    expect(JSON.stringify(response.body)).not.toContain("owner-id");
    expect(JSON.stringify(response.body)).not.toContain("raw-row");
    expect(accepted.counters.validatePage).toBe(1);

    const rejected = fixture({ validPage: false });
    rejected.ports.readPage = async () => ({
      id: "legacy-row-id",
      content: "raw-row",
      owner: "owner-id",
    });
    const rejectedHandler = createMcpProtocolHandler(rejected.ports);
    const rejectedResponse = await rejectedHandler.handleHttp({ body: callRequest() });

    expect(errorCode(rejectedResponse)).toBe(-32603);
    expect(JSON.stringify(rejectedResponse.body)).not.toContain("Synthesized result");
    expect(JSON.stringify(rejectedResponse.body)).not.toContain("raw-row");
    expect(JSON.stringify(rejectedResponse.body)).not.toContain("owner-id");
  });

  test("A7 handles initialize, Streamable HTTP notifications, protocol errors, and SSE deterministically", async () => {
    const { ports, counters } = fixture();
    const handler = createMcpProtocolHandler(ports);

    const initialized = await handler.handleHttp({
      body: { jsonrpc: "2.0", id: 1, method: "initialize" },
    });
    const initializedResult = rpcBody(initialized).result as Record<string, unknown>;
    expect(initializedResult.protocolVersion).toBe(MCP_PROTOCOL_VERSION);

    const notification = await handler.handleHttp({
      body: { jsonrpc: "2.0", method: "notifications/initialized" },
    });
    expect(notification.status).toBe(202);
    expect(notification.body).toBeUndefined();

    const unknown = await handler.handleHttp({
      accept: "text/event-stream",
      body: { jsonrpc: "2.0", id: "unknown", method: "not/a/method" },
    });
    expect(unknown.status).toBe(200);
    expect(unknown.headers["content-type"]).toBe("text/event-stream");
    expect(unknown.body).toBe("event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":\"unknown\",\"error\":{\"code\":-32601,\"message\":\"Method not found\"}}\n\n");
    expect(counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });
  });

  test("U1 rejects malformed or failed cursor validation before data access", async () => {
    const { ports, counters } = fixture({ cursorFailure: true });
    const handler = createMcpProtocolHandler(ports);

    const response = await handler.handleHttp({ body: callRequest({ cursor: "bad-cursor" }) });

    expect(errorCode(response)).toBe(-32602);
    expect(counters).toMatchObject({ cursorParse: 1, readPage: 0, validatePage: 0 });
  });

  test("U2 rejects a cross-binding cursor through its injected validator before data access", async () => {
    const { ports, counters } = fixture();
    const originalParse = ports.cursor.parse;
    ports.cursor.parse = (input) => {
      counters.cursorParse += 1;
      counters.order.push(`cursorParse:${input.cursor}`);
      if (input.cursor === "cross-binding") {
        throw new Error("binding mismatch");
      }
      return originalParse(input);
    };
    const handler = createMcpProtocolHandler(ports);

    const response = await handler.handleHttp({ body: callRequest({ cursor: "cross-binding" }) });

    expect(errorCode(response)).toBe(-32602);
    expect(counters).toMatchObject({ readPage: 0, validatePage: 0 });
  });
});
