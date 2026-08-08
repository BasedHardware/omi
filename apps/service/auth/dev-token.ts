import { createHmac, timingSafeEqual } from "node:crypto";
import { isProxy } from "node:util/types";

import type { ApplicationMemoryReadAuthorizationRequest } from "../../../core/retrieve/authorization-boundary";

/**
 * Dev-mode HMAC token issuer/verifier seam.
 *
 * This is deliberately not an auth system: callers inject the keyset and clock,
 * HTTP handlers stay free of issuer details, and a real credential adapter can
 * replace this module without changing those handlers. No production
 * credentials, Firebase, network, env-var secret loading, wall clock, or
 * Math.random live here.
 */
const TOKEN_PREFIX = "dev1";
const TOKEN_VERSION = 1;
const SIGNATURE_BYTES = 32;
const MAX_SIGNING_KEYS = 8;
const MIN_SIGNING_SECRET_BYTES = 32;
const MAX_SIGNING_SECRET_BYTES = 4_096;
const MAX_PAYLOAD_BYTES = 3_072;
const MAX_TOKEN_TTL_SECONDS = 86_400;
const MAX_TOKEN_ENCODED_BYTES = 4_096;
const MAX_UID_CODE_UNITS = 128;

const KEY_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;
const UID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const BASE64URL_PATTERN = /^[A-Za-z0-9_-]+$/;
const DUMMY_SECRET = new Uint8Array(MIN_SIGNING_SECRET_BYTES);
const DUMMY_SIGNATURE = new Uint8Array(SIGNATURE_BYTES);

// The only memory-read scope the core authorization boundary currently gates on.
// Mirrors REQUIRED_MEMORY_READ_SCOPE in authorization-boundary.ts (unexported).
const REQUIRED_MEMORY_READ_SCOPE = "memories.read";

type JsonValue = null | boolean | number | string | readonly JsonValue[] | { readonly [key: string]: JsonValue };

export interface DevPrincipal {
  readonly uid: string;
}

export interface DevTokenSigningKey {
  readonly key_id: string;
  readonly secret: Uint8Array;
}

export interface DevTokenSigningKeyset {
  readonly active_key_id: string;
  readonly keys: readonly DevTokenSigningKey[];
}

export interface DevTokenIssuerConfig {
  readonly signing_keyset: DevTokenSigningKeyset;
  readonly ttl_seconds: number;
}

export interface DevTokenIssuer {
  issue(uid: string, nowEpochSeconds: number): string;
  resolve(token: string, nowEpochSeconds: number): DevPrincipal | null;
}

// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
export interface DevPrincipalAuthorizationOptions {
  // domain-pending(DIV-DOMAPPS-001)
  readonly app_id: string;
  // domain-pending(DIV-DOMAPPS-006)
  readonly key_id: string;
}

interface TokenPayload {
  readonly version: 1;
  readonly uid: string;
  readonly issued_at_epoch_seconds: number;
  readonly expires_at_epoch_seconds: number;
}

const PAYLOAD_KEYS = Object.freeze([
  "expires_at_epoch_seconds",
  "issued_at_epoch_seconds",
  "uid",
  "version",
] as const);

const configurationError = (message: string): never => { throw new TypeError(message); };
type Reject = (message: string) => never;

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

const trySnapshotExactDataDescriptors = (
  value: unknown,
  expectedKeys: readonly string[],
): Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>> | null => {
  if (value === null || typeof value !== "object" || isProxy(value) || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key === "symbol")) return null;
  const keys = (ownKeys as string[]).sort();
  const expected = [...expectedKeys].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) return null;
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
    if (!Number.isFinite(value)) configurationError("token payload rejects non-finite numbers");
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

const normalizeSigningKeyset = (keyset: DevTokenSigningKeyset): {
  readonly activeKey: DevTokenSigningKey;
  readonly keys: ReadonlyMap<string, DevTokenSigningKey>;
} => {
  const keysetDescriptors = snapshotExactDataDescriptors(keyset, ["active_key_id", "keys"], configurationError);
  const activeKeyId = keysetDescriptors.active_key_id!.value;
  const candidates = snapshotExactArray(keysetDescriptors.keys!.value, MAX_SIGNING_KEYS, configurationError);
  if (typeof activeKeyId !== "string" || !KEY_ID_PATTERN.test(activeKeyId)
    || candidates.length < 1 || candidates.length > MAX_SIGNING_KEYS) return configurationError("invalid dev token signing keyset");
  const keys = new Map<string, DevTokenSigningKey>();
  for (const candidate of candidates) {
    const descriptors = snapshotExactDataDescriptors(candidate, ["key_id", "secret"], configurationError);
    const keyId = descriptors.key_id!.value;
    const secret = descriptors.secret!.value;
    if (typeof keyId !== "string" || !KEY_ID_PATTERN.test(keyId)
      || !(secret instanceof Uint8Array) || isProxy(secret)
      || (Object.getPrototypeOf(secret) !== Uint8Array.prototype && !Buffer.isBuffer(secret))
      || secret.byteLength < MIN_SIGNING_SECRET_BYTES || secret.byteLength > MAX_SIGNING_SECRET_BYTES
      || secret.buffer instanceof SharedArrayBuffer
      || keys.has(keyId)) return configurationError("invalid dev token signing keyset");
    keys.set(keyId, Object.freeze({ key_id: keyId, secret: new Uint8Array(secret) }));
  }
  const activeKey = keys.get(activeKeyId);
  if (!activeKey) return configurationError("active dev token signing key is absent");
  return { activeKey, keys };
};

const snapshotIssuerConfig = (config: DevTokenIssuerConfig): {
  readonly activeKey: DevTokenSigningKey;
  readonly keys: ReadonlyMap<string, DevTokenSigningKey>;
  readonly ttlSeconds: number;
} => {
  const descriptors = snapshotExactDataDescriptors(config, ["signing_keyset", "ttl_seconds"], configurationError);
  const ttl = descriptors.ttl_seconds!.value;
  if (!Number.isSafeInteger(ttl) || (ttl as number) < 1 || (ttl as number) > MAX_TOKEN_TTL_SECONDS) {
    return configurationError("invalid dev token lifetime");
  }
  const { activeKey, keys } = normalizeSigningKeyset(descriptors.signing_keyset!.value as DevTokenSigningKeyset);
  return { activeKey, keys, ttlSeconds: ttl as number };
};

const requireSafeEpochSeconds = (value: unknown, label: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) configurationError(`invalid ${label}`);
  return value as number;
};

const requireUid = (value: unknown): string => {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_UID_CODE_UNITS
    || !UID_PATTERN.test(value)) configurationError("invalid dev token uid");
  return value;
};

const parsePayload = (encodedPayload: string): TokenPayload | null => {
  const decoded = decodeCanonicalBase64Url(encodedPayload, MAX_PAYLOAD_BYTES);
  if (!decoded) return null;
  const text = Buffer.from(decoded).toString("utf8");
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return null;
  }
  const descriptors = trySnapshotExactDataDescriptors(value, PAYLOAD_KEYS);
  if (!descriptors) return null;
  const version = descriptors.version!.value;
  const uid = descriptors.uid!.value;
  const issuedAt = descriptors.issued_at_epoch_seconds!.value;
  const expiresAt = descriptors.expires_at_epoch_seconds!.value;
  if (version !== TOKEN_VERSION
    || typeof uid !== "string" || !UID_PATTERN.test(uid)
    || !Number.isSafeInteger(issuedAt) || (issuedAt as number) < 0
    || !Number.isSafeInteger(expiresAt) || (expiresAt as number) < 0) return null;
  const payload: TokenPayload = Object.freeze({
    version: TOKEN_VERSION,
    uid,
    issued_at_epoch_seconds: issuedAt as number,
    expires_at_epoch_seconds: expiresAt as number,
  });
  let canonical: string;
  try {
    canonical = canonicalJson(payload as unknown as JsonValue);
  } catch {
    return null;
  }
  if (canonical !== text) return null;
  return payload;
};

/**
 * Builds a hermetic issuer/verifier closed over a snapshotted keyset and TTL.
 * Time is always caller-supplied as `nowEpochSeconds`.
 */
export const createDevTokenIssuer = (config: DevTokenIssuerConfig): DevTokenIssuer => {
  const snapshot = snapshotIssuerConfig(config);
  return Object.freeze({
    issue(uid: string, nowEpochSeconds: number): string {
      const principalUid = requireUid(uid);
      const issuedAt = requireSafeEpochSeconds(nowEpochSeconds, "dev token issue time");
      if (issuedAt > Number.MAX_SAFE_INTEGER - snapshot.ttlSeconds) configurationError("invalid dev token lifetime");
      const payload: TokenPayload = {
        version: TOKEN_VERSION,
        uid: principalUid,
        issued_at_epoch_seconds: issuedAt,
        expires_at_epoch_seconds: issuedAt + snapshot.ttlSeconds,
      };
      const encodedPayload = encodeBase64Url(Buffer.from(canonicalJson(payload as unknown as JsonValue), "utf8"));
      const encodedSignature = encodeBase64Url(
        signature(TOKEN_PREFIX, snapshot.activeKey.key_id, encodedPayload, snapshot.activeKey.secret),
      );
      const token = `${TOKEN_PREFIX}.${snapshot.activeKey.key_id}.${encodedPayload}.${encodedSignature}`;
      if (Buffer.byteLength(token, "utf8") > MAX_TOKEN_ENCODED_BYTES) configurationError("dev token exceeds encoded size bound");
      return token;
    },
    resolve(token: string, nowEpochSeconds: number): DevPrincipal | null {
      const now = requireSafeEpochSeconds(nowEpochSeconds, "dev token verification time");
      if (typeof token !== "string" || Buffer.byteLength(token, "utf8") > MAX_TOKEN_ENCODED_BYTES) return null;
      const parts = token.split(".");
      if (parts.length !== 4) return null;
      const [prefix, keyId, encodedPayload, encodedSignature] = parts as [string, string, string, string];
      if (prefix !== TOKEN_PREFIX || !KEY_ID_PATTERN.test(keyId)) return null;

      // Unknown key IDs and malformed signatures still execute a fixed-size HMAC
      // comparison. Failure modes stay indistinguishable: resolve returns null only.
      const configuredKey = snapshot.keys.get(keyId);
      const expectedSignature = signature(prefix, keyId, encodedPayload, configuredKey?.secret ?? DUMMY_SECRET);
      const decodedSignature = decodeCanonicalBase64Url(encodedSignature, SIGNATURE_BYTES);
      const suppliedSignature = decodedSignature?.byteLength === SIGNATURE_BYTES ? decodedSignature : DUMMY_SIGNATURE;
      const signatureMatches = timingSafeEqual(Buffer.from(expectedSignature), Buffer.from(suppliedSignature));
      if (!configuredKey || decodedSignature?.byteLength !== SIGNATURE_BYTES || !signatureMatches) return null;

      const payload = parsePayload(encodedPayload);
      if (!payload) return null;
      const ttl = payload.expires_at_epoch_seconds - payload.issued_at_epoch_seconds;
      if (ttl < 1 || ttl > MAX_TOKEN_TTL_SECONDS
        || now < payload.issued_at_epoch_seconds
        || now >= payload.expires_at_epoch_seconds) return null;
      return Object.freeze({ uid: payload.uid });
    },
  });
};

/**
 * Maps a verified DevPrincipal onto the live application authorization request
 * shape. The core authorization boundary today only accepts credential_kind
 * "mcp_api_key" and grant consumer "mcp". Mapping onto those existing values is
 * intentional: new authority classes are David's decision and are explicitly
 * out of bounds for this seam.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-006)
export const devPrincipalToAuthorizationRequest = (
  principal: DevPrincipal,
  options: DevPrincipalAuthorizationOptions,
): ApplicationMemoryReadAuthorizationRequest => {
  const principalDescriptors = snapshotExactDataDescriptors(principal, ["uid"], configurationError);
  const optionDescriptors = snapshotExactDataDescriptors(options, ["app_id", "key_id"], configurationError);
  const uid = requireUid(principalDescriptors.uid!.value);
  const appId = optionDescriptors.app_id!.value;
  const keyId = optionDescriptors.key_id!.value;
  // domain-pending(DIV-DOMAPPS-001)
  if (typeof appId !== "string" || appId.length === 0 || appId.length > MAX_UID_CODE_UNITS) {
    configurationError("invalid authorization app_id");
  }
  // domain-pending(DIV-DOMAPPS-006)
  if (typeof keyId !== "string" || keyId.length === 0 || keyId.length > MAX_UID_CODE_UNITS) {
    configurationError("invalid authorization key_id");
  }
  // domain-pending(DIV-DOMCORE-001)
  // domain-pending(DIV-DOMAPPS-001)
  // domain-pending(DIV-DOMAPPS-006)
  // domain-pending(DIV-DOMX-006)
  return Object.freeze({
    owner_account_id: uid,
    credential: Object.freeze({
      owner_account_id: uid,
      // Must remain "mcp_api_key": inventing a developer/dev credential kind
      // would create a new authority class (David decides; out of bounds here).
      credential_kind: "mcp_api_key" as const,
      // domain-pending(DIV-DOMAPPS-001)
      app_id: appId,
      // domain-pending(DIV-DOMAPPS-006)
      key_id: keyId,
      scopes: Object.freeze([REQUIRED_MEMORY_READ_SCOPE]),
      active: true,
    }),
    // domain-pending(DIV-DOMX-006)
    persisted_grant: Object.freeze({
      owner_account_id: uid,
      // Must remain "mcp": inventing a developer/dev consumer would create a
      // new authority class (David decides; out of bounds here).
      consumer: "mcp" as const,
      // domain-pending(DIV-DOMAPPS-001)
      app_id: appId,
      // domain-pending(DIV-DOMAPPS-006)
      key_id: keyId,
      enabled: true,
      default_read: true,
      scopes: Object.freeze([REQUIRED_MEMORY_READ_SCOPE]),
    }),
  });
};
