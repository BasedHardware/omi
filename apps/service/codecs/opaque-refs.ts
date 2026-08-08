// Markers name only the terms this module actually uses: the memory/item
// concept, the citation/evidence concept, and the keyed-digest concept.
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-001)
import { createHmac } from "node:crypto";
import { isProxy } from "node:util/types";

/**
 * Reader-scoped opaque reference codecs for ApplicationReadPorts.
 *
 * Outputs are content-free handles only: never raw internal coordinates.
 * Hermetic — no wall clock, randomness, network, or process env.
 */
const MIN_ROOT_SECRET_BYTES = 32;
const MAX_ROOT_SECRET_BYTES = 4_096;
const DIGEST_PATTERN = /^[a-f0-9]{64}$/;
const STABLE_VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const ITEM_REF = /^mem1_[a-f0-9]{64}$/;
const CITATION_REF = /^cit1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;

/** Key-derivation label for the per-reader subkey. */
const READER_SUBKEY_LABEL = "omi.service.opaque-reader-subkey.v1";
/** Distinct domain labels so identical inputs cannot collide across codecs. */
const DOMAIN_VISIBLE_KEY = "omi.service.opaque-visible-key.v1";
const DOMAIN_ITEM_REF = "omi.service.opaque-item-ref.v1";
const DOMAIN_CITATION_REF = "omi.service.opaque-citation-ref.v1";
const DOMAIN_TRACE_REF = "omi.service.opaque-trace-ref.v1";

const CONFIG_KEYS = Object.freeze(["reader_projection_digest", "root_secret"] as const);

export interface ReaderScopedOpaqueCodecConfig {
  /** Root HMAC secret; must be at least 32 bytes. Copied at factory time. */
  readonly root_secret: Uint8Array;
  /** Reader identity digest that scopes every opaque handle. */
  readonly reader_projection_digest: string;
}

export interface ReaderScopedOpaqueCodecs {
  readonly encodeVisibleKey: (input: string) => string;
  readonly encodeItemRef: (input: string) => string;
  readonly encodeCitationRef: (input: string) => string;
  readonly encodeTraceRef: (input: string) => string;
}

const configurationError = (message: string): never => {
  throw new TypeError(message);
};

const snapshotExactDataDescriptors = (
  value: unknown,
  expectedKeys: readonly string[],
): Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>> => {
  if (value === null || typeof value !== "object" || isProxy(value) || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    return configurationError("opaque codec config requires an exact plain object");
  }
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some((key) => typeof key === "symbol")) {
    return configurationError("opaque codec config rejects symbol keys");
  }
  const keys = (ownKeys as string[]).sort();
  const expected = [...expectedKeys].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    return configurationError("opaque codec config has unexpected fields");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      return configurationError("opaque codec config allows only enumerable own data properties");
    }
  }
  return descriptors as Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;
};

const copyRootSecret = (value: unknown): Uint8Array => {
  if (!(value instanceof Uint8Array) || isProxy(value)
    || (Object.getPrototypeOf(value) !== Uint8Array.prototype && !Buffer.isBuffer(value))
    || value.buffer instanceof SharedArrayBuffer
    || value.byteLength < MIN_ROOT_SECRET_BYTES
    || value.byteLength > MAX_ROOT_SECRET_BYTES) {
    return configurationError("opaque codec root_secret must be a 32..4096 byte Uint8Array");
  }
  return new Uint8Array(value);
};

const deriveReaderSubkey = (rootSecret: Uint8Array, readerProjectionDigest: string): Buffer =>
  createHmac("sha256", Buffer.from(rootSecret))
    .update(READER_SUBKEY_LABEL, "ascii")
    .update("\0", "ascii")
    .update(readerProjectionDigest, "ascii")
    .digest();

const encodeOpaque = (
  readerSubkey: Buffer,
  domainLabel: string,
  prefix: string,
  pattern: RegExp,
  input: string,
): string => {
  if (typeof input !== "string") {
    return configurationError("opaque codec input must be a string");
  }
  const hex = createHmac("sha256", readerSubkey)
    .update(domainLabel, "ascii")
    .update("\0", "ascii")
    .update(input, "utf8")
    .digest("hex");
  const encoded = `${prefix}${hex}`;
  if (!pattern.test(encoded) || !DIGEST_PATTERN.test(hex)) {
    return configurationError("opaque codec produced an invalid handle");
  }
  return encoded;
};

/**
 * Builds the four ApplicationReadPorts opaque codecs, keyed to one reader.
 * Same reader + same input is deterministic; different readers never share
 * opaque values for the same internal coordinate.
 */
export const createReaderScopedOpaqueCodecs = (
  config: ReaderScopedOpaqueCodecConfig,
): Readonly<ReaderScopedOpaqueCodecs> => {
  const descriptors = snapshotExactDataDescriptors(config, CONFIG_KEYS);
  const readerProjectionDigest = descriptors.reader_projection_digest!.value;
  if (typeof readerProjectionDigest !== "string" || !DIGEST_PATTERN.test(readerProjectionDigest)) {
    return configurationError("opaque codec reader_projection_digest must be a lowercase SHA-256 hex digest");
  }
  const rootSecret = copyRootSecret(descriptors.root_secret!.value);
  const readerSubkey = deriveReaderSubkey(rootSecret, readerProjectionDigest);
  // Drop the copied root material from the closure surface; only the derived
  // reader subkey is retained for encoding.
  rootSecret.fill(0);

  return Object.freeze({
    encodeVisibleKey: (input: string): string =>
      encodeOpaque(readerSubkey, DOMAIN_VISIBLE_KEY, "vk1_", STABLE_VISIBLE_KEY, input),
    encodeItemRef: (input: string): string =>
      encodeOpaque(readerSubkey, DOMAIN_ITEM_REF, "mem1_", ITEM_REF, input),
    encodeCitationRef: (input: string): string =>
      encodeOpaque(readerSubkey, DOMAIN_CITATION_REF, "cit1_", CITATION_REF, input),
    encodeTraceRef: (input: string): string =>
      encodeOpaque(readerSubkey, DOMAIN_TRACE_REF, "tr1_", TRACE_REF, input),
  });
};
