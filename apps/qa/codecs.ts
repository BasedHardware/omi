// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
import { createHmac } from "node:crypto";

/**
 * QA-only reader-scoped keyed reference codecs.
 *
 * These turn internal coordinates into the opaque public references the ratified
 * read contract emits. They are keyed rather than plain hashes so that knowing an
 * internal ref does not let anyone recompute its public reference, and
 * reader-scoped so the same internal ref under two readers cannot be correlated.
 */

const MIN_SECRET_BYTES = 32;

const DOMAIN_VISIBLE_KEY = "visible-key-v1";
const DOMAIN_ITEM_REF = "item-ref-v1";
const DOMAIN_CITATION_REF = "citation-ref-v1";
const DOMAIN_TRACE_REF = "trace-ref-v1";

export interface QaCodecKeyMaterial {
  /** Reader-scoped secret. At least 32 bytes. */
  readonly secret: Uint8Array;
  /** Binds every derived reference to one reader/authorization scope. */
  readonly reader_scope: string;
}

export interface QaReferenceCodecs {
  readonly encodeVisibleKey: (canonicalSortTuple: string) => string;
  readonly encodeItemRef: (candidateRef: string) => string;
  readonly encodeCitationRef: (canonicalClosure: string) => string;
  readonly encodeTraceRef: (internalRef: string) => string;
}

/**
 * Length-prefixed UTF-8 frame: each field is a uint32-BE byte length followed by
 * exactly that many bytes. Injective because lengths uniquely delimit fields, so two
 * distinct (domain, reader_scope, input) triples cannot serialize to the same bytes.
 */
const frameMessage = (domain: string, readerScope: string, input: string): Buffer => {
  const domainBytes = Buffer.from(domain, "utf8");
  const scopeBytes = Buffer.from(readerScope, "utf8");
  const inputBytes = Buffer.from(input, "utf8");
  const message = Buffer.allocUnsafe(12 + domainBytes.length + scopeBytes.length + inputBytes.length);
  let offset = 0;
  message.writeUInt32BE(domainBytes.length, offset);
  offset += 4;
  domainBytes.copy(message, offset);
  offset += domainBytes.length;
  message.writeUInt32BE(scopeBytes.length, offset);
  offset += 4;
  scopeBytes.copy(message, offset);
  offset += scopeBytes.length;
  message.writeUInt32BE(inputBytes.length, offset);
  offset += 4;
  inputBytes.copy(message, offset);
  return message;
};

const hmacHex = (secret: Uint8Array, message: Buffer): string =>
  createHmac("sha256", Buffer.from(secret))
    .update(message)
    .digest("hex");

const makeEncoder = (
  secret: Uint8Array,
  readerScope: string,
  domain: string,
  prefix: string,
): ((input: string) => string) => (input: string) => `${prefix}${hmacHex(secret, frameMessage(domain, readerScope, input))}`;

export const createQaReferenceCodecs = (key: QaCodecKeyMaterial): QaReferenceCodecs => {
  if (!(key.secret instanceof Uint8Array) || key.secret.byteLength < MIN_SECRET_BYTES) {
    throw new TypeError("QA codec secret must be at least 32 bytes");
  }
  if (typeof key.reader_scope !== "string" || key.reader_scope.length === 0) {
    throw new TypeError("QA codec reader_scope must be non-empty");
  }
  const secret = new Uint8Array(key.secret);
  const { reader_scope } = key;
  return Object.freeze({
    encodeVisibleKey: makeEncoder(secret, reader_scope, DOMAIN_VISIBLE_KEY, "vk1_"),
    encodeItemRef: makeEncoder(secret, reader_scope, DOMAIN_ITEM_REF, "mem1_"),
    encodeCitationRef: makeEncoder(secret, reader_scope, DOMAIN_CITATION_REF, "cit1_"),
    encodeTraceRef: makeEncoder(secret, reader_scope, DOMAIN_TRACE_REF, "tr1_"),
  });
};
