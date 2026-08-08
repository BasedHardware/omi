/**
 * Protocol-native MCP transport seam.
 *
 * This module deliberately has no HTTP framework, storage, credential, or
 * contract-package dependency. The edge adapter supplies all of those through
 * ports so this surface can be exercised before an edge runtime is selected.
 */

// domain-pending(DIV-DOMCORE-001): "memory" is legacy terminology until the
// read-contract vocabulary is ratified.
// domain-pending(DIV-DOMCORE-008): the synthesized projection's atom name is
// still pending; do not turn this transport label into a domain type.
export const SYNTHESIZED_MEMORY_READ_TOOL = "read_synthesized_memory";
export const SYNTHESIZED_MEMORY_READ_SCOPE = "memories.read";
export const SYNTHESIZED_MEMORY_READ_RATE_POLICY = "mcp.synthesized-memory.read";
export const MCP_PROTOCOL_VERSION = "2025-03-26";

export interface CursorBindings {
  ownerAuthorizationDigest: string;
  // domain-pending(DIV-DOMAPPS-001): "app" remains a legacy public label
  // while its plugin-era persistence terminology is unresolved.
  // domain-pending(DIV-DOMAPPS-006): "app" and "key" are legacy labels for
  // two incompatible credential systems. This transport receives digests only.
  appAuthorizationDigest: string;
  // domain-pending(DIV-DOMAPPS-006): see appAuthorizationDigest above.
  keyAuthorizationDigest: string;
  graphGenerationDigest: string;
  projectionGenerationDigest: string;
  filterDigest: string;
  readModeDigest: string;
}

/** Authentication is opaque to the protocol and is never serialized. */
export interface McpCredential {
  readonly scopes: readonly string[];
  readonly rateLimitIdentity: string;
  readonly cursorBindings: CursorBindings;
  readonly authentication: unknown;
}

export interface McpToolDefinition {
  readonly name: typeof SYNTHESIZED_MEMORY_READ_TOOL;
  readonly requiredScope: typeof SYNTHESIZED_MEMORY_READ_SCOPE;
  readonly ratePolicy: typeof SYNTHESIZED_MEMORY_READ_RATE_POLICY;
}

// domain-pending(DIV-DOMX-006): this is the request-time authorization result,
// not a decision to name it a persisted "grant".
export type AuthorizationDecision =
  | { readonly allowed: true; readonly readAuthorization: unknown }
  | { readonly allowed: false };

type GrantedAuthorization = Extract<AuthorizationDecision, { readonly allowed: true }>;

export type RateLimitDecision =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly retryAfterSeconds?: number };

export interface McpProtocolPorts {
  authenticate(input: { readonly authorizationHeader: string | undefined }): Promise<McpCredential | null>;
  authorize(input: {
    readonly credential: McpCredential;
    readonly tool: McpToolDefinition;
  }): Promise<AuthorizationDecision>;
  rateLimit(input: {
    readonly credential: McpCredential;
    readonly declaredPolicy: typeof SYNTHESIZED_MEMORY_READ_RATE_POLICY;
  }): Promise<RateLimitDecision>;
  readPage(input: {
    readonly authorization: unknown;
    readonly afterVisibleKey: string | null;
    readonly limit: number;
    readonly issueCursor: (lastVisibleKey: string) => string;
  }): Promise<unknown>;
  /**
   * The Track 1 contract package owns this validator. Keeping the value
   * opaque here avoids a second public page/Memory DTO in the MCP transport.
   */
  validatePage(page: unknown): boolean;
  cursor: {
    parse(input: { readonly cursor: string; readonly bindings: CursorBindings }): { readonly lastVisibleKey: string };
    issue(input: { readonly lastVisibleKey: string; readonly bindings: CursorBindings }): string;
  };
}

export interface McpHttpRequest {
  readonly authorization?: string;
  readonly accept?: string;
  /** The caller parses bytes; this handler owns JSON-RPC validation. */
  readonly body: unknown;
}

export interface McpHttpResponse {
  readonly status: 200 | 202 | 401;
  readonly headers: Readonly<Record<string, string>>;
  readonly body?: unknown;
}

type RpcId = string | number | null;

interface RpcRequest {
  readonly jsonrpc: "2.0";
  readonly method: string;
  readonly id?: RpcId;
  readonly params?: unknown;
}

interface RpcResponse {
  readonly jsonrpc: "2.0";
  readonly id: RpcId;
  readonly result?: unknown;
  readonly error?: { readonly code: number; readonly message: string; readonly data?: unknown };
}

const TOOL: McpToolDefinition = {
  name: SYNTHESIZED_MEMORY_READ_TOOL,
  requiredScope: SYNTHESIZED_MEMORY_READ_SCOPE,
  ratePolicy: SYNTHESIZED_MEMORY_READ_RATE_POLICY,
};

const TOOL_DESCRIPTOR = {
  name: TOOL.name,
  description: "Read the authorized synthesized projection.",
  inputSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      cursor: { type: "string", minLength: 1, maxLength: 4096 },
      limit: { type: "integer", minimum: 1, maximum: 100 },
    },
  },
  annotations: {
    readOnlyHint: true,
    destructiveHint: false,
    openWorldHint: false,
  },
  securitySchemes: [{ type: "oauth2", scopes: [TOOL.requiredScope] }],
} as const;

const JSON_HEADERS = Object.freeze({
  "content-type": "application/json",
  "mcp-protocol-version": MCP_PROTOCOL_VERSION,
});

const SSE_HEADERS = Object.freeze({
  "content-type": "text/event-stream",
  "cache-control": "no-cache",
  "mcp-protocol-version": MCP_PROTOCOL_VERSION,
});

export function createMcpProtocolHandler(ports: McpProtocolPorts): {
  handleHttp(request: McpHttpRequest): Promise<McpHttpResponse>;
} {
  return {
    async handleHttp(request: McpHttpRequest): Promise<McpHttpResponse> {
      let credential: McpCredential | null;
      try {
        // Authenticate before inspecting request body or dispatching a method.
        const authenticated = await ports.authenticate({ authorizationHeader: request.authorization });
        credential = isCredential(authenticated) ? authenticated : null;
      } catch {
        credential = null;
      }

      if (credential === null) {
        return {
          status: 401,
          headers: JSON_HEADERS,
          body: { error: "authentication_required" },
        };
      }

      const isBatch = Array.isArray(request.body);
      const messages = isBatch ? request.body : [request.body];
      const responses: Array<RpcResponse | null> = [];
      if (messages.length === 0) {
        responses.push(invalidRequest());
      } else {
        for (const message of messages) {
          responses.push(await dispatch(ports, credential, message));
        }
      }
      const emitted = responses.filter((response): response is RpcResponse => response !== null);

      if (emitted.length === 0) {
        return { status: 202, headers: JSON_HEADERS };
      }

      const body = isBatch ? emitted : emitted[0];
      if (acceptsSse(request.accept)) {
        return {
          status: 200,
          headers: SSE_HEADERS,
          body: `event: message\ndata: ${JSON.stringify(body)}\n\n`,
        };
      }

      return { status: 200, headers: JSON_HEADERS, body };
    },
  };
}

async function dispatch(
  ports: McpProtocolPorts,
  credential: McpCredential,
  input: unknown,
): Promise<RpcResponse | null> {
  const request = parseRequest(input);
  if (request === null) {
    return invalidRequest();
  }

  const isNotification = !Object.hasOwn(request, "id");
  if (isNotification) {
    // A notification must never produce a JSON-RPC response. We deliberately
    // do not execute tool calls as notifications because a read would have no
    // observable result and could consume a credential's quota unexpectedly.
    return null;
  }

  switch (request.method) {
    case "initialize":
      return success(request.id ?? null, {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "omi-platform-mcp", version: "0.0.0" },
      });
    case "ping":
      return success(request.id ?? null, {});
    case "tools/list":
      return listTools(ports, credential, request);
    case "tools/call":
      return callTool(ports, credential, request);
    default:
      return error(request.id ?? null, -32601, "Method not found");
  }
}

async function listTools(
  ports: McpProtocolPorts,
  credential: McpCredential,
  request: RpcRequest,
): Promise<RpcResponse> {
  if (request.params !== undefined && !isRecord(request.params)) {
    return error(request.id ?? null, -32602, "Invalid params");
  }

  const decision = await gateTool(ports, credential);
  return success(request.id ?? null, { tools: decision === null ? [] : [TOOL_DESCRIPTOR] });
}

async function callTool(
  ports: McpProtocolPorts,
  credential: McpCredential,
  request: RpcRequest,
): Promise<RpcResponse> {
  const parsed = parseToolCall(request.params);
  if (parsed === null) {
    return error(request.id ?? null, -32602, "Invalid params");
  }
  if (parsed.name !== TOOL.name) {
    return error(request.id ?? null, -32602, "Unknown tool");
  }

  const authorization = await gateTool(ports, credential);
  if (authorization === null) {
    return insufficientScope(request.id ?? null);
  }

  let rate: RateLimitDecision;
  try {
    rate = await ports.rateLimit({ credential, declaredPolicy: TOOL.ratePolicy });
  } catch {
    return error(request.id ?? null, -32603, "Internal error");
  }
  if (rate.allowed !== true) {
    const retryAfterSeconds = isRecord(rate) ? validRetryAfter(rate.retryAfterSeconds as number | undefined) : undefined;
    return error(request.id ?? null, -32029, "Rate limit exceeded", retryAfterSeconds === undefined
      ? undefined
      : { retryAfterSeconds });
  }

  let afterVisibleKey: string | null = null;
  if (parsed.cursor !== undefined) {
    try {
      afterVisibleKey = ports.cursor.parse({ cursor: parsed.cursor, bindings: credential.cursorBindings }).lastVisibleKey;
    } catch {
      // The cursor port never returns or logs an invalid cursor payload.
      return error(request.id ?? null, -32602, "Invalid cursor");
    }
  }

  let page: unknown;
  try {
    page = await ports.readPage({
      authorization: authorization.readAuthorization,
      afterVisibleKey,
      limit: parsed.limit,
      issueCursor: (lastVisibleKey) => ports.cursor.issue({
        lastVisibleKey,
        bindings: credential.cursorBindings,
      }),
    });
  } catch {
    return error(request.id ?? null, -32603, "Internal error");
  }

  try {
    if (!ports.validatePage(page)) {
      return error(request.id ?? null, -32603, "Invalid synthesized projection");
    }
  } catch {
    return error(request.id ??null, -32603, "Invalid synthesized projection");
  }

  try {
    const serializedPage = JSON.stringify(page);
    if (typeof serializedPage !== "string") {
      return error(request.id ?? null, -32603, "Invalid synthesized projection");
    }
    return success(request.id ?? null, {
      content: [{ type: "text", text: serializedPage }],
    });
  } catch {
    return error(request.id ?? null, -32603, "Invalid synthesized projection");
  }
}

/** Returns the same eligibility gate for tools/list and tools/call. */
async function gateTool(ports: McpProtocolPorts, credential: McpCredential): Promise<GrantedAuthorization | null> {
  if (!credential.scopes.includes(TOOL.requiredScope)) {
    return null;
  }
  try {
    const decision = await ports.authorize({ credential, tool: TOOL });
    return isGrantedAuthorization(decision) ? decision : null;
  } catch {
    return null;
  }
}

function parseRequest(input: unknown): RpcRequest | null {
  if (!isRecord(input) || input.jsonrpc !== "2.0" || typeof input.method !== "string") {
    return null;
  }
  if (Object.hasOwn(input, "id") && !isRpcId(input.id)) {
    return null;
  }
  return input as RpcRequest;
}

function parseToolCall(input: unknown): { name: string; cursor?: string; limit: number } | null {
  if (!isRecord(input) || !hasOnlyKeys(input, ["name", "arguments"]) || typeof input.name !== "string") {
    return null;
  }
  const args = input.arguments === undefined ? {} : input.arguments;
  if (!isRecord(args) || !hasOnlyKeys(args, ["cursor", "limit"])) {
    return null;
  }
  if (args.cursor !== undefined && (typeof args.cursor !== "string" || args.cursor.length === 0 || args.cursor.length > 4096)) {
    return null;
  }
  if (args.limit !== undefined && (!Number.isInteger(args.limit) || args.limit < 1 || args.limit > 100)) {
    return null;
  }
  return {
    name: input.name,
    cursor: args.cursor as string | undefined,
    limit: (args.limit as number | undefined) ?? 20,
  };
}

function invalidRequest(): RpcResponse {
  return error(null, -32600, "Invalid Request");
}

function insufficientScope(id: RpcId): RpcResponse {
  return error(id, -32003, "Insufficient scope", {
    "mcp/www_authenticate": `Bearer scope="${TOOL.requiredScope}"`,
  });
}

function success(id: RpcId, result: unknown): RpcResponse {
  return { jsonrpc: "2.0", id, result };
}

function error(id: RpcId, code: number, message: string, data?: unknown): RpcResponse {
  return {
    jsonrpc: "2.0",
    id,
    error: data === undefined ? { code, message } : { code, message, data },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRpcId(value: unknown): value is RpcId {
  return value === null || typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
}

function isCredential(value: unknown): value is McpCredential {
  if (!isRecord(value) || !Array.isArray(value.scopes) || !value.scopes.every((scope) => typeof scope === "string")) {
    return false;
  }
  if (typeof value.rateLimitIdentity !== "string" || !isRecord(value.cursorBindings)) {
    return false;
  }
  const bindings = value.cursorBindings;
  return [
    "ownerAuthorizationDigest",
    "appAuthorizationDigest",
    "keyAuthorizationDigest",
    "graphGenerationDigest",
    "projectionGenerationDigest",
    "filterDigest",
    "readModeDigest",
  ].every((field) => typeof bindings[field] === "string");
}

function isGrantedAuthorization(value: unknown): value is GrantedAuthorization {
  return isRecord(value) && value.allowed === true && Object.hasOwn(value, "readAuthorization");
}

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key));
}

function validRetryAfter(value: number | undefined): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function acceptsSse(accept: string | undefined): boolean {
  return accept?.split(",").some((entry) => entry.trim().toLowerCase().startsWith("text/event-stream")) ?? false;
}
