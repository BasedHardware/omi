// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-006)
import { describe, expect, test } from "bun:test";

import { InvalidMcpCursorError } from "./cursor";
import {
  createMcpProtocolHandler,
  MCP_PROTOCOL_VERSION,
  SYNTHESIZED_MEMORY_READ_RATE_POLICY,
  SYNTHESIZED_MEMORY_READ_SCOPE,
  SYNTHESIZED_MEMORY_READ_TOOL,
  type McpCredential,
  type McpHttpRequest,
  type McpProtocolPorts,
} from "./protocol";

type Counters = {
  validateOrigin: number;
  authenticate: number;
  authorize: number;
  rateLimit: number;
  readPage: number;
  validatePage: number;
  reauthorizeBeforeEmission: number;
  order: string[];
  rateInputs: Array<Record<string, unknown>>;
  readInputs: Array<{ authorization: unknown; cursor: string | null; limit: number }>;
};

type FixtureOptions = {
  originAllowed?: boolean;
  authenticated?: boolean;
  scopes?: readonly string[];
  authorize?: boolean;
  transportRateAllowed?: boolean;
  readRateAllowed?: boolean;
  reauthorize?: boolean;
  readPageError?: unknown;
  validatedPage?: string | null;
  uid?: string;
  app_id?: string;
  key_id?: string;
};

type ToolDescriptorForTest = {
  inputSchema: { properties: { cursor: { minLength: number } } };
};

function fixture(options: FixtureOptions = {}): { ports: McpProtocolPorts; counters: Counters } {
  const counters: Counters = {
    validateOrigin: 0,
    authenticate: 0,
    authorize: 0,
    rateLimit: 0,
    readPage: 0,
    validatePage: 0,
    reauthorizeBeforeEmission: 0,
    order: [],
    rateInputs: [],
    readInputs: [],
  };
  const credential: McpCredential = {
    kind: "mcp_api_key",
    scopes: options.scopes ?? [SYNTHESIZED_MEMORY_READ_SCOPE],
    rateLimitKey: {
      prefix: "mcp",
      uid: options.uid ?? "owner-1",
      app_id: options.app_id ?? "app-1",
      key_id: options.key_id ?? "key-1",
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
      // domain-pending(DIV-DOMX-002): test the HTTP caller "surface" through
      // the adapter-owned Origin policy rather than inventing a domain term.
      async validateOrigin() {
        counters.validateOrigin += 1;
        return options.originAllowed !== false;
      },
      async authenticate(input) {
        counters.authenticate += 1;
        counters.order.push(`authenticate:${input.requiredKind}`);
        return options.authenticated === false ? null : credential;
      },
      async authorize() {
        counters.authorize += 1;
        counters.order.push("authorize");
        return options.authorize === false ? { allowed: false } : { allowed: true, readAuthorization: { internalOnly: true } };
      },
      async rateLimit(input) {
        counters.rateLimit += 1;
        counters.rateInputs.push({ ...input });
        counters.order.push(`rateLimit:${input.rate_policy}:${input.key_id}`);
        const allowed = input.rate_policy === "mcp:sse"
          ? options.transportRateAllowed !== false
          : options.readRateAllowed !== false;
        return allowed ? { allowed: true } : { allowed: false, retryAfterSeconds: 3 };
      },
      async readPage(input) {
        counters.readPage += 1;
        counters.order.push(`readPage:${input.cursor ?? "start"}`);
        counters.readInputs.push({
          authorization: input.authorization,
          cursor: input.cursor,
          limit: input.limit,
        });
        if (options.readPageError !== undefined) {
          throw options.readPageError;
        }
        return page;
      },
      validatePage(value) {
        counters.validatePage += 1;
        counters.order.push("validatePage");
        return options.validatedPage === undefined ? JSON.stringify(value) : options.validatedPage;
      },
      async reauthorizeBeforeEmission() {
        counters.reauthorizeBeforeEmission += 1;
        counters.order.push("reauthorizeBeforeEmission");
        return options.reauthorize !== false;
      },
    },
  };
}

function meta(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    ...overrides,
  };
}

function post(
  rpcMethod: string,
  params: Record<string, unknown>,
  options: { id?: string | number; headerName?: string | undefined; headers?: Record<string, string | undefined> } = {},
): McpHttpRequest {
  const headers: Record<string, string | undefined> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    "Mcp-Method": rpcMethod,
    Authorization: "api-key-test-only",
    ...options.headers,
  };
  const name = options.headerName ?? (rpcMethod === "tools/call" ? params.name as string | undefined : undefined);
  if (name !== undefined) {
    headers["Mcp-Name"] = name;
  }
  return {
    method: "POST",
    headers,
    body: { jsonrpc: "2.0", id: options.id ?? "request-1", method: rpcMethod, params },
  };
}

function discoverRequest(options: Parameters<typeof post>[2] = {}): McpHttpRequest {
  return post("server/discover", { _meta: meta() }, options);
}

function listRequest(options: Parameters<typeof post>[2] = {}): McpHttpRequest {
  return post("tools/list", { _meta: meta() }, options);
}

function callRequest(
  arguments_: Record<string, unknown> = {},
  toolName = SYNTHESIZED_MEMORY_READ_TOOL,
  options: Parameters<typeof post>[2] = {},
): McpHttpRequest {
  return post("tools/call", { name: toolName, arguments: arguments_, _meta: meta() }, options);
}

function rpcBody(response: { body?: unknown }): Record<string, unknown> {
  expect(response.body).toBeDefined();
  return response.body as Record<string, unknown>;
}

function errorCode(response: { body?: unknown }): number {
  return ((rpcBody(response).error as Record<string, unknown>).code) as number;
}

describe("MCP 2026-07-28 synthesized read handler", () => {
  test("A1 requires a single self-describing POST and API-key authentication before any grant/read work", async () => {
    const unauthenticated = fixture({ authenticated: false });
    const response = await createMcpProtocolHandler(unauthenticated.ports).handleHttp(callRequest());

    expect(response.status).toBe(401);
    expect(unauthenticated.counters).toMatchObject({ authenticate: 1, authorize: 0, rateLimit: 0, readPage: 0 });
    expect(unauthenticated.counters.order).toEqual(["authenticate:mcp_api_key"]);

    const batch = fixture();
    const batchResponse = await createMcpProtocolHandler(batch.ports).handleHttp({
      method: "POST",
      headers: {},
      body: [callRequest().body],
    });
    expect(batchResponse.status).toBe(400);
    expect(errorCode(batchResponse)).toBe(-32600);
    expect(batch.counters.authenticate).toBe(0);

    const wrongMethod = await createMcpProtocolHandler(fixture().ports).handleHttp({
      ...callRequest(),
      method: "GET",
    });
    expect(wrongMethod.status).toBe(405);
  });

  test("A2 implements modern discovery and removes initialize/notification/SSE-era methods", async () => {
    const { ports, counters } = fixture();
    const handler = createMcpProtocolHandler(ports);

    const discovery = await handler.handleHttp(discoverRequest());
    const discovered = rpcBody(discovery).result as Record<string, unknown>;
    expect(discovery.status).toBe(200);
    expect(discovered).toMatchObject({
      resultType: "complete",
      supportedVersions: [MCP_PROTOCOL_VERSION],
      ttlMs: 0,
      cacheScope: "private",
    });

    const initialize = await handler.handleHttp(post("initialize", { _meta: meta() }));
    expect(initialize.status).toBe(404);
    expect(errorCode(initialize)).toBe(-32601);
    expect(counters).toMatchObject({ authorize: 0, rateLimit: 1, readPage: 0 });
    expect(counters.rateInputs[0]).toMatchObject({ rate_policy: "mcp:sse", log_on_failure: true });

    const notification = await createMcpProtocolHandler(fixture().ports).handleHttp({
      method: "POST",
      headers: {
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "Mcp-Method": "notifications/initialized",
      },
      body: { jsonrpc: "2.0", method: "notifications/initialized", params: { _meta: meta() } },
    });
    expect(notification.status).toBe(400);
    expect(errorCode(notification)).toBe(-32600);

    const sseOnlyAttempt = await createMcpProtocolHandler(fixture().ports).handleHttp(listRequest({
      headers: { Accept: "text/event-stream" },
    }));
    expect(sseOnlyAttempt.status).toBe(400);
    expect(errorCode(sseOnlyAttempt)).toBe(-32600);
  });

  test("A4 uses the exact declared per-key rate tuple before any read", async () => {
    const { ports, counters } = fixture({ readRateAllowed: false });
    const response = await createMcpProtocolHandler(ports).handleHttp(callRequest());

    expect(errorCode(response)).toBe(-32029);
    expect(counters).toMatchObject({ readPage: 0, validatePage: 0, reauthorizeBeforeEmission: 0 });
    expect(counters.order).toEqual([
      "authenticate:mcp_api_key",
      "rateLimit:mcp:sse:key-1",
      "authorize",
      `rateLimit:${SYNTHESIZED_MEMORY_READ_RATE_POLICY}:key-1`,
    ]);
    expect(counters.rateInputs).toEqual([{
      prefix: "mcp",
      uid: "owner-1",
      app_id: "app-1",
      key_id: "key-1",
      rate_policy: "mcp:sse",
      log_on_failure: true,
    }, {
      prefix: "mcp",
      uid: "owner-1",
      app_id: "app-1",
      key_id: "key-1",
      scope: SYNTHESIZED_MEMORY_READ_SCOPE,
      rate_policy: SYNTHESIZED_MEMORY_READ_RATE_POLICY,
      log_on_failure: true,
    }]);
  });

  test("A5 uses the transport ring for list/call and the read ring only before call data", async () => {
    const denied = fixture({ readRateAllowed: false });
    const handler = createMcpProtocolHandler(denied.ports);
    const list = await handler.handleHttp(listRequest());
    const call = await handler.handleHttp(callRequest());
    const tools = (rpcBody(list).result as Record<string, unknown>).tools as Array<Record<string, unknown>>;

    expect(tools).toHaveLength(1);
    expect(errorCode(call)).toBe(-32029);
    expect(denied.counters).toMatchObject({ authorize: 2, rateLimit: 3, readPage: 0 });
    expect(denied.counters.rateInputs.map((input) => input.rate_policy)).toEqual([
      "mcp:sse",
      "mcp:sse",
      "mcp:memories_read",
    ]);

    const noGrant = fixture({ authorize: false });
    const noGrantHandler = createMcpProtocolHandler(noGrant.ports);
    const noGrantList = await noGrantHandler.handleHttp(listRequest());
    const noGrantCall = await noGrantHandler.handleHttp(callRequest());
    expect(((rpcBody(noGrantList).result as Record<string, unknown>).tools as unknown[])).toEqual([]);
    expect(errorCode(noGrantCall)).toBe(-32602);
    expect(noGrant.counters).toMatchObject({ authorize: 2, rateLimit: 2, readPage: 0 });

    const allowed = fixture();
    const listed = await createMcpProtocolHandler(allowed.ports).handleHttp(listRequest());
    const listedResult = rpcBody(listed).result as Record<string, unknown>;
    const listedTool = (listedResult.tools as Array<Record<string, unknown>>)[0];
    expect(listedResult).toMatchObject({ resultType: "complete", ttlMs: 0, cacheScope: "private" });
    expect(Object.hasOwn(listedTool, "securitySchemes")).toBe(false);
  });

  test("A7 validates exact headers and request metadata, with protocol errors at HTTP 400", async () => {
    const { ports, counters } = fixture();
    const handler = createMcpProtocolHandler(ports);

    const mismatchedName = await handler.handleHttp(callRequest({}, SYNTHESIZED_MEMORY_READ_TOOL, { headerName: "other" }));
    expect(mismatchedName.status).toBe(400);
    expect(errorCode(mismatchedName)).toBe(-32020);

    const missingVersion = await handler.handleHttp(post("tools/list", { _meta: meta() }, {
      headers: { "MCP-Protocol-Version": undefined },
    }));
    expect(missingVersion.status).toBe(400);
    expect(errorCode(missingVersion)).toBe(-32020);

    const namedDiscovery = await handler.handleHttp(discoverRequest({ headerName: "not-allowed" }));
    expect(namedDiscovery.status).toBe(400);
    expect(errorCode(namedDiscovery)).toBe(-32020);

    const badMeta = await handler.handleHttp(post("tools/list", {
      _meta: meta({ "io.modelcontextprotocol/logLevel": "too-loud" }),
    }));
    expect(badMeta.status).toBe(400);
    expect(errorCode(badMeta)).toBe(-32602);

    const unsupported = await handler.handleHttp(post("tools/list", { _meta: meta() }, {
      headers: { "MCP-Protocol-Version": "2025-11-25" },
    }));
    expect(unsupported.status).toBe(400);
    expect(errorCode(unsupported)).toBe(-32022);

    const unknown = await handler.handleHttp(post("prompts/list", { _meta: meta() }));
    expect(unknown.status).toBe(404);
    expect(errorCode(unknown)).toBe(-32601);
    expect(counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });
  });

  test("T1 rejects an invalid Origin before content negotiation and requires the Streamable HTTP POST envelope", async () => {
    const blocked = fixture({ originAllowed: false });
    const originResponse = await createMcpProtocolHandler(blocked.ports).handleHttp(listRequest({
      headers: {
        Origin: "https://attacker.invalid",
        "Content-Type": "text/plain",
        Accept: "text/event-stream",
      },
    }));
    expect(originResponse.status).toBe(403);
    expect(errorCode(originResponse)).toBe(-32600);
    expect(blocked.counters).toMatchObject({ validateOrigin: 1, authenticate: 0, rateLimit: 0 });

    const malformedContent = fixture();
    const malformedContentResponse = await createMcpProtocolHandler(malformedContent.ports).handleHttp(listRequest({
      headers: { "Content-Type": "text/plain" },
    }));
    expect(malformedContentResponse.status).toBe(400);
    expect(errorCode(malformedContentResponse)).toBe(-32600);
    expect(malformedContent.counters).toMatchObject({ authenticate: 0, rateLimit: 0 });

    const jsonOnly = fixture();
    const jsonOnlyResponse = await createMcpProtocolHandler(jsonOnly.ports).handleHttp(listRequest({
      headers: { Accept: "application/json" },
    }));
    expect(jsonOnlyResponse.status).toBe(400);
    expect(errorCode(jsonOnlyResponse)).toBe(-32600);
    expect(jsonOnly.counters).toMatchObject({ authenticate: 0, rateLimit: 0 });

    const validOrigin = fixture();
    const accepted = await createMcpProtocolHandler(validOrigin.ports).handleHttp(discoverRequest({
      headers: { Origin: "https://trusted.example" },
    }));
    expect(accepted.status).toBe(200);
    expect(validOrigin.counters.validateOrigin).toBe(1);
  });

  test("T2 accepts valid modern request metadata and never reflects it", async () => {
    // domain-pending(DIV-DOMX-002): extension metadata may describe a caller
    // surface, but this transport deliberately does not project it downstream.
    const metadata = {
      "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
      "io.modelcontextprotocol/clientInfo": {
        name: "valid-client",
        version: "1.0.0",
        title: "Valid Client",
      },
      "io.modelcontextprotocol/clientCapabilities": {
        roots: {},
        extensions: { "com.example/mcp-surface": { enabled: true } },
      },
      progressToken: 7,
      "io.modelcontextprotocol/logLevel": "info",
      "com.example/request-surface": { secret: "must-not-reflect" },
    };
    const response = await createMcpProtocolHandler(fixture().ports).handleHttp(post("server/discover", { _meta: metadata }));

    expect(response.status).toBe(200);
    expect(JSON.stringify(response.body)).not.toContain("must-not-reflect");
    expect(JSON.stringify(response.body)).not.toContain("request-surface");
    expect(JSON.stringify(response.body)).not.toContain("progressToken");
  });

  test("T3 accepts the schema's optional tools/list cursor and omitted tools/call arguments", async () => {
    const listed = await createMcpProtocolHandler(fixture().ports).handleHttp(post("tools/list", {
      _meta: meta(),
      cursor: "opaque-list-cursor",
    }));
    expect(listed.status).toBe(200);
    expect(((rpcBody(listed).result as Record<string, unknown>).tools as unknown[])).toHaveLength(1);

    const called = fixture();
    const calledResponse = await createMcpProtocolHandler(called.ports).handleHttp(post("tools/call", {
      _meta: meta(),
      name: SYNTHESIZED_MEMORY_READ_TOOL,
    }));
    expect(calledResponse.status).toBe(200);
    expect(called.counters.readPage).toBe(1);
  });

  test("T4 fails closed when a rate-limit dependency returns null or a malformed decision", async () => {
    const nullDecision = fixture();
    nullDecision.ports.rateLimit = async () => null as never;
    const nullResponse = await createMcpProtocolHandler(nullDecision.ports).handleHttp(callRequest());
    expect(errorCode(nullResponse)).toBe(-32603);
    expect(nullDecision.counters.readPage).toBe(0);

    const malformedDecision = fixture();
    let callCount = 0;
    malformedDecision.ports.rateLimit = async () => {
      callCount += 1;
      return callCount === 1 ? { allowed: true } : { allowed: true, smuggled: true } as never;
    };
    const malformedResponse = await createMcpProtocolHandler(malformedDecision.ports).handleHttp(callRequest());
    expect(errorCode(malformedResponse)).toBe(-32603);
    expect(malformedDecision.counters.readPage).toBe(0);
  });

  test("T5 rejects malformed cursor syntax before authorization or readPage", async () => {
    for (const malformed of ["", "   ", "x".repeat(4097), 7]) {
      const dependency = fixture();
      const response = await createMcpProtocolHandler(dependency.ports).handleHttp(
        callRequest({ cursor: malformed }),
      );
      expect(response.status).toBe(400);
      expect(errorCode(response)).toBe(-32602);
      expect(dependency.counters).toMatchObject({ authorize: 0, readPage: 0, validatePage: 0, reauthorizeBeforeEmission: 0 });
    }
  });

  test("T6 accepts only an exact authorization decision with a real read authorization", async () => {
    for (const decision of [
      { allowed: true, readAuthorization: null },
      { allowed: true, readAuthorization: {}, smuggled: true },
      { allowed: false, readAuthorization: { smuggled: true } },
    ]) {
      const authorization = fixture();
      authorization.ports.authorize = async () => decision as never;
      const response = await createMcpProtocolHandler(authorization.ports).handleHttp(callRequest());
      expect(errorCode(response)).toBe(-32602);
      expect(authorization.counters).toMatchObject({ readPage: 0, validatePage: 0, reauthorizeBeforeEmission: 0 });
    }
  });

  test("T7 snapshots credential routing data before rate limiting and authorization", async () => {
    const snapshot = fixture();
    const rawCredential = {
      kind: "mcp_api_key" as const,
      scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
      rateLimitKey: { prefix: "mcp" as const, uid: "owner-1", app_id: "app-1", key_id: "key-1" },
      authentication: { adapterOnly: true },
    } satisfies McpCredential;
    let authorizedCredential: McpCredential | undefined;
    const originalRateLimit = snapshot.ports.rateLimit;
    snapshot.ports.authenticate = async () => rawCredential;
    snapshot.ports.rateLimit = async (input) => {
      if (input.rate_policy === "mcp:sse") {
        rawCredential.scopes.length = 0;
        rawCredential.rateLimitKey.key_id = "raced-key";
        rawCredential.authentication.adapterOnly = false;
      }
      return originalRateLimit(input);
    };
    snapshot.ports.authorize = async ({ credential }) => {
      authorizedCredential = credential;
      return { allowed: true, readAuthorization: { adapterOnly: true } };
    };

    const response = await createMcpProtocolHandler(snapshot.ports).handleHttp(callRequest());
    expect(response.status).toBe(200);
    expect(snapshot.counters.rateInputs[0]).toMatchObject({ key_id: "key-1" });
    expect(authorizedCredential).toBeDefined();
    expect(authorizedCredential?.scopes).toEqual([SYNTHESIZED_MEMORY_READ_SCOPE]);
    expect(authorizedCredential?.rateLimitKey.key_id).toBe("key-1");
    expect((authorizedCredential?.authentication as { adapterOnly: boolean }).adapterOnly).toBe(true);
    expect(Object.hasOwn(authorizedCredential as object, "cursorBindings")).toBe(false);
    expect(Object.isFrozen(authorizedCredential)).toBe(true);
    expect(Object.isFrozen(authorizedCredential?.rateLimitKey)).toBe(true);
  });

  test("T7b rejects credential and authorization accessors without invoking a safe-to-evil swap getter", async () => {
    const credentialDependency = fixture();
    let rateLimitKeyGetterCalls = 0;
    const credentialWithAccessor = {
      kind: "mcp_api_key",
      scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
      authentication: { adapterOnly: true },
    };
    Object.defineProperty(credentialWithAccessor, "rateLimitKey", {
      enumerable: true,
      get() {
        rateLimitKeyGetterCalls += 1;
        return rateLimitKeyGetterCalls === 1
          ? { prefix: "mcp", uid: "owner-1", app_id: "app-1", key_id: "safe-key" }
          : { prefix: "mcp", uid: "owner-evil", app_id: "app-evil", key_id: "evil-key" };
      },
    });
    credentialDependency.ports.authenticate = async () => credentialWithAccessor as never;
    const credentialResponse = await createMcpProtocolHandler(credentialDependency.ports).handleHttp(callRequest());
    expect(credentialResponse.status).toBe(401);
    expect(rateLimitKeyGetterCalls).toBe(0);
    expect(credentialDependency.counters).toMatchObject({ rateLimit: 0, authorize: 0, readPage: 0 });

    const authorizationDependency = fixture();
    let readAuthorizationGetterCalls = 0;
    const authorizationWithAccessor = { allowed: true };
    Object.defineProperty(authorizationWithAccessor, "readAuthorization", {
      enumerable: true,
      get() {
        readAuthorizationGetterCalls += 1;
        return readAuthorizationGetterCalls === 1
          ? { readToken: "safe" }
          : { readToken: "evil" };
      },
    });
    authorizationDependency.ports.authorize = async () => authorizationWithAccessor as never;
    const authorizationResponse = await createMcpProtocolHandler(authorizationDependency.ports).handleHttp(callRequest());
    expect(errorCode(authorizationResponse)).toBe(-32602);
    expect(readAuthorizationGetterCalls).toBe(0);
    expect(authorizationDependency.counters).toMatchObject({ readPage: 0, validatePage: 0, reauthorizeBeforeEmission: 0 });
  });

  test("T7c rejects credential and authorization proxies without invoking their traps", async () => {
    const credentialDependency = fixture();
    let credentialTrapCalls = 0;
    const credentialProxy = new Proxy({
      kind: "mcp_api_key",
      scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
      rateLimitKey: { prefix: "mcp", uid: "owner-1", app_id: "app-1", key_id: "key-1" },
      authentication: { adapterOnly: true },
    }, {
      getPrototypeOf() {
        credentialTrapCalls += 1;
        return Object.prototype;
      },
      ownKeys() {
        credentialTrapCalls += 1;
        return [];
      },
    });
    credentialDependency.ports.authenticate = async () => credentialProxy as never;
    const credentialResponse = await createMcpProtocolHandler(credentialDependency.ports).handleHttp(callRequest());
    expect(credentialResponse.status).toBe(401);
    expect(credentialTrapCalls).toBe(0);
    expect(credentialDependency.counters).toMatchObject({ rateLimit: 0, authorize: 0, readPage: 0 });

    const authorizationDependency = fixture();
    let authorizationTrapCalls = 0;
    const authorizationProxy = new Proxy({
      allowed: true,
      readAuthorization: { readToken: "safe" },
    }, {
      getPrototypeOf() {
        authorizationTrapCalls += 1;
        return Object.prototype;
      },
      ownKeys() {
        authorizationTrapCalls += 1;
        return [];
      },
    });
    authorizationDependency.ports.authorize = async () => authorizationProxy;
    const authorizationResponse = await createMcpProtocolHandler(authorizationDependency.ports).handleHttp(callRequest());
    expect(errorCode(authorizationResponse)).toBe(-32602);
    expect(authorizationTrapCalls).toBe(0);
    expect(authorizationDependency.counters).toMatchObject({ readPage: 0, validatePage: 0, reauthorizeBeforeEmission: 0 });
  });

  test("T8 returns a fresh tool descriptor graph for each tools/list response", async () => {
    const handler = createMcpProtocolHandler(fixture().ports);
    const first = await handler.handleHttp(listRequest());
    const firstTool = ((rpcBody(first).result as Record<string, unknown>).tools as ToolDescriptorForTest[])[0];
    firstTool.inputSchema.properties.cursor.minLength = 999;

    const second = await handler.handleHttp(listRequest());
    const secondTool = ((rpcBody(second).result as Record<string, unknown>).tools as ToolDescriptorForTest[])[0];
    expect(secondTool).not.toBe(firstTool);
    expect(secondTool.inputSchema.properties.cursor.minLength).toBe(1);
  });

  test("U0 passes syntactically valid cursor bytes to readPage unchanged after auth and rate gates", async () => {
    const { ports, counters } = fixture();
    const cursor = "mcp1.opaque-payload.opaque-signature";

    const response = await createMcpProtocolHandler(ports).handleHttp(
      callRequest({ cursor, limit: 37 }),
    );

    expect(response.status).toBe(200);
    expect(counters.readPage).toBe(1);
    expect(counters.readInputs).toEqual([{
      authorization: { internalOnly: true },
      cursor,
      limit: 37,
    }]);
    expect(Object.keys(counters.readInputs[0]).sort()).toEqual(["authorization", "cursor", "limit"]);
    expect(counters.order).toEqual([
      "authenticate:mcp_api_key",
      "rateLimit:mcp:sse:key-1",
      "authorize",
      `rateLimit:${SYNTHESIZED_MEMORY_READ_RATE_POLICY}:key-1`,
      `readPage:${cursor}`,
      "validatePage",
      "reauthorizeBeforeEmission",
    ]);
  });

  test("U1 maps only readPage InvalidMcpCursorError failures to the uniform invalid-cursor response", async () => {
    class ConstructedSubclass extends InvalidMcpCursorError {}
    const first = fixture({ readPageError: new InvalidMcpCursorError() });
    const second = fixture({ readPageError: new InvalidMcpCursorError() });
    const subclass = fixture({ readPageError: new ConstructedSubclass() });
    const firstResponse = await createMcpProtocolHandler(first.ports).handleHttp(
      callRequest({ cursor: "well-shaped-but-invalid-a" }, SYNTHESIZED_MEMORY_READ_TOOL, { id: "same" }),
    );
    const secondResponse = await createMcpProtocolHandler(second.ports).handleHttp(
      callRequest({ cursor: "well-shaped-but-invalid-b" }, SYNTHESIZED_MEMORY_READ_TOOL, { id: "same" }),
    );
    const subclassResponse = await createMcpProtocolHandler(subclass.ports).handleHttp(
      callRequest({ cursor: "well-shaped-but-invalid-subclass" }, SYNTHESIZED_MEMORY_READ_TOOL, { id: "same" }),
    );

    expect(firstResponse.status).toBe(400);
    expect(errorCode(firstResponse)).toBe(-32602);
    expect(rpcBody(firstResponse)).toEqual(rpcBody(secondResponse));
    expect(rpcBody(firstResponse)).toEqual(rpcBody(subclassResponse));
    expect(first.counters).toMatchObject({ readPage: 1, validatePage: 0, reauthorizeBeforeEmission: 0 });
    expect(second.counters).toMatchObject({ readPage: 1, validatePage: 0, reauthorizeBeforeEmission: 0 });
    expect(subclass.counters).toMatchObject({ readPage: 1, validatePage: 0, reauthorizeBeforeEmission: 0 });
  });

  test("U1b keeps non-cursor readPage failures internal", async () => {
    const failure = fixture({ readPageError: new Error("storage unavailable") });
    const response = await createMcpProtocolHandler(failure.ports).handleHttp(
      callRequest({ cursor: "well-shaped-cursor" }),
    );

    expect(response.status).toBe(200);
    expect(errorCode(response)).toBe(-32603);
    expect(failure.counters).toMatchObject({ readPage: 1, validatePage: 0, reauthorizeBeforeEmission: 0 });
  });

  test("U1c keeps invalid-cursor lookalikes internal without executing accessors or proxy traps", async () => {
    class ConstructedSubclass extends InvalidMcpCursorError {}

    const rewrittenPrototype = Object.setPrototypeOf(
      new Error("prototype spoof"),
      InvalidMcpCursorError.prototype,
    );
    let accessorCalls = 0;
    const accessorShape = {};
    Object.defineProperty(accessorShape, "code", {
      enumerable: true,
      get() {
        accessorCalls += 1;
        return "invalid_cursor";
      },
    });
    let proxyTrapCalls = 0;
    const proxyShape = new Proxy(new InvalidMcpCursorError(), {
      get() {
        proxyTrapCalls += 1;
        return "invalid_cursor";
      },
      getPrototypeOf() {
        proxyTrapCalls += 1;
        return InvalidMcpCursorError.prototype;
      },
      ownKeys() {
        proxyTrapCalls += 1;
        return [];
      },
    });

    for (const spoof of [
      Object.create(InvalidMcpCursorError.prototype),
      { code: "invalid_cursor" },
      rewrittenPrototype,
      Object.create(ConstructedSubclass.prototype),
      accessorShape,
      proxyShape,
    ]) {
      const failure = fixture({ readPageError: spoof });
      const response = await createMcpProtocolHandler(failure.ports).handleHttp(
        callRequest({ cursor: "well-shaped-cursor" }),
      );
      expect(response.status).toBe(200);
      expect(errorCode(response)).toBe(-32603);
      expect(failure.counters).toMatchObject({ readPage: 1, validatePage: 0, reauthorizeBeforeEmission: 0 });
    }
    expect(accessorCalls).toBe(0);
    expect(proxyTrapCalls).toBe(0);
  });

  test("U2 rejects credential extras, including auth-time cursor state, before authorization", async () => {
    const unknownCredential = fixture();
    unknownCredential.ports.authenticate = async () => ({
      kind: "mcp_api_key",
      scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
      rateLimitKey: { prefix: "mcp", uid: "owner-1", app_id: "app-1", key_id: "key-1", extra: "reject" },
      authentication: null,
    } as never);
    const credentialResponse = await createMcpProtocolHandler(unknownCredential.ports).handleHttp(callRequest());
    expect(credentialResponse.status).toBe(401);
    expect(unknownCredential.counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });

    const authTimeCursorState = fixture();
    authTimeCursorState.ports.authenticate = async () => ({
      kind: "mcp_api_key",
      scopes: [SYNTHESIZED_MEMORY_READ_SCOPE],
      rateLimitKey: { prefix: "mcp", uid: "owner-1", app_id: "app-1", key_id: "key-1" },
      cursorBindings: { dishonestAuthTimeStub: true },
      authentication: null,
    } as never);
    const cursorStateResponse = await createMcpProtocolHandler(authTimeCursorState.ports).handleHttp(callRequest());
    expect(cursorStateResponse.status).toBe(401);
    expect(authTimeCursorState.counters).toMatchObject({ authorize: 0, rateLimit: 0, readPage: 0 });
  });

  test("S3 leaves a hidden and unknown tool indistinguishable to an unscoped caller", async () => {
    const hidden = fixture({ scopes: [] });
    const unknown = fixture({ scopes: [] });
    const hiddenResponse = await createMcpProtocolHandler(hidden.ports).handleHttp(callRequest({}, SYNTHESIZED_MEMORY_READ_TOOL, { id: "same" }));
    const unknownResponse = await createMcpProtocolHandler(unknown.ports).handleHttp(callRequest({}, "unknown_tool", { id: "same" }));

    expect(rpcBody(hiddenResponse)).toEqual(rpcBody(unknownResponse));
    expect(hidden.counters).toMatchObject({ authorize: 0, rateLimit: 1, readPage: 0 });
    expect(unknown.counters).toMatchObject({ authorize: 0, rateLimit: 1, readPage: 0 });
  });

  test("S4 emits the immutable contract-parser snapshot and reauthorizes immediately before positive bytes", async () => {
    const snapshot = fixture();
    const mutablePage: Record<string, unknown> = { text: "before" };
    snapshot.ports.readPage = async () => mutablePage;
    snapshot.ports.validatePage = () => {
      mutablePage.text = "raw-after-validation";
      return "{\"text\":\"immutable-contract-snapshot\"}";
    };
    const snapshotResponse = await createMcpProtocolHandler(snapshot.ports).handleHttp(callRequest());
    const snapshotResult = rpcBody(snapshotResponse).result as Record<string, unknown>;
    const snapshotContent = ((snapshotResult.content as Array<Record<string, unknown>>)[0].text) as string;
    expect(snapshotResult.resultType).toBe("complete");
    expect(snapshotContent).toBe("{\"text\":\"immutable-contract-snapshot\"}");
    expect(JSON.stringify(snapshotResponse.body)).not.toContain("raw-after-validation");
    expect(snapshot.counters.reauthorizeBeforeEmission).toBe(1);

    const revoked = fixture({ reauthorize: false });
    const revokedResponse = await createMcpProtocolHandler(revoked.ports).handleHttp(callRequest());
    expect(errorCode(revokedResponse)).toBe(-32003);
    expect(JSON.stringify(revokedResponse.body)).not.toContain("Synthesized result");
    expect(revoked.counters).toMatchObject({ readPage: 1, validatePage: 1, reauthorizeBeforeEmission: 1 });
  });

  test("FEAT-AUTH-013 keeps otherwise identical API keys in separate rate buckets", async () => {
    const first = fixture({ uid: "owner-1", app_id: "app-1", key_id: "key-a" });
    const second = fixture({ uid: "owner-1", app_id: "app-1", key_id: "key-b" });

    await createMcpProtocolHandler(first.ports).handleHttp(callRequest());
    await createMcpProtocolHandler(second.ports).handleHttp(callRequest());

    const firstRead = first.counters.rateInputs.find((input) => input.rate_policy === "mcp:memories_read");
    const secondRead = second.counters.rateInputs.find((input) => input.rate_policy === "mcp:memories_read");
    expect(firstRead).toMatchObject({ key_id: "key-a", rate_policy: "mcp:memories_read", log_on_failure: true });
    expect(secondRead).toMatchObject({ key_id: "key-b", rate_policy: "mcp:memories_read", log_on_failure: true });
    expect(firstRead).not.toEqual(secondRead);
  });
});
