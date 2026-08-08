/**
 * Stateless MCP 2026-07-28 HTTP/JSON-RPC seam.
 *
 * This is deliberately framework-, storage-, and SDK-free. The app adapter
 * supplies API-key authentication, grant checks, rate limiting, page reading,
 * contract parsing, cursor minting, and the final revocation fence.
 */

// domain-pending(DIV-DOMCORE-001): "memory" is legacy terminology until the
// read-contract vocabulary is ratified.
// domain-pending(DIV-DOMCORE-008): the synthesized projection's atom name is
// still pending; do not turn this transport label into a domain type.
export const SYNTHESIZED_MEMORY_READ_TOOL = "read_synthesized_memory";
export const SYNTHESIZED_MEMORY_READ_SCOPE = "memories.read";
export const SYNTHESIZED_MEMORY_READ_RATE_POLICY = "mcp:memories_read";
export const MCP_TRANSPORT_RATE_POLICY = "mcp:sse";
export const MCP_PROTOCOL_VERSION = "2026-07-28";

/** DIV-AUTH-005's one declared scope/rate/logging dependency. */
export interface McpScopedDependency {
  readonly scope: typeof SYNTHESIZED_MEMORY_READ_SCOPE;
  readonly rate_policy: typeof SYNTHESIZED_MEMORY_READ_RATE_POLICY;
  readonly log_on_failure: true;
}

export const SYNTHESIZED_MEMORY_READ_DEPENDENCY: McpScopedDependency = Object.freeze({
  scope: SYNTHESIZED_MEMORY_READ_SCOPE,
  rate_policy: SYNTHESIZED_MEMORY_READ_RATE_POLICY,
  log_on_failure: true,
});

export interface CursorBindings {
  readonly ownerAuthorizationDigest: string;
  // domain-pending(DIV-DOMAPPS-001): "app" remains a legacy public label
  // while its plugin-era persistence terminology is unresolved.
  // domain-pending(DIV-DOMAPPS-006): this transport receives digests only.
  readonly appAuthorizationDigest: string;
  // domain-pending(DIV-DOMAPPS-006): see appAuthorizationDigest above.
  readonly keyAuthorizationDigest: string;
  readonly graphGenerationDigest: string;
  readonly projectionGenerationDigest: string;
  readonly filterDigest: string;
  readonly readModeDigest: string;
}

export interface McpCredentialRateLimitKey {
  readonly prefix: "mcp";
  readonly uid: string;
  // domain-pending(DIV-DOMAPPS-001): "app" remains a legacy public label.
  // domain-pending(DIV-DOMAPPS-006): this is exact credential identity, not a
  // collapsed key-family label.
  readonly app_id: string;
  // domain-pending(DIV-DOMAPPS-006): see app_id above.
  readonly key_id: string;
}

/** API-key-only QA surface; this is never serialized onto the MCP wire. */
export interface McpCredential {
  readonly kind: "mcp_api_key";
  readonly scopes: readonly string[];
  readonly rateLimitKey: McpCredentialRateLimitKey;
  readonly cursorBindings: CursorBindings;
  readonly authentication: unknown;
}

export interface McpToolDefinition {
  readonly name: typeof SYNTHESIZED_MEMORY_READ_TOOL;
  readonly dependency: McpScopedDependency;
}

// domain-pending(DIV-DOMX-006): this is request-time authorization, not a
// decision to name it a persisted "grant".
export type AuthorizationDecision =
  | { readonly allowed: true; readonly readAuthorization: unknown }
  | { readonly allowed: false };

export type RateLimitDecision =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly retryAfterSeconds?: number };

type GrantedAuthorization = Extract<AuthorizationDecision, { readonly allowed: true }>;
type ToolGate =
  | { readonly kind: "allowed"; readonly authorization: GrantedAuthorization }
  | { readonly kind: "denied" };

type McpRateLimitInput =
  | {
    readonly prefix: "mcp";
    readonly uid: string;
    readonly app_id: string;
    readonly key_id: string;
    readonly rate_policy: typeof MCP_TRANSPORT_RATE_POLICY;
    readonly log_on_failure: true;
  }
  | {
    readonly prefix: "mcp";
    readonly uid: string;
    readonly app_id: string;
    readonly key_id: string;
    readonly scope: typeof SYNTHESIZED_MEMORY_READ_SCOPE;
    readonly rate_policy: typeof SYNTHESIZED_MEMORY_READ_RATE_POLICY;
    readonly log_on_failure: true;
  };

export interface McpProtocolPorts {
  authenticate(input: {
    readonly apiKeyHeader: string | undefined;
    readonly requiredKind: "mcp_api_key";
  }): Promise<McpCredential | null>;
  authorize(input: {
    readonly credential: McpCredential;
    readonly tool: McpToolDefinition;
  }): Promise<AuthorizationDecision>;
  /** FEAT-AUTH-013's exact per-credential tuple; no opaque shared bucket. */
  rateLimit(input: McpRateLimitInput): Promise<RateLimitDecision>;
  readPage(input: {
    readonly authorization: unknown;
    readonly afterVisibleKey: string | null;
    readonly limit: number;
    readonly issueCursor: (lastVisibleKey: string) => string;
  }): Promise<unknown>;
  /**
   * The Track 1 contract parser validates once and returns the bounded,
   * immutable JSON snapshot to emit. The handler never re-reads `page`.
   */
  validatePage(page: unknown): Promise<string | null> | string | null;
  /** Re-check scope plus persisted authorization immediately before bytes. */
  reauthorizeBeforeEmission(input: {
    readonly credential: McpCredential;
    readonly tool: McpToolDefinition;
  }): Promise<boolean>;
  cursor: {
    parse(input: { readonly cursor: string; readonly bindings: CursorBindings }): { readonly lastVisibleKey: string };
    issue(input: { readonly lastVisibleKey: string; readonly bindings: CursorBindings }): string;
  };
}

export interface McpHttpRequest {
  readonly method: string;
  readonly headers: Readonly<Record<string, string | undefined>>;
  readonly body: unknown;
}

export interface McpHttpResponse {
  readonly status: 200 | 400 | 401 | 404 | 405;
  readonly headers: Readonly<Record<string, string>>;
  readonly body?: unknown;
}

type RpcId = string | number;
interface RpcRequest {
  readonly jsonrpc: "2.0";
  readonly id: RpcId;
  readonly method: string;
  readonly params: Record<string, unknown>;
}
interface RpcResponse {
  readonly jsonrpc: "2.0";
  readonly id: RpcId | null;
  readonly result?: Record<string, unknown>;
  readonly error?: { readonly code: number; readonly message: string; readonly data?: unknown };
}

const TOOL: McpToolDefinition = {
  name: SYNTHESIZED_MEMORY_READ_TOOL,
  dependency: SYNTHESIZED_MEMORY_READ_DEPENDENCY,
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
} as const;

const JSON_HEADERS = Object.freeze({
  "content-type": "application/json",
  "mcp-protocol-version": MCP_PROTOCOL_VERSION,
});
const PRIVATE_CACHE = Object.freeze({ ttlMs: 0, cacheScope: "private" });
const MAX_VALIDATED_PAGE_BYTES = 1_000_000;

export function createMcpProtocolHandler(ports: McpProtocolPorts): {
  handleHttp(request: McpHttpRequest): Promise<McpHttpResponse>;
} {
  return {
    async handleHttp(request: McpHttpRequest): Promise<McpHttpResponse> {
      if (request.method !== "POST") {
        return { status: 405, headers: JSON_HEADERS };
      }
      if (Array.isArray(request.body)) {
        return rpcHttp(400, invalidRequest());
      }

      const rpc = parseRpcRequest(request.body);
      if (rpc === null) {
        return rpcHttp(400, invalidRequest());
      }
      const meta = parseRequestMeta(rpc.params);
      if (meta === null) {
        return rpcHttp(400, error(rpc.id, -32602, "Invalid params"));
      }

      const headerFailure = validateHeaders(request.headers, rpc, meta.protocolVersion);
      if (headerFailure !== null) {
        return rpcHttp(headerFailure.status, error(rpc.id, headerFailure.code, headerFailure.message, headerFailure.data));
      }

      let credential: McpCredential | null;
      try {
        credential = await ports.authenticate({
          apiKeyHeader: readHeader(request.headers, "authorization").value,
          requiredKind: "mcp_api_key",
        });
      } catch {
        credential = null;
      }
      if (!isCredential(credential)) {
        return { status: 401, headers: JSON_HEADERS, body: { error: "authentication_required" } };
      }

      if (rpc.method === "server/discover" || rpc.method === "tools/list" || rpc.method === "tools/call") {
        const transportRate = await applyTransportRateLimit(ports, credential, rpc.id);
        if (transportRate !== null) {
          return rpcHttp(200, transportRate);
        }
      }

      switch (rpc.method) {
        case "server/discover":
          return discover(rpc);
        case "tools/list":
          return listTools(ports, credential, rpc);
        case "tools/call":
          return callTool(ports, credential, rpc);
        default:
          return rpcHttp(404, error(rpc.id, -32601, "Method not found"));
      }
    },
  };
}

function discover(rpc: RpcRequest): McpHttpResponse {
  if (!hasExactKeys(rpc.params, ["_meta"])) {
    return rpcHttp(400, error(rpc.id, -32602, "Invalid params"));
  }
  return rpcHttp(200, success(rpc.id, {
    resultType: "complete",
    supportedVersions: [MCP_PROTOCOL_VERSION],
    capabilities: { tools: { listChanged: false } },
    serverInfo: { name: "omi-platform-mcp", version: "0.0.0" },
    ...PRIVATE_CACHE,
  }));
}

async function listTools(ports: McpProtocolPorts, credential: McpCredential, rpc: RpcRequest): Promise<McpHttpResponse> {
  if (!hasExactKeys(rpc.params, ["_meta"])) {
    return rpcHttp(400, error(rpc.id, -32602, "Invalid params"));
  }
  const gate = await visibilityGate(ports, credential);
  return rpcHttp(200, success(rpc.id, {
    resultType: "complete",
    tools: gate.kind === "allowed" ? [TOOL_DESCRIPTOR] : [],
    ...PRIVATE_CACHE,
  }));
}

async function callTool(ports: McpProtocolPorts, credential: McpCredential, rpc: RpcRequest): Promise<McpHttpResponse> {
  const call = parseToolCall(rpc.params);
  if (call === null) {
    return rpcHttp(400, error(rpc.id, -32602, "Invalid params"));
  }

  // Gate before deciding whether the name is known: an unscoped caller sees
  // identical error and work for a hidden known tool and an unknown one.
  const gate = await visibilityGate(ports, credential);
  if (gate.kind === "denied" || call.name !== TOOL.name) {
    return rpcHttp(200, error(rpc.id, -32602, "Tool unavailable"));
  }

  const readRate = await applyReadRateLimit(ports, credential, rpc.id);
  if (readRate !== null) {
    return rpcHttp(200, readRate);
  }

  let afterVisibleKey: string | null = null;
  if (call.cursor !== undefined) {
    try {
      afterVisibleKey = ports.cursor.parse({ cursor: call.cursor, bindings: credential.cursorBindings }).lastVisibleKey;
    } catch {
      return rpcHttp(400, error(rpc.id, -32602, "Invalid cursor"));
    }
  }

  let page: unknown;
  try {
    page = await ports.readPage({
      authorization: gate.authorization.readAuthorization,
      afterVisibleKey,
      limit: call.limit,
      issueCursor: (lastVisibleKey) => ports.cursor.issue({
        lastVisibleKey,
        bindings: credential.cursorBindings,
      }),
    });
  } catch {
    return rpcHttp(200, error(rpc.id, -32603, "Internal error"));
  }

  let validatedJson: string | null;
  try {
    validatedJson = await ports.validatePage(page);
  } catch {
    return rpcHttp(200, error(rpc.id, -32603, "Invalid synthesized projection"));
  }
  if (!isBoundedJsonSnapshot(validatedJson)) {
    return rpcHttp(200, error(rpc.id, -32603, "Invalid synthesized projection"));
  }

  try {
    if (await ports.reauthorizeBeforeEmission({ credential, tool: TOOL }) !== true) {
      return rpcHttp(200, error(rpc.id, -32003, "Access no longer permitted"));
    }
  } catch {
    return rpcHttp(200, error(rpc.id, -32003, "Access no longer permitted"));
  }

  return rpcHttp(200, success(rpc.id, {
    resultType: "complete",
    content: [{ type: "text", text: validatedJson }],
  }));
}

/** Exactly the same scope plus persisted-grant visibility gate for list/call. */
async function visibilityGate(ports: McpProtocolPorts, credential: McpCredential): Promise<ToolGate> {
  if (!credential.scopes.includes(TOOL.dependency.scope)) {
    return { kind: "denied" };
  }
  let authorization: AuthorizationDecision;
  try {
    authorization = await ports.authorize({ credential, tool: TOOL });
  } catch {
    return { kind: "denied" };
  }
  if (!isGrantedAuthorization(authorization)) {
    return { kind: "denied" };
  }

  return { kind: "allowed", authorization };
}

/**
 * The retained transport ring protects every authenticated modern request.
 * It intentionally does not consume the read budget used only for data access.
 */
async function applyTransportRateLimit(ports: McpProtocolPorts, credential: McpCredential, id: RpcId): Promise<RpcResponse | null> {
  const key = credential.rateLimitKey;
  return applyRateLimit(ports, {
    prefix: key.prefix,
    uid: key.uid,
    app_id: key.app_id,
    key_id: key.key_id,
    rate_policy: MCP_TRANSPORT_RATE_POLICY,
    log_on_failure: true,
  }, id);
}

async function applyReadRateLimit(ports: McpProtocolPorts, credential: McpCredential, id: RpcId): Promise<RpcResponse | null> {
  const key = credential.rateLimitKey;
  return applyRateLimit(ports, {
    prefix: key.prefix,
    uid: key.uid,
    app_id: key.app_id,
    key_id: key.key_id,
    scope: TOOL.dependency.scope,
    rate_policy: TOOL.dependency.rate_policy,
    log_on_failure: TOOL.dependency.log_on_failure,
  }, id);
}

async function applyRateLimit(ports: McpProtocolPorts, input: McpRateLimitInput, id: RpcId | null): Promise<RpcResponse | null> {
  let rate: RateLimitDecision;
  try {
    rate = await ports.rateLimit(input);
  } catch {
    return error(id, -32603, "Internal error");
  }
  if (rate.allowed === true) {
    return null;
  }
  const retryAfterSeconds = isRecord(rate) ? validRetryAfter(rate.retryAfterSeconds as number | undefined) : undefined;
  return error(id, -32029, "Rate limit exceeded", retryAfterSeconds === undefined ? undefined : { retryAfterSeconds });
}

function parseRpcRequest(input: unknown): RpcRequest | null {
  if (!isRecord(input) || !hasExactKeys(input, ["jsonrpc", "id", "method", "params"])) {
    return null;
  }
  if (input.jsonrpc !== "2.0" || !isRpcId(input.id) || !isNonEmptyString(input.method) || !isRecord(input.params)) {
    return null;
  }
  return input as RpcRequest;
}

function parseRequestMeta(params: Record<string, unknown>): { protocolVersion: string } | null {
  const meta = params._meta;
  if (!isRecord(meta) || !hasOnlyKeys(meta, [
    "io.modelcontextprotocol/protocolVersion",
    "io.modelcontextprotocol/clientCapabilities",
    "io.modelcontextprotocol/clientInfo",
  ])) {
    return null;
  }
  if (!isNonEmptyString(meta["io.modelcontextprotocol/protocolVersion"]) || !isExactEmptyObject(meta["io.modelcontextprotocol/clientCapabilities"])) {
    return null;
  }
  const clientInfo = meta["io.modelcontextprotocol/clientInfo"];
  if (clientInfo !== undefined && (!isRecord(clientInfo)
    || !hasExactKeys(clientInfo, ["name", "version"])
    || !isNonEmptyString(clientInfo.name)
    || !isNonEmptyString(clientInfo.version))) {
    return null;
  }
  return { protocolVersion: meta["io.modelcontextprotocol/protocolVersion"] as string };
}

function parseToolCall(params: Record<string, unknown>): { name: string; cursor?: string; limit: number } | null {
  if (!hasExactKeys(params, ["name", "arguments", "_meta"]) || !isToolName(params.name) || !isRecord(params.arguments)) {
    return null;
  }
  const args = params.arguments;
  if (!hasOnlyKeys(args, ["cursor", "limit"])) {
    return null;
  }
  if (args.cursor !== undefined && (!isNonEmptyString(args.cursor) || args.cursor.length > 4096)) {
    return null;
  }
  if (args.limit !== undefined && (!Number.isInteger(args.limit) || args.limit < 1 || args.limit > 100)) {
    return null;
  }
  return { name: params.name as string, cursor: args.cursor as string | undefined, limit: (args.limit as number | undefined) ?? 20 };
}

function validateHeaders(
  headers: Readonly<Record<string, string | undefined>>,
  rpc: RpcRequest,
  metaProtocolVersion: string,
): { status: 400; code: -32020 | -32022; message: string; data?: unknown } | null {
  const protocol = readHeader(headers, "mcp-protocol-version");
  if (!protocol.valid || protocol.value === undefined) {
    return headerMismatch("Missing or malformed MCP-Protocol-Version header");
  }
  if (protocol.value !== MCP_PROTOCOL_VERSION) {
    return {
      status: 400,
      code: -32022,
      message: "Unsupported protocol version",
      data: { supported: [MCP_PROTOCOL_VERSION], requested: protocol.value },
    };
  }
  if (metaProtocolVersion !== protocol.value) {
    return headerMismatch("MCP-Protocol-Version header does not match request metadata");
  }

  const method = readHeader(headers, "mcp-method");
  if (!method.valid || method.value === undefined || method.value !== rpc.method) {
    return headerMismatch("Mcp-Method header does not match request method");
  }

  const bodyName = rpc.method === "tools/call" && isRecord(rpc.params) && typeof rpc.params.name === "string"
    ? rpc.params.name
    : null;
  const name = readHeader(headers, "mcp-name");
  if (!name.valid) {
    return headerMismatch("Malformed Mcp-Name header");
  }
  if (bodyName === null) {
    if (name.value !== undefined && name.value !== "") {
      return headerMismatch("Mcp-Name must be empty for this method");
    }
    return null;
  }
  if (name.value === undefined || decodeMcpHeaderValue(name.value) !== bodyName) {
    return headerMismatch("Mcp-Name header does not match request name");
  }
  return null;
}

function readHeader(headers: Readonly<Record<string, string | undefined>>, expected: string): { readonly valid: boolean; readonly value: string | undefined } {
  const matches = Object.entries(headers).filter(([name]) => name.toLowerCase() === expected);
  if (matches.length > 1) {
    return { valid: false, value: undefined };
  }
  const value = matches[0]?.[1];
  return { valid: value === undefined || isSafeHeaderValue(value), value };
}

function decodeMcpHeaderValue(value: string): string | null {
  const match = /^=\?base64\?([A-Za-z0-9+/]*={0,2})\?=$/.exec(value);
  if (match === null) {
    return value;
  }
  try {
    const decoded = Buffer.from(match[1], "base64");
    if (decoded.toString("base64") !== match[1]) {
      return null;
    }
    return decoded.toString("utf8");
  } catch {
    return null;
  }
}

function headerMismatch(message: string): { status: 400; code: -32020; message: string } {
  return { status: 400, code: -32020, message };
}

function isCredential(value: unknown): value is McpCredential {
  if (!isRecord(value) || !hasExactKeys(value, ["kind", "scopes", "rateLimitKey", "cursorBindings", "authentication"])) {
    return false;
  }
  if (value.kind !== "mcp_api_key" || !Array.isArray(value.scopes) || !value.scopes.every(isNonEmptyString)) {
    return false;
  }
  if (!isCredentialRateLimitKey(value.rateLimitKey) || !isRecord(value.cursorBindings)) {
    return false;
  }
  const bindings = value.cursorBindings;
  return hasExactKeys(bindings, [
    "ownerAuthorizationDigest",
    "appAuthorizationDigest",
    "keyAuthorizationDigest",
    "graphGenerationDigest",
    "projectionGenerationDigest",
    "filterDigest",
    "readModeDigest",
  ]) && Object.values(bindings).every(isNonEmptyString);
}

function isCredentialRateLimitKey(value: unknown): value is McpCredentialRateLimitKey {
  return isRecord(value)
    && hasExactKeys(value, ["prefix", "uid", "app_id", "key_id"])
    && value.prefix === "mcp"
    && isNonEmptyString(value.uid)
    && isNonEmptyString(value.app_id)
    && isNonEmptyString(value.key_id);
}

function isGrantedAuthorization(value: unknown): value is GrantedAuthorization {
  return isRecord(value) && value.allowed === true && Object.hasOwn(value, "readAuthorization");
}

function isBoundedJsonSnapshot(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || Buffer.byteLength(value, "utf8") > MAX_VALIDATED_PAGE_BYTES) {
    return false;
  }
  try {
    return isRecord(JSON.parse(value));
  } catch {
    return false;
  }
}

function rpcHttp(status: 200 | 400 | 404, body: RpcResponse): McpHttpResponse {
  return { status, headers: JSON_HEADERS, body };
}

function success(id: RpcId, result: Record<string, unknown>): RpcResponse {
  return { jsonrpc: "2.0", id, result };
}

function invalidRequest(): RpcResponse {
  return error(null, -32600, "Invalid Request");
}

function error(id: RpcId | null, code: number, message: string, data?: unknown): RpcResponse {
  return { jsonrpc: "2.0", id, error: data === undefined ? { code, message } : { code, message, data } };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function isRpcId(value: unknown): value is RpcId {
  return typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
}

function isToolName(value: unknown): value is string {
  return isNonEmptyString(value) && value.length <= 128 && /^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isSafeHeaderValue(value: string): boolean {
  return /^[\t\x20-\x7E]*$/.test(value);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key));
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && hasOnlyKeys(value, keys);
}

function isExactEmptyObject(value: unknown): boolean {
  return isRecord(value) && Object.keys(value).length === 0;
}

function validRetryAfter(value: number | undefined): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}
