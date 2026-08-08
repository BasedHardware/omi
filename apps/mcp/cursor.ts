import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Protocol-local port of the HMAC keyset-cursor behavior ruled by ADR-004 and
 * DIV-MEM-004. This module is deliberately pure: it performs no storage,
 * authorization, transport, or network work.
 */
const CURSOR_PREFIX = "mcp1";
const CURSOR_VERSION = 1;
const SIGNATURE_BYTES = 32;
const MAX_SIGNING_KEYS = 8;
const MIN_SIGNING_SECRET_BYTES = 32;
const MAX_PAYLOAD_BYTES = 3_072;
const MAX_LAST_VISIBLE_KEY_BYTES = 512;
const MAX_CURSOR_TTL_SECONDS = 86_400;
export const MAX_MCP_CURSOR_ENCODED_BYTES = 4_096;

const DIGEST_PATTERN = /^[a-f0-9]{64}$/;
const KEY_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const OPAQUE_KEY_PATTERN = /^[A-Za-z0-9_-]+$/;
const DUMMY_SECRET = new Uint8Array(MIN_SIGNING_SECRET_BYTES);
const DUMMY_SIGNATURE = new Uint8Array(SIGNATURE_BYTES);

type JsonValue = null | boolean | number | string | readonly JsonValue[] | { readonly [key: string]: JsonValue };

// `app` is the live authorization-record term until the vocabulary ruling lands.
// domain-pending(DIV-DOMAPPS-001)
// `key` spans two credential systems and remains mechanically renameable.
// domain-pending(DIV-DOMAPPS-006)
// `grant` here means the persisted authorization record, not a request capability.
// domain-pending(DIV-DOMX-006)
export interface McpCursorBindings {
  readonly owner_digest: string;
  readonly app_digest: string;
  readonly credential_key_digest: string;
  readonly authorization_generation_digest: string;
  readonly grant_generation_digest: string;
  readonly graph_generation_digest: string;
  readonly projection_generation_digest: string;
  readonly visibility_digest: string;
  readonly filter_digest: string;
  readonly query_digest: string;
  readonly source_digest: string;
  readonly read_mode_digest: string;
}

export interface McpCursorSigningKey {
  readonly key_id: string;
  readonly secret: Uint8Array;
}

export interface McpCursorSigningKeyset {
  readonly active_key_id: string;
  readonly keys: readonly McpCursorSigningKey[];
}

export interface IssueMcpCursorRequest {
  /**
   * The continuation key must already be opaque and content-free. Raw user,
   * application, credential, query, or source identifiers do not belong here.
   */
  readonly last_visible_key: string;
  readonly bindings: McpCursorBindings;
  readonly issued_at_epoch_seconds: number;
  readonly ttl_seconds: number;
}

export interface VerifyMcpCursorRequest {
  readonly bindings: McpCursorBindings;
  readonly now_epoch_seconds: number;
}

export interface McpCursorClaims {
  readonly version: 1;
  readonly signing_key_id: string;
  readonly issued_at_epoch_seconds: number;
  readonly expires_at_epoch_seconds: number;
  readonly last_visible_key: string;
  readonly bindings: Readonly<McpCursorBindings>;
}

/** Every client-controlled cursor failure intentionally has one public shape. */
export class InvalidMcpCursorError extends Error {
  readonly code = "invalid_cursor" as const;

  constructor() {
    super("invalid cursor");
    this.name = "InvalidMcpCursorError";
  }
}

interface CursorPayload {
  readonly version: 1;
  readonly issued_at_epoch_seconds: number;
  readonly expires_at_epoch_seconds: number;
  readonly last_visible_key: string;
  readonly bindings: McpCursorBindings;
}

const BINDING_KEYS = Object.freeze([
  "owner_digest",
  "app_digest",
  "credential_key_digest",
  "authorization_generation_digest",
  "grant_generation_digest",
  "graph_generation_digest",
  "projection_generation_digest",
  "visibility_digest",
  "filter_digest",
  "query_digest",
  "source_digest",
  "read_mode_digest",
] as const satisfies readonly (keyof McpCursorBindings)[]);

const PAYLOAD_KEYS = Object.freeze([
  "bindings",
  "expires_at_epoch_seconds",
  "issued_at_epoch_seconds",
  "last_visible_key",
  "version",
] as const);

const invalid = (): never => { throw new InvalidMcpCursorError(); };
const configurationError = (message: string): never => { throw new TypeError(message); };

const isExactPlainObject = (value: unknown, expectedKeys: readonly string[]): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Object.keys(descriptors).sort();
  const expected = [...expectedKeys].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) return false;
  return Object.values(descriptors).every((descriptor) => "value" in descriptor && descriptor.enumerable);
};

const canonicalJson = (value: JsonValue): string => {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) configurationError("cursor payload rejects non-finite numbers");
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.entries(value)
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    .join(",")}}`;
};

const encodeBase64Url = (value: Uint8Array): string => Buffer.from(value).toString("base64url");

const decodeCanonicalBase64Url = (value: string, maxBytes: number): Uint8Array | null => {
  if (!value || !OPAQUE_KEY_PATTERN.test(value) || value.length % 4 === 1) return null;
  try {
    const decoded = Buffer.from(value, "base64url");
    if (decoded.byteLength > maxBytes || decoded.toString("base64url") !== value) return null;
    return decoded;
  } catch {
    return null;
  }
};

const signature = (prefix: string, keyId: string, payload: string, secret: Uint8Array): Uint8Array =>
  createHmac("sha256", Buffer.from(secret))
    .update(`${prefix}.${keyId}.${payload}`, "ascii")
    .digest();

const normalizeSigningKeyset = (keyset: McpCursorSigningKeyset): {
  readonly activeKey: McpCursorSigningKey;
  readonly keys: ReadonlyMap<string, McpCursorSigningKey>;
} => {
  if (keyset === null || typeof keyset !== "object" || !Array.isArray(keyset.keys)
    || !KEY_ID_PATTERN.test(keyset.active_key_id)
    || keyset.keys.length < 1 || keyset.keys.length > MAX_SIGNING_KEYS) {
    return configurationError("invalid MCP cursor signing keyset");
  }
  const keys = new Map<string, McpCursorSigningKey>();
  for (const candidate of keyset.keys) {
    if (candidate === null || typeof candidate !== "object" || !KEY_ID_PATTERN.test(candidate.key_id)
      || !(candidate.secret instanceof Uint8Array) || candidate.secret.byteLength < MIN_SIGNING_SECRET_BYTES
      || keys.has(candidate.key_id)) {
      return configurationError("invalid MCP cursor signing keyset");
    }
    keys.set(candidate.key_id, Object.freeze({ key_id: candidate.key_id, secret: new Uint8Array(candidate.secret) }));
  }
  const activeKey = keys.get(keyset.active_key_id);
  if (!activeKey) return configurationError("active MCP cursor signing key is absent");
  return { activeKey, keys };
};

const validateBindings = (value: unknown): value is McpCursorBindings => {
  if (!isExactPlainObject(value, BINDING_KEYS)) return false;
  return BINDING_KEYS.every((key) => typeof value[key] === "string" && DIGEST_PATTERN.test(value[key]));
};

const assertIssueBindings = (value: unknown): asserts value is McpCursorBindings => {
  if (!validateBindings(value)) configurationError("cursor bindings must be exact SHA-256 digests");
};

const validateExpected = (request: VerifyMcpCursorRequest): void => {
  if (request === null || typeof request !== "object" || !validateBindings(request.bindings)
    || !Number.isSafeInteger(request.now_epoch_seconds) || request.now_epoch_seconds < 0) {
    configurationError("invalid MCP cursor verification context");
  }
};

const validateOpaqueLastVisibleKey = (value: unknown): value is string =>
  typeof value === "string"
  && OPAQUE_KEY_PATTERN.test(value)
  && Buffer.byteLength(value, "utf8") <= MAX_LAST_VISIBLE_KEY_BYTES;

const parsePayload = (encodedPayload: string): CursorPayload => {
  const decoded = decodeCanonicalBase64Url(encodedPayload, MAX_PAYLOAD_BYTES);
  if (!decoded) return invalid();
  const text = Buffer.from(decoded).toString("utf8");
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return invalid();
  }
  if (!isExactPlainObject(value, PAYLOAD_KEYS) || !validateBindings(value.bindings)
    || value.version !== CURSOR_VERSION
    || !Number.isSafeInteger(value.issued_at_epoch_seconds) || value.issued_at_epoch_seconds < 0
    || !Number.isSafeInteger(value.expires_at_epoch_seconds) || value.expires_at_epoch_seconds < 0
    || !validateOpaqueLastVisibleKey(value.last_visible_key)) {
    return invalid();
  }
  let canonical: string;
  try {
    canonical = canonicalJson(value as unknown as JsonValue);
  } catch {
    return invalid();
  }
  if (canonical !== text) return invalid();
  return value as unknown as CursorPayload;
};

const digestEquals = (left: string, right: string): boolean =>
  timingSafeEqual(Buffer.from(left, "ascii"), Buffer.from(right, "ascii"));

const bindingsEqual = (left: McpCursorBindings, right: McpCursorBindings): boolean => {
  let matches = true;
  for (const key of BINDING_KEYS) matches = digestEquals(left[key], right[key]) && matches;
  return matches;
};

export const issueMcpCursor = (
  request: IssueMcpCursorRequest,
  signingKeyset: McpCursorSigningKeyset,
): string => {
  const { activeKey } = normalizeSigningKeyset(signingKeyset);
  assertIssueBindings(request.bindings);
  if (!validateOpaqueLastVisibleKey(request.last_visible_key)) configurationError("last visible key must be an opaque bounded token");
  if (!Number.isSafeInteger(request.issued_at_epoch_seconds) || request.issued_at_epoch_seconds < 0
    || !Number.isSafeInteger(request.ttl_seconds) || request.ttl_seconds < 1
    || request.ttl_seconds > MAX_CURSOR_TTL_SECONDS
    || request.issued_at_epoch_seconds > Number.MAX_SAFE_INTEGER - request.ttl_seconds) {
    return configurationError("invalid MCP cursor lifetime");
  }
  const payload: CursorPayload = {
    version: CURSOR_VERSION,
    issued_at_epoch_seconds: request.issued_at_epoch_seconds,
    expires_at_epoch_seconds: request.issued_at_epoch_seconds + request.ttl_seconds,
    last_visible_key: request.last_visible_key,
    bindings: { ...request.bindings },
  };
  const encodedPayload = encodeBase64Url(Buffer.from(canonicalJson(payload as unknown as JsonValue), "utf8"));
  const encodedSignature = encodeBase64Url(signature(CURSOR_PREFIX, activeKey.key_id, encodedPayload, activeKey.secret));
  const cursor = `${CURSOR_PREFIX}.${activeKey.key_id}.${encodedPayload}.${encodedSignature}`;
  if (Buffer.byteLength(cursor, "utf8") > MAX_MCP_CURSOR_ENCODED_BYTES) configurationError("MCP cursor exceeds encoded size bound");
  return cursor;
};

export const verifyMcpCursor = (
  cursor: string,
  request: VerifyMcpCursorRequest,
  signingKeyset: McpCursorSigningKeyset,
): Readonly<McpCursorClaims> => {
  validateExpected(request);
  const { keys } = normalizeSigningKeyset(signingKeyset);
  if (typeof cursor !== "string" || Buffer.byteLength(cursor, "utf8") > MAX_MCP_CURSOR_ENCODED_BYTES) return invalid();
  const parts = cursor.split(".");
  if (parts.length !== 4) return invalid();
  const [prefix, keyId, encodedPayload, encodedSignature] = parts as [string, string, string, string];
  if (prefix !== CURSOR_PREFIX || !KEY_ID_PATTERN.test(keyId)) return invalid();

  // Unknown key IDs and malformed signatures still execute a fixed-size HMAC
  // comparison. The key ID is not secret, but no signature branch is variable-time.
  const configuredKey = keys.get(keyId);
  const expectedSignature = signature(prefix, keyId, encodedPayload, configuredKey?.secret ?? DUMMY_SECRET);
  const decodedSignature = decodeCanonicalBase64Url(encodedSignature, SIGNATURE_BYTES);
  const suppliedSignature = decodedSignature?.byteLength === SIGNATURE_BYTES ? decodedSignature : DUMMY_SIGNATURE;
  const signatureMatches = timingSafeEqual(Buffer.from(expectedSignature), Buffer.from(suppliedSignature));
  if (!configuredKey || decodedSignature?.byteLength !== SIGNATURE_BYTES || !signatureMatches) return invalid();

  const payload = parsePayload(encodedPayload);
  const ttl = payload.expires_at_epoch_seconds - payload.issued_at_epoch_seconds;
  if (ttl < 1 || ttl > MAX_CURSOR_TTL_SECONDS
    || request.now_epoch_seconds < payload.issued_at_epoch_seconds
    || request.now_epoch_seconds >= payload.expires_at_epoch_seconds
    || !bindingsEqual(payload.bindings, request.bindings)) {
    return invalid();
  }
  const bindings = Object.freeze({ ...payload.bindings });
  return Object.freeze({
    version: CURSOR_VERSION,
    signing_key_id: keyId,
    issued_at_epoch_seconds: payload.issued_at_epoch_seconds,
    expires_at_epoch_seconds: payload.expires_at_epoch_seconds,
    last_visible_key: payload.last_visible_key,
    bindings,
  });
};

/**
 * Enforces the security-sensitive call order for data adapters: all token,
 * lifetime, key-rotation, and replay-binding checks complete synchronously
 * before the callback receives a continuation key.
 */
export const readAfterMcpCursorValidation = <Result>(
  cursor: string,
  request: VerifyMcpCursorRequest,
  signingKeyset: McpCursorSigningKeyset,
  readData: (claims: Readonly<McpCursorClaims>) => Result,
): Result => {
  const claims = verifyMcpCursor(cursor, request, signingKeyset);
  return readData(claims);
};
