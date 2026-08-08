import { createHmac, timingSafeEqual } from "node:crypto";
import { isProxy } from "node:util/types";

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
const MAX_SIGNING_SECRET_BYTES = 4_096;
const MAX_PAYLOAD_BYTES = 3_072;
const MAX_CURSOR_TTL_SECONDS = 86_400;
export const MAX_MCP_CURSOR_ENCODED_BYTES = 4_096;

const DIGEST_PATTERN = /^[a-f0-9]{64}$/;
const KEY_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const BASE64URL_PATTERN = /^[A-Za-z0-9_-]+$/;
const OPAQUE_VISIBLE_KEYSET_PATTERN = /^vk1_[a-f0-9]{64}$/;
const DUMMY_SECRET = new Uint8Array(MIN_SIGNING_SECRET_BYTES);
const DUMMY_SIGNATURE = new Uint8Array(SIGNATURE_BYTES);
declare const opaqueVisibleKeysetBrand: unique symbol;

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
  readonly account_generation_digest: string;
  readonly graph_generation_digest: string;
  readonly projection_generation_digest: string;
  readonly projection_commit_digest: string;
  readonly visibility_digest: string;
  readonly filter_digest: string;
  readonly query_digest: string;
  readonly cursor_policy_digest: string;
  readonly source_digest: string;
  readonly read_mode_digest: string;
}

/**
 * A service-produced `vk1_<sha256>` HMAC/digest handle for the deterministic
 * stable sort keyset of the last *visible* row. The service resolves it back to
 * that visible tuple; it is never an offset, raw row ID, or content.
 */
export type OpaqueVisibleKeyset = string & { readonly [opaqueVisibleKeysetBrand]: true };

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
   * The continuation key must already encode the deterministic stable sort
   * keyset of the last visible row. Raw user, application, credential, query,
   * source identifiers, hidden-row coordinates, and offsets do not belong here.
   */
  readonly last_visible_key: OpaqueVisibleKeyset;
  readonly bindings: McpCursorBindings;
  /** The authoritative page read timestamp; cursor TTL starts from this snapshot. */
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
  /** The signed page read timestamp, not an ambient decode or response time. */
  readonly issued_at_epoch_seconds: number;
  readonly expires_at_epoch_seconds: number;
  readonly last_visible_key: OpaqueVisibleKeyset;
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
  readonly last_visible_key: OpaqueVisibleKeyset;
  readonly bindings: McpCursorBindings;
}

const BINDING_KEYS = Object.freeze([
  "owner_digest",
  "app_digest",
  "credential_key_digest",
  "authorization_generation_digest",
  "grant_generation_digest",
  "account_generation_digest",
  "graph_generation_digest",
  "projection_generation_digest",
  "projection_commit_digest",
  "visibility_digest",
  "filter_digest",
  "query_digest",
  "cursor_policy_digest",
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
type Reject = (message: string) => never;
const rejectInvalidCursor: Reject = () => invalid();

const snapshotExactDataDescriptors = (
  value: unknown,
  expectedKeys: readonly string[],
  reject: Reject,
): Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>> => {
  if (value === null || typeof value !== "object" || isProxy(value) || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return reject("expected an exact plain object");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key === "symbol")) return reject("symbol keys are not allowed");
  const keys = (ownKeys as string[]).sort();
  const expected = [...expectedKeys].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) return reject("unexpected object fields");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return reject("only enumerable own data properties are allowed");
  }
  return descriptors as Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;
};

const snapshotExactArray = (value: unknown, maxLength: number, reject: Reject): readonly unknown[] => {
  if (value === null || typeof value !== "object" || isProxy(value) || !Array.isArray(value)
    || Object.getPrototypeOf(value) !== Array.prototype) return reject("expected an exact plain array");
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key === "symbol")) return reject("symbol array keys are not allowed");
  const lengthDescriptor = Object.getOwnPropertyDescriptor(value, "length");
  if (!lengthDescriptor || !("value" in lengthDescriptor) || !Number.isSafeInteger(lengthDescriptor.value)
    || lengthDescriptor.value < 0 || lengthDescriptor.value > maxLength) return reject("invalid array length");
  const length = lengthDescriptor.value as number;
  const expectedKeys = ["length", ...Array.from({ length }, (_, index) => String(index))].sort();
  const keys = (ownKeys as string[]).sort();
  if (keys.length !== expectedKeys.length || keys.some((key, index) => key !== expectedKeys[index])) {
    return reject("sparse or extended arrays are not allowed");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const snapshot: unknown[] = [];
  for (let index = 0; index < length; index++) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return reject("array accessors are not allowed");
    snapshot.push(descriptor.value);
  }
  return Object.freeze(snapshot);
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
  if (!value || !BASE64URL_PATTERN.test(value) || value.length % 4 === 1) return null;
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
  const keysetDescriptors = snapshotExactDataDescriptors(keyset, ["active_key_id", "keys"], configurationError);
  const activeKeyId = keysetDescriptors.active_key_id!.value;
  const candidates = snapshotExactArray(keysetDescriptors.keys!.value, MAX_SIGNING_KEYS, configurationError);
  if (typeof activeKeyId !== "string" || !KEY_ID_PATTERN.test(activeKeyId)
    || candidates.length < 1 || candidates.length > MAX_SIGNING_KEYS) return configurationError("invalid MCP cursor signing keyset");
  const keys = new Map<string, McpCursorSigningKey>();
  for (const candidate of candidates) {
    const descriptors = snapshotExactDataDescriptors(candidate, ["key_id", "secret"], configurationError);
    const keyId = descriptors.key_id!.value;
    const secret = descriptors.secret!.value;
    if (typeof keyId !== "string" || !KEY_ID_PATTERN.test(keyId)
      || !(secret instanceof Uint8Array) || isProxy(secret)
      || (Object.getPrototypeOf(secret) !== Uint8Array.prototype && !Buffer.isBuffer(secret))
      || secret.byteLength < MIN_SIGNING_SECRET_BYTES || secret.byteLength > MAX_SIGNING_SECRET_BYTES
      || secret.buffer instanceof SharedArrayBuffer
      || keys.has(keyId)) return configurationError("invalid MCP cursor signing keyset");
    keys.set(keyId, Object.freeze({ key_id: keyId, secret: new Uint8Array(secret) }));
  }
  const activeKey = keys.get(activeKeyId);
  if (!activeKey) return configurationError("active MCP cursor signing key is absent");
  return { activeKey, keys };
};

const snapshotBindings = (value: unknown, reject: Reject): Readonly<McpCursorBindings> => {
  const descriptors = snapshotExactDataDescriptors(value, BINDING_KEYS, reject);
  const snapshot = {} as Record<keyof McpCursorBindings, string>;
  for (const key of BINDING_KEYS) {
    const field = descriptors[key]!.value;
    if (typeof field !== "string" || !DIGEST_PATTERN.test(field)) return reject("cursor bindings must be exact SHA-256 digests");
    snapshot[key] = field;
  }
  return Object.freeze(snapshot);
};

const snapshotIssueRequest = (request: IssueMcpCursorRequest): Readonly<IssueMcpCursorRequest> => {
  const descriptors = snapshotExactDataDescriptors(
    request,
    ["last_visible_key", "bindings", "issued_at_epoch_seconds", "ttl_seconds"],
    configurationError,
  );
  const lastVisibleKey = descriptors.last_visible_key!.value;
  const issuedAt = descriptors.issued_at_epoch_seconds!.value;
  const ttl = descriptors.ttl_seconds!.value;
  if (!validateOpaqueLastVisibleKey(lastVisibleKey)) configurationError("last visible key must be a content-free stable-visible-keyset token");
  if (!Number.isSafeInteger(issuedAt) || (issuedAt as number) < 0
    || !Number.isSafeInteger(ttl) || (ttl as number) < 1 || (ttl as number) > MAX_CURSOR_TTL_SECONDS
    || (issuedAt as number) > Number.MAX_SAFE_INTEGER - (ttl as number)) configurationError("invalid MCP cursor lifetime");
  return Object.freeze({
    last_visible_key: lastVisibleKey,
    bindings: snapshotBindings(descriptors.bindings!.value, configurationError),
    issued_at_epoch_seconds: issuedAt as number,
    ttl_seconds: ttl as number,
  });
};

const snapshotVerifyRequest = (request: VerifyMcpCursorRequest): Readonly<VerifyMcpCursorRequest> => {
  const descriptors = snapshotExactDataDescriptors(request, ["bindings", "now_epoch_seconds"], configurationError);
  const now = descriptors.now_epoch_seconds!.value;
  if (!Number.isSafeInteger(now) || (now as number) < 0) configurationError("invalid MCP cursor verification context");
  return Object.freeze({
    bindings: snapshotBindings(descriptors.bindings!.value, configurationError),
    now_epoch_seconds: now as number,
  });
};

const validateOpaqueLastVisibleKey = (value: unknown): value is OpaqueVisibleKeyset =>
  typeof value === "string" && OPAQUE_VISIBLE_KEYSET_PATTERN.test(value);

/**
 * Makes the caller acknowledge the stable-visible-keyset boundary before a
 * value can be issued. This validates the fixed content-free token grammar;
 * the page adapter remains responsible for deriving and resolving the handle
 * solely from visible rows in the endpoint's deterministic sort order.
 */
export const asOpaqueVisibleKeyset = (encodedStableVisibleKeyset: string): OpaqueVisibleKeyset => {
  if (!validateOpaqueLastVisibleKey(encodedStableVisibleKeyset)) {
    return configurationError("last visible keyset must be a content-free vk1 digest token");
  }
  return encodedStableVisibleKeyset;
};

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
  const descriptors = snapshotExactDataDescriptors(value, PAYLOAD_KEYS, rejectInvalidCursor);
  const version = descriptors.version!.value;
  const issuedAt = descriptors.issued_at_epoch_seconds!.value;
  const expiresAt = descriptors.expires_at_epoch_seconds!.value;
  const lastVisibleKey = descriptors.last_visible_key!.value;
  if (version !== CURSOR_VERSION
    || !Number.isSafeInteger(issuedAt) || (issuedAt as number) < 0
    || !Number.isSafeInteger(expiresAt) || (expiresAt as number) < 0
    || !validateOpaqueLastVisibleKey(lastVisibleKey)) return invalid();
  const payload: CursorPayload = Object.freeze({
    version: CURSOR_VERSION,
    issued_at_epoch_seconds: issuedAt as number,
    expires_at_epoch_seconds: expiresAt as number,
    last_visible_key: lastVisibleKey,
    bindings: snapshotBindings(descriptors.bindings!.value, rejectInvalidCursor),
  });
  let canonical: string;
  try {
    canonical = canonicalJson(payload as unknown as JsonValue);
  } catch {
    return invalid();
  }
  if (canonical !== text) return invalid();
  return payload;
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
  const snapshot = snapshotIssueRequest(request);
  const { activeKey } = normalizeSigningKeyset(signingKeyset);
  const payload: CursorPayload = {
    version: CURSOR_VERSION,
    issued_at_epoch_seconds: snapshot.issued_at_epoch_seconds,
    expires_at_epoch_seconds: snapshot.issued_at_epoch_seconds + snapshot.ttl_seconds,
    last_visible_key: snapshot.last_visible_key,
    bindings: snapshot.bindings,
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
  const snapshot = snapshotVerifyRequest(request);
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
    || snapshot.now_epoch_seconds < payload.issued_at_epoch_seconds
    || snapshot.now_epoch_seconds >= payload.expires_at_epoch_seconds
    || !bindingsEqual(payload.bindings, snapshot.bindings)) {
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
