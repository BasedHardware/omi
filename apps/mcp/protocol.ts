import { isProxy } from "node:util/types";

import { InvalidMcpCursorError } from "./cursor";

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

// domain-pending(DIV-DOMX-002): "surface" remains an unresolved label here.
/** API-key-only QA surface; this is never serialized onto the MCP wire. */
export interface McpCredential {
  readonly kind: "mcp_api_key";
  readonly scopes: readonly string[];
  readonly rateLimitKey: McpCredentialRateLimitKey;
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
  // domain-pending(DIV-DOMX-002): the caller "surface" vocabulary remains
  // unsettled; the adapter owns the origin allow-list for this HTTP surface.
  validateOrigin(input: { readonly origin: string }): Promise<boolean> | boolean;
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
  /**
   * The coherent read composition owns cursor verification and
   * issuance. Only that layer has the complete authorization, projection,
   * commit, source, and frontier snapshot needed by the 15-field cursor
   * binding. The transport forwards the syntactically bounded client bytes
   * unchanged and translates only `InvalidMcpCursorError` to the public
   * invalid-cursor response.
   */
  readPage(input: {
    readonly authorization: unknown;
    readonly cursor: string | null;
    readonly limit: number;
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
}

export interface McpHttpRequest {
  readonly method: string;
  readonly headers: Readonly<Record<string, string | undefined>>;
  readonly body: unknown;
}

export interface McpHttpResponse {
  readonly status: 200 | 400 | 401 | 403 | 404 | 405;
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

const TOOL: McpToolDefinition = Object.freeze({
  name: SYNTHESIZED_MEMORY_READ_TOOL,
  dependency: SYNTHESIZED_MEMORY_READ_DEPENDENCY,
});

const JSON_HEADERS = Object.freeze({
  "content-type": "application/json",
  "mcp-protocol-version": MCP_PROTOCOL_VERSION,
});
const PRIVATE_CACHE = Object.freeze({ ttlMs: 0, cacheScope: "private" });
const MAX_VALIDATED_PAGE_BYTES = 1_000_000;
const DETACH_FAILED = Symbol("mcp_dependency_data_detach_failed");

export function createMcpProtocolHandler(ports: McpProtocolPorts): {
  handleHttp(request: McpHttpRequest): Promise<McpHttpResponse>;
} {
  return {
    async handleHttp(request: McpHttpRequest): Promise<McpHttpResponse> {
      const origin = readHeader(request.headers, "origin");
      if (!origin.valid || (origin.value !== undefined && !await isAllowedOrigin(ports, origin.value))) {
        // Do this before endpoint/content negotiation: an invalid Origin must
        // never gain a different result by choosing a malformed envelope.
        return rpcHttp(403, error(null, -32600, "Forbidden origin"));
      }
      if (request.method !== "POST") {
        return { status: 405, headers: JSON_HEADERS };
      }
      if (!hasStreamableHttpEnvelope(request.headers)) {
        return rpcHttp(400, invalidRequest());
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

      let authenticatedCredential: McpCredential | null;
      try {
        authenticatedCredential = await ports.authenticate({
          apiKeyHeader: readHeader(request.headers, "authorization").value,
          requiredKind: "mcp_api_key",
        });
      } catch {
        authenticatedCredential = null;
      }
      const credential = snapshotCredential(authenticatedCredential);
      if (credential === null) {
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
    _meta: { "io.modelcontextprotocol/serverInfo": { name: "omi-platform-mcp", version: "0.0.0" } },
    ...PRIVATE_CACHE,
  }));
}

async function listTools(ports: McpProtocolPorts, credential: McpCredential, rpc: RpcRequest): Promise<McpHttpResponse> {
  if (parseListTools(rpc.params) === null) {
    return rpcHttp(400, error(rpc.id, -32602, "Invalid params"));
  }
  const gate = await visibilityGate(ports, credential);
  return rpcHttp(200, success(rpc.id, {
    resultType: "complete",
    // Create a fresh graph for every response: callers must never be able to
    // mutate a later credential's advertised tool definition.
    tools: gate.kind === "allowed" ? [toolDescriptor()] : [],
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

  let page: unknown;
  try {
    page = await ports.readPage({
      authorization: gate.authorization.readAuthorization,
      cursor: call.cursor ?? null,
      limit: call.limit,
    });
  } catch (caught) {
    if (caught instanceof InvalidMcpCursorError) {
      return rpcHttp(400, error(rpc.id, -32602, "Invalid cursor"));
    }
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
  const granted = snapshotGrantedAuthorization(authorization);
  if (granted === null) {
    return { kind: "denied" };
  }

  return { kind: "allowed", authorization: granted };
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
  let rate: unknown;
  try {
    rate = await ports.rateLimit(input);
  } catch {
    return error(id, -32603, "Internal error");
  }
  const decision = snapshotRateLimitDecision(rate);
  if (decision === null) {
    return error(id, -32603, "Internal error");
  }
  if (decision.allowed === true) {
    return null;
  }
  const retryAfterSeconds = decision.retryAfterSeconds;
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
  if (!isRecord(meta) || !Object.keys(meta).every(isValidMetaKey)) {
    return null;
  }
  if (!isNonEmptyString(meta["io.modelcontextprotocol/protocolVersion"])
    || !isClientCapabilities(meta["io.modelcontextprotocol/clientCapabilities"])) {
    return null;
  }
  const clientInfo = meta["io.modelcontextprotocol/clientInfo"];
  if (clientInfo !== undefined && !isClientInfo(clientInfo)) {
    return null;
  }
  const progressToken = meta.progressToken;
  if (progressToken !== undefined && !isProgressToken(progressToken)) {
    return null;
  }
  const logLevel = meta["io.modelcontextprotocol/logLevel"];
  if (logLevel !== undefined && !isLoggingLevel(logLevel)) {
    return null;
  }
  return { protocolVersion: meta["io.modelcontextprotocol/protocolVersion"] as string };
}

function parseToolCall(params: Record<string, unknown>): { name: string; cursor?: string; limit: number } | null {
  if (!hasOnlyKeys(params, ["name", "arguments", "_meta"]) || !isToolName(params.name)) {
    return null;
  }
  const args = params.arguments ?? {};
  if (!isRecord(args)) {
    return null;
  }
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

function hasStreamableHttpEnvelope(headers: Readonly<Record<string, string | undefined>>): boolean {
  const contentType = readHeader(headers, "content-type");
  const accept = readHeader(headers, "accept");
  return contentType.valid
    && isJsonContentType(contentType.value)
    && accept.valid
    && acceptsMediaType(accept.value, "application/json")
    && acceptsMediaType(accept.value, "text/event-stream");
}

async function isAllowedOrigin(ports: McpProtocolPorts, origin: string): Promise<boolean> {
  try {
    return await ports.validateOrigin({ origin }) === true;
  } catch {
    return false;
  }
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
  if (!isRecord(value) || !hasExactKeys(value, ["kind", "scopes", "rateLimitKey", "authentication"])) {
    return false;
  }
  if (value.kind !== "mcp_api_key" || !Array.isArray(value.scopes) || !value.scopes.every(isNonEmptyString)) {
    return false;
  }
  return isCredentialRateLimitKey(value.rateLimitKey);
}

/** Snapshot once after authentication so downstream ports cannot race its tuple. */
function snapshotCredential(value: unknown): McpCredential | null {
  const snapshot = detachDependencyData(value);
  return snapshot !== DETACH_FAILED && isCredential(snapshot) ? snapshot : null;
}

function isCredentialRateLimitKey(value: unknown): value is McpCredentialRateLimitKey {
  return isRecord(value)
    && hasExactKeys(value, ["prefix", "uid", "app_id", "key_id"])
    && value.prefix === "mcp"
    && isNonEmptyString(value.uid)
    && isNonEmptyString(value.app_id)
    && isNonEmptyString(value.key_id);
}

function snapshotGrantedAuthorization(value: unknown): GrantedAuthorization | null {
  const snapshot = detachDependencyData(value);
  if (snapshot === DETACH_FAILED
    || !isRecord(snapshot)
    || !hasExactKeys(snapshot, ["allowed", "readAuthorization"])
    || snapshot.allowed !== true
    || !isRealReadAuthorization(snapshot.readAuthorization)) {
    return null;
  }
  return snapshot as GrantedAuthorization;
}

function isRealReadAuthorization(value: unknown): boolean {
  return typeof value === "string"
    ? isNonEmptyString(value)
    : isRecord(value) && Object.keys(value).length > 0 && isJsonObject(value);
}

function snapshotRateLimitDecision(value: unknown): RateLimitDecision | null {
  const snapshot = detachDependencyData(value);
  if (snapshot === DETACH_FAILED || !isRecord(snapshot)) {
    return null;
  }
  if (snapshot.allowed === true) {
    return hasExactKeys(snapshot, ["allowed"]) ? { allowed: true } : null;
  }
  if (snapshot.allowed !== false || !hasOnlyKeys(snapshot, ["allowed", "retryAfterSeconds"])) {
    return null;
  }
  const retryAfterSeconds = snapshot.retryAfterSeconds;
  if (retryAfterSeconds !== undefined && validRetryAfter(retryAfterSeconds as number | undefined) === undefined) {
    return null;
  }
  return retryAfterSeconds === undefined ? { allowed: false } : { allowed: false, retryAfterSeconds: retryAfterSeconds as number };
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

function rpcHttp(status: 200 | 400 | 403 | 404, body: RpcResponse): McpHttpResponse {
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

function isJsonContentType(value: string | undefined): boolean {
  return value !== undefined && value.split(";", 1)[0]?.trim().toLowerCase() === "application/json";
}

function acceptsMediaType(value: string | undefined, expected: string): boolean {
  return value?.split(",").some((candidate) => {
    const segments = candidate.trim().split(";");
    if (segments.shift()?.trim().toLowerCase() !== expected) {
      return false;
    }
    const quality = segments.find((segment) => segment.trim().toLowerCase().startsWith("q="));
    if (quality === undefined) {
      return true;
    }
    const parsed = Number(quality.trim().slice(2));
    return Number.isFinite(parsed) && parsed > 0 && parsed <= 1;
  }) ?? false;
}

function parseListTools(params: Record<string, unknown>): { readonly cursor?: string } | null {
  if (!hasOnlyKeys(params, ["_meta", "cursor"])) {
    return null;
  }
  if (params.cursor !== undefined && typeof params.cursor !== "string") {
    return null;
  }
  return params.cursor === undefined ? {} : { cursor: params.cursor };
}

function toolDescriptor(): Record<string, unknown> {
  return {
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
  };
}

function isClientInfo(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, ["name", "version", "title", "description", "websiteUrl", "icons"])) {
    return false;
  }
  return isNonEmptyString(value.name)
    && isNonEmptyString(value.version)
    && (value.title === undefined || typeof value.title === "string")
    && (value.description === undefined || typeof value.description === "string")
    && (value.websiteUrl === undefined || typeof value.websiteUrl === "string")
    && (value.icons === undefined || (Array.isArray(value.icons) && value.icons.every(isJsonObject)));
}

function isClientCapabilities(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  for (const [name, capability] of Object.entries(value)) {
    if (!isJsonObject(capability)) {
      return false;
    }
    if (name === "extensions" && !Object.entries(capability).every(([extension, settings]) =>
      isValidMetaKeyWithPrefix(extension) && isJsonObject(settings))) {
      return false;
    }
  }
  return true;
}

function isProgressToken(value: unknown): boolean {
  return typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
}

function isLoggingLevel(value: unknown): boolean {
  return value === "debug" || value === "info" || value === "notice" || value === "warning"
    || value === "error" || value === "critical" || value === "alert" || value === "emergency";
}

function isValidMetaKey(value: string): boolean {
  return isValidMetaKeyParts(value, false);
}

function isValidMetaKeyWithPrefix(value: string): boolean {
  return isValidMetaKeyParts(value, true);
}

function isValidMetaKeyParts(value: string, requirePrefix: boolean): boolean {
  const slash = value.indexOf("/");
  if (slash < 0) {
    return !requirePrefix && isValidMetaName(value);
  }
  if (slash !== value.lastIndexOf("/")) {
    return false;
  }
  return isValidMetaPrefix(value.slice(0, slash)) && isValidMetaName(value.slice(slash + 1));
}

function isValidMetaPrefix(value: string): boolean {
  return /^(?:[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?)(?:\.[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*$/.test(value);
}

function isValidMetaName(value: string): boolean {
  return value === "" || /^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$/.test(value);
}

function isJsonObject(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && Object.values(value).every(isJsonValue);
}

function isJsonValue(value: unknown): boolean {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return true;
  }
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  if (Array.isArray(value)) {
    return value.every(isJsonValue);
  }
  return isJsonObject(value);
}

/**
 * Detach one dependency result by descriptors, never by property reads.
 * Accessors, symbols, exotic prototypes, sparse arrays, and non-JSON values
 * are rejected before a getter can run. Callers validate and consume only the
 * returned frozen graph, never the dependency-owned source object again.
 */
function detachDependencyData(value: unknown): unknown | typeof DETACH_FAILED {
  try {
    return detachPlainData(value, 0);
  } catch {
    return DETACH_FAILED;
  }
}

function detachPlainData(value: unknown, depth: number): unknown {
  if (depth > 64) {
    throw new TypeError("Dependency result is too deeply nested");
  }
  if (typeof value === "object" && value !== null && isProxy(value)) {
    throw new TypeError("Dependency result contains a proxy");
  }
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("Dependency result contains a non-finite number");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return detachPlainArray(value, depth + 1);
  }
  if (typeof value === "object") {
    return detachPlainObject(value, depth + 1);
  }
  throw new TypeError("Dependency result is not plain data");
}

function detachPlainArray(value: unknown[], depth: number): readonly unknown[] {
  if (Object.getPrototypeOf(value) !== Array.prototype) {
    throw new TypeError("Dependency result contains an exotic array");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) {
    throw new TypeError("Dependency result contains symbol keys");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const lengthDescriptor = descriptors.length;
  if (lengthDescriptor === undefined || !("value" in lengthDescriptor) || typeof lengthDescriptor.value !== "number") {
    throw new TypeError("Dependency result has an invalid array length");
  }
  const length = lengthDescriptor.value;
  if (!Number.isSafeInteger(length) || length < 0 || keys.length !== length + 1) {
    throw new TypeError("Dependency result contains sparse or extra array properties");
  }
  const detached: unknown[] = [];
  for (let index = 0; index < length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("Dependency result contains an array accessor");
    }
    detached.push(detachPlainData(descriptor.value, depth));
  }
  return Object.freeze(detached);
}

function detachPlainObject(value: object, depth: number): Readonly<Record<string, unknown>> {
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError("Dependency result contains an exotic object");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) {
    throw new TypeError("Dependency result contains symbol keys");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const detached = Object.create(null) as Record<string, unknown>;
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("Dependency result contains an accessor or hidden property");
    }
    Object.defineProperty(detached, key, {
      value: detachPlainData(descriptor.value, depth),
      enumerable: true,
      writable: false,
      configurable: false,
    });
  }
  return Object.freeze(detached);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key));
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && hasOnlyKeys(value, keys);
}

function validRetryAfter(value: number | undefined): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}
