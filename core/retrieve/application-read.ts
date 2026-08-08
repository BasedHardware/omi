// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { isProxy } from "node:util/types";

import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
import {
  SYNTHESIZED_READ_CONTRACT_VERSION,
  parseCitationRef,
  parseRecallFrontier,
  parseSha256Digest,
  parseSynthesizedItemId,
  parseSynthesizedPageJson,
  parseSynthesizedText,
} from "@omi-core/ratified-contracts/projections/synthesized";

import {
  isApplicationGrantProjectedTreeInput,
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
  type ApplicationProjectionLoad,
} from "./authorization-boundary";
import {
  buildContentSafeRecallTrace,
  computeRecallCompleteness,
  emitRecallTraceSafely,
  mergeAuthorizedRecallCandidates,
  qualifyRecallAbsence,
  type AuthorizedRecallCandidate,
  type ContentSafeRecallTrace,
  type RecallCompletenessInput,
  type RecallCompletenessResult,
} from "./recall-integrity";

const SHA256_HEX = /^[a-f0-9]{64}$/;
const INTERNAL_REF = /^[\x21-\x7e]{1,512}$/;
const STABLE_VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const SYNTHESIS_VERSION = /^[\x21-\x7e]{1,128}$/;
const MAX_PAGE_LIMIT = 100;
const MAX_CURSOR_CODE_UNITS = 4_096;
export const MAX_APPLICATION_OVERLAY_ITEMS = 1_000;
export const MAX_APPLICATION_OVERLAY_BYTES = 2_000_000;

type PlainJson = null | boolean | number | string | readonly PlainJson[] | { readonly [key: string]: PlainJson };
type CandidateSource = "durable" | "overlay";

export interface ApplicationSynthesisProvenance {
  readonly synthesis_version: string;
  readonly input_digest: string;
  readonly output_digest: string;
}

/**
 * Internal, already-synthesized and already-grounded input. Every coordinate
 * in this record is server-private; only keyed codec results may reach the
 * ratified page DTO.
 */
export interface ApplicationSynthesizedCandidateRecord {
  readonly owner_account_id: string;
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly authorization_generation_digest: string;
  readonly projection_generation_digest: string;
  readonly projected_content_digest: string;
  readonly durable_generation_digest: string;
  readonly overlay_generation_digest: string;
  readonly declared_generation_digest: string;
  readonly accepted_generation_digest: string;
  readonly stm_generation_digest: string;
  readonly candidate_ref: string;
  readonly dedupe_ref: string;
  readonly dedupe_rank: number;
  readonly order_key: string;
  readonly stable_visible_key: string;
  readonly origin: "durable" | "stm" | "accepted_unprocessed";
  readonly frontier: string;
  readonly supersedes_refs: readonly string[];
  readonly effective_policy: {
    readonly subject_class: string;
    readonly sensitivity: string;
    readonly capture_class: string;
  };
  readonly synthesized_text: string;
  readonly citation_provenance_ids: readonly string[];
  readonly synthesis_provenance: ApplicationSynthesisProvenance | null;
}

export interface ApplicationRecallGenerationDigests {
  readonly authorization_generation_digest: string;
  readonly durable_generation_digest: string;
  readonly overlay_generation_digest: string;
  readonly declared_generation_digest: string;
  readonly accepted_generation_digest: string;
  readonly stm_generation_digest: string;
}

/**
 * Provider-neutral, content-free coordinates from the coherent read. The
 * composition layer maps them to its protocol bindings and supplies its own
 * cursor-policy/signing configuration; this core knows neither.
 */
export interface ApplicationReadCoherentCoordinates {
  readonly owner_identity_digest: string;
  readonly application_identity_digest: string;
  readonly credential_identity_digest: string;
  readonly authorization_state_digest: string;
  readonly grant_state_digest: string;
  readonly account_head_digest: string;
  readonly authorized_graph_digest: string;
  readonly coherent_projection_commit_digest: string;
  readonly visibility_digest: string;
  readonly filter_digest: string;
  readonly query_digest: string;
  readonly source_digest: string;
  readonly read_mode_digest: string;
  readonly read_timestamp_epoch_seconds: number;
}

export interface ApplicationRecallOverlayLoad {
  readonly max_items: number;
  readonly max_bytes: number;
  readonly candidates: readonly ApplicationSynthesizedCandidateRecord[];
}

/** One adapter-owned coherent read; this file does not define a production store. */
export interface ApplicationRecallCoherentLoad {
  readonly projection_load: ApplicationProjectionLoad;
  readonly overlay: ApplicationRecallOverlayLoad;
  readonly coverage: RecallCompletenessInput;
  readonly generations: ApplicationRecallGenerationDigests;
  readonly read_coordinates: ApplicationReadCoherentCoordinates;
}

export interface ApplicationReadAuthorizationAttempt {
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest;
  readonly load_coherent: () => ApplicationRecallCoherentLoad;
}

export interface ApplicationSynthesizedPageRequest {
  readonly limit: number;
  /** Raw protocol cursor; authenticity is verified against this read's attestation. */
  readonly cursor: string | null;
}

export interface ApplicationReadSnapshotAttestation extends ApplicationReadCoherentCoordinates {
  readonly synthesized_projection_generation_digest: string;
  readonly projected_content_digest: string;
  readonly durable_generation_digest: string;
  readonly overlay_generation_digest: string;
  readonly declared_generation_digest: string;
  readonly accepted_generation_digest: string;
  readonly stm_generation_digest: string;
  readonly coverage: RecallCompletenessInput;
}

export interface ApplicationReadAttestation extends ApplicationReadSnapshotAttestation {
  readonly last_visible_key: string | null;
}

export interface ApplicationSynthesizedPageResult {
  readonly canonical_json: string;
  readonly attestation: ApplicationReadAttestation;
}

export interface ApplicationReadPorts {
  /** Resolves current credential/grant state and a zero-argument coherent loader. */
  readonly resolveAttempt: () => ApplicationReadAuthorizationAttempt;
  /** Receives exactly the branded authorized projection, and no request authority. */
  readonly loadDurableCandidates: (
    input: ApplicationGrantProjectedTreeInputSnapshot,
  ) => unknown;
  /** Reader-scoped keyed codecs. Raw internal coordinates are never accepted as output. */
  readonly encodeItemRef: (candidateRef: string) => unknown;
  readonly encodeCitationRef: (provenanceId: string) => unknown;
  readonly encodeTraceRef: (internalRef: string) => unknown;
  /** Verifies all protocol replay bindings against this exact coherent snapshot. */
  readonly verifyCursor: (cursor: string, attestation: ApplicationReadSnapshotAttestation) => unknown;
  /** Protocol adapter mints the signed cursor from only the last visible stable key. */
  readonly issueCursor: (lastVisibleKey: string, attestation: ApplicationReadSnapshotAttestation) => unknown;
  readonly traceSink: (trace: ContentSafeRecallTrace) => void | Promise<void>;
}

export class ApplicationReadInvalidatedError extends Error {
  readonly code = "application_read_invalidated" as const;

  constructor() {
    super("application read invalidated during revalidation");
    this.name = "ApplicationReadInvalidatedError";
  }
}

/** The final ratified parser remains the fail-closed wire-contract boundary. */
export class ApplicationReadContractMismatchError extends Error {
  readonly code = "application_read_contract_mismatch" as const;

  constructor() {
    super("application read result is not representable by the ratified contract");
    this.name = "ApplicationReadContractMismatchError";
  }
}

const fail = (message: string): never => { throw new TypeError(`application read ${message}`); };
const compareStrings = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;
const uniqueStrings = (values: readonly string[]): boolean => new Set(values).size === values.length;

const defineDataProperty = (target: object, key: PropertyKey, value: unknown): void => {
  const descriptor = Object.create(null) as PropertyDescriptor;
  descriptor.value = value;
  descriptor.enumerable = true;
  descriptor.configurable = true;
  descriptor.writable = true;
  Object.defineProperty(target, key, descriptor);
};

const ownDescriptorValue = (descriptor: PropertyDescriptor | undefined): unknown => {
  if (!descriptor || !Object.hasOwn(descriptor, "value")) return fail("requires enumerable own data properties");
  return descriptor.value;
};

/**
 * Detaches a hostile graph from one descriptor snapshot per node. Proxies,
 * classes, getters, symbols, hidden fields, sparse/decorated arrays, aliases,
 * cycles and non-JSON values are rejected before semantic reads.
 */
const detachPlainJsonStrict = (input: unknown): PlainJson => {
  const seen = new WeakSet<object>();
  const copy = (value: unknown): PlainJson => {
    if (value === null || typeof value === "string" || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) return fail("rejects non-finite numbers");
      return Object.is(value, -0) ? 0 : value;
    }
    if (typeof value !== "object") return fail("accepts plain JSON only");
    if (isProxy(value)) return fail("rejects proxies");
    if (seen.has(value)) return fail("rejects aliases and cycles");
    seen.add(value);

    const array = Array.isArray(value);
    const prototype = Object.getPrototypeOf(value);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype) {
      return fail("rejects non-plain prototypes");
    }
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some((key) => typeof key === "symbol")) return fail("rejects symbol keys");

    if (array) {
      const lengthDescriptor = descriptors.length;
      const rawLength = ownDescriptorValue(lengthDescriptor);
      if (!Number.isSafeInteger(rawLength) || (rawLength as number) < 0
        || !lengthDescriptor || lengthDescriptor.enumerable || lengthDescriptor.configurable) {
        return fail("rejects invalid array lengths");
      }
      const length = rawLength as number;
      if (keys.length !== length + 1) return fail("rejects sparse or decorated arrays");
      const output: PlainJson[] = [];
      for (let index = 0; index < length; index += 1) {
        const descriptor = descriptors[String(index)];
        if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, "value")) {
          return fail("rejects sparse arrays and array accessors");
        }
        output.push(copy(descriptor.value));
      }
      return Object.freeze(output);
    }

    const output: Record<string, PlainJson> = {};
    for (const key of (keys as string[]).sort(compareStrings)) {
      const descriptor = descriptors[key];
      if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, "value")) {
        return fail("rejects accessors and nonenumerable fields");
      }
      defineDataProperty(output, key, copy(descriptor.value));
    }
    return Object.freeze(output);
  };
  return copy(input);
};

const isRecord = (value: PlainJson): value is { readonly [key: string]: PlainJson } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const exactRecord = (value: PlainJson, expected: readonly string[]): value is { readonly [key: string]: PlainJson } => {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value).sort(compareStrings);
  const wanted = [...expected].sort(compareStrings);
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const exactDescriptors = (
  value: unknown,
  expected: readonly string[],
): Readonly<Record<string, PropertyDescriptor>> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return fail("requires an exact plain callback record");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key === "symbol")) return fail("rejects callback-record symbols");
  const actual = (ownKeys as string[]).sort(compareStrings);
  const wanted = [...expected].sort(compareStrings);
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    return fail("rejects unexpected callback-record fields");
  }
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, "value")) {
      return fail("rejects callback-record accessors and hidden fields");
    }
  }
  return descriptors;
};

const callbackValue = (descriptor: PropertyDescriptor | undefined): ((...args: never[]) => unknown) => {
  const value = ownDescriptorValue(descriptor);
  if (typeof value !== "function" || isProxy(value)) return fail("requires non-proxy callback functions");
  return value as (...args: never[]) => unknown;
};

interface SnapshottedPorts {
  readonly resolveAttempt: ApplicationReadPorts["resolveAttempt"];
  readonly loadDurableCandidates: ApplicationReadPorts["loadDurableCandidates"];
  readonly encodeItemRef: ApplicationReadPorts["encodeItemRef"];
  readonly encodeCitationRef: ApplicationReadPorts["encodeCitationRef"];
  readonly encodeTraceRef: ApplicationReadPorts["encodeTraceRef"];
  readonly verifyCursor: ApplicationReadPorts["verifyCursor"];
  readonly issueCursor: ApplicationReadPorts["issueCursor"];
  readonly traceSink: ApplicationReadPorts["traceSink"];
}

const snapshotPorts = (ports: ApplicationReadPorts): SnapshottedPorts => {
  const descriptors = exactDescriptors(ports, [
    "resolveAttempt",
    "loadDurableCandidates",
    "encodeItemRef",
    "encodeCitationRef",
    "encodeTraceRef",
    "verifyCursor",
    "issueCursor",
    "traceSink",
  ]);
  return Object.freeze({
    resolveAttempt: callbackValue(descriptors.resolveAttempt) as ApplicationReadPorts["resolveAttempt"],
    loadDurableCandidates: callbackValue(descriptors.loadDurableCandidates) as ApplicationReadPorts["loadDurableCandidates"],
    encodeItemRef: callbackValue(descriptors.encodeItemRef) as ApplicationReadPorts["encodeItemRef"],
    encodeCitationRef: callbackValue(descriptors.encodeCitationRef) as ApplicationReadPorts["encodeCitationRef"],
    encodeTraceRef: callbackValue(descriptors.encodeTraceRef) as ApplicationReadPorts["encodeTraceRef"],
    verifyCursor: callbackValue(descriptors.verifyCursor) as ApplicationReadPorts["verifyCursor"],
    issueCursor: callbackValue(descriptors.issueCursor) as ApplicationReadPorts["issueCursor"],
    traceSink: callbackValue(descriptors.traceSink) as ApplicationReadPorts["traceSink"],
  });
};

const canonicalPlainJson = (value: PlainJson): string => {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean" || typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) {
    const members: string[] = [];
    for (let index = 0; index < value.length; index += 1) members.push(canonicalPlainJson(value[index]!));
    return `[${members.join(",")}]`;
  }
  const record = value as { readonly [key: string]: PlainJson };
  return `{${Object.keys(record).sort(compareStrings)
    .map((key) => `${JSON.stringify(key)}:${canonicalPlainJson(record[key]!)}`).join(",")}}`;
};

const parsePageRequest = (request: ApplicationSynthesizedPageRequest): Readonly<ApplicationSynthesizedPageRequest> => {
  const value = detachPlainJsonStrict(request);
  if (!exactRecord(value, ["limit", "cursor"])
    || typeof value.limit !== "number" || !Number.isSafeInteger(value.limit)
    || value.limit < 1 || value.limit > MAX_PAGE_LIMIT
    || (value.cursor !== null
      && (typeof value.cursor !== "string" || value.cursor.length > MAX_CURSOR_CODE_UNITS
        || parseKeysetCursor(value.cursor) === null))) {
    return fail("received an invalid page request");
  }
  return Object.freeze({ limit: value.limit, cursor: value.cursor });
};

const GENERATION_KEYS = Object.freeze([
  "authorization_generation_digest",
  "durable_generation_digest",
  "overlay_generation_digest",
  "declared_generation_digest",
  "accepted_generation_digest",
  "stm_generation_digest",
] as const satisfies readonly (keyof ApplicationRecallGenerationDigests)[]);

const parseGenerations = (value: PlainJson): Readonly<ApplicationRecallGenerationDigests> => {
  if (!exactRecord(value, GENERATION_KEYS)) return fail("generation receipt has an invalid shape");
  const output = {} as Record<(typeof GENERATION_KEYS)[number], string>;
  for (const key of GENERATION_KEYS) {
    const digest = value[key];
    if (typeof digest !== "string" || !SHA256_HEX.test(digest) || parseSha256Digest(digest) === null) {
      return fail("generation receipt requires lowercase SHA-256 digests");
    }
    output[key] = digest;
  }
  return Object.freeze(output);
};

interface ParsedCoherentLoad {
  readonly projection_load: ApplicationProjectionLoad;
  readonly overlay: {
    readonly max_items: number;
    readonly max_bytes: number;
    readonly candidates: readonly PlainJson[];
  };
  readonly coverage: RecallCompletenessInput;
  readonly generations: Readonly<ApplicationRecallGenerationDigests>;
  readonly read_coordinates: Readonly<ApplicationReadCoherentCoordinates>;
}

const READ_COORDINATE_DIGEST_KEYS = Object.freeze([
  "owner_identity_digest",
  "application_identity_digest",
  "credential_identity_digest",
  "authorization_state_digest",
  "grant_state_digest",
  "account_head_digest",
  "authorized_graph_digest",
  "coherent_projection_commit_digest",
  "visibility_digest",
  "filter_digest",
  "query_digest",
  "source_digest",
  "read_mode_digest",
] as const satisfies readonly Exclude<keyof ApplicationReadCoherentCoordinates, "read_timestamp_epoch_seconds">[]);

const parseReadCoordinates = (value: PlainJson): Readonly<ApplicationReadCoherentCoordinates> => {
  const expected = [...READ_COORDINATE_DIGEST_KEYS, "read_timestamp_epoch_seconds"];
  if (!exactRecord(value, expected)) return fail("read coordinates have an invalid shape");
  const output = {} as Record<(typeof READ_COORDINATE_DIGEST_KEYS)[number], string>;
  for (const key of READ_COORDINATE_DIGEST_KEYS) {
    const digest = value[key];
    if (typeof digest !== "string" || parseSha256Digest(digest) === null) {
      return fail("read coordinates require lowercase SHA-256 digests");
    }
    output[key] = digest;
  }
  if (typeof value.read_timestamp_epoch_seconds !== "number"
    || !Number.isSafeInteger(value.read_timestamp_epoch_seconds)
    || value.read_timestamp_epoch_seconds < 0) return fail("read coordinates require an authoritative timestamp");
  return Object.freeze({
    ...output,
    read_timestamp_epoch_seconds: value.read_timestamp_epoch_seconds,
  });
};

const parseCoherentLoad = (input: unknown): ParsedCoherentLoad => {
  const value = detachPlainJsonStrict(input);
  if (!exactRecord(value, ["projection_load", "overlay", "coverage", "generations", "read_coordinates"])
    || !exactRecord(value.overlay, ["max_items", "max_bytes", "candidates"])
    || typeof value.overlay.max_items !== "number" || !Number.isSafeInteger(value.overlay.max_items)
    || value.overlay.max_items < 1 || value.overlay.max_items > MAX_APPLICATION_OVERLAY_ITEMS
    || typeof value.overlay.max_bytes !== "number" || !Number.isSafeInteger(value.overlay.max_bytes)
    || value.overlay.max_bytes < 1 || value.overlay.max_bytes > MAX_APPLICATION_OVERLAY_BYTES
    || !Array.isArray(value.overlay.candidates)
    || value.overlay.candidates.length > value.overlay.max_items) return fail("coherent load has an invalid overlay bound");
  const encodedOverlayBytes = Buffer.byteLength(canonicalPlainJson(value.overlay.candidates), "utf8");
  if (encodedOverlayBytes > value.overlay.max_bytes) return fail("coherent load exceeds its overlay byte bound");
  if (!isRecord(value.projection_load) || !isRecord(value.coverage)) return fail("coherent load has an invalid shape");
  const generations = parseGenerations(value.generations);
  const readCoordinates = parseReadCoordinates(value.read_coordinates);
  if (readCoordinates.authorization_state_digest !== generations.authorization_generation_digest) {
    return fail("authorization state and generation coordinates disagree");
  }
  return Object.freeze({
    projection_load: value.projection_load as unknown as ApplicationProjectionLoad,
    overlay: Object.freeze({
      max_items: value.overlay.max_items,
      max_bytes: value.overlay.max_bytes,
      candidates: value.overlay.candidates,
    }),
    coverage: value.coverage as unknown as RecallCompletenessInput,
    generations,
    read_coordinates: readCoordinates,
  });
};

interface ParsedAuthorizationAttempt {
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest;
  readonly load_coherent: () => ApplicationRecallCoherentLoad;
}

const parseAuthorizationAttempt = (input: unknown): ParsedAuthorizationAttempt => {
  const descriptors = exactDescriptors(input, ["authorization_request", "load_coherent"]);
  const authorizationRequest = detachPlainJsonStrict(ownDescriptorValue(descriptors.authorization_request));
  if (!isRecord(authorizationRequest)) return fail("authorization request must be a plain JSON record");
  return Object.freeze({
    authorization_request: authorizationRequest as unknown as ApplicationMemoryReadAuthorizationRequest,
    load_coherent: callbackValue(descriptors.load_coherent) as () => ApplicationRecallCoherentLoad,
  });
};

interface GenerationSignature extends ApplicationRecallGenerationDigests {
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projection_generation_digest: string;
  readonly projected_content_digest: string;
  readonly read_coordinates: Readonly<ApplicationReadCoherentCoordinates>;
  readonly coverage_canonical: string;
}

const buildGenerationSignature = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  generations: ApplicationRecallGenerationDigests,
  readCoordinates: Readonly<ApplicationReadCoherentCoordinates>,
  coverage: RecallCompletenessInput,
): Readonly<GenerationSignature> => {
  const projectionGeneration = input.graph_generation;
  const fields = [
    input.projection_authorization_digest,
    input.reader_projection_digest,
    projectionGeneration,
    input.projected_content_digest,
  ];
  if (!fields.every((digest) => typeof digest === "string" && SHA256_HEX.test(digest))) {
    return fail("authorized projection requires lowercase SHA-256 bindings");
  }
  return Object.freeze({
    projection_authorization_digest: input.projection_authorization_digest,
    reader_projection_digest: input.reader_projection_digest,
    projection_generation_digest: projectionGeneration,
    projected_content_digest: input.projected_content_digest,
    ...generations,
    read_coordinates: readCoordinates,
    coverage_canonical: canonicalPlainJson(coverage as unknown as PlainJson),
  });
};

interface AuthorizedCoherentRead {
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest;
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly coherent: ParsedCoherentLoad;
  readonly signature: Readonly<GenerationSignature>;
}

const loadAuthorizedCoherentRead = (ports: SnapshottedPorts): AuthorizedCoherentRead => {
  const resolved = Reflect.apply(ports.resolveAttempt, undefined, []);
  const attempt = parseAuthorizationAttempt(resolved);
  const coherentBox: { value?: ParsedCoherentLoad } = {};
  const loadCoherent = attempt.load_coherent;
  const projected = readAfterApplicationAuthorization(attempt.authorization_request, () => {
    const loaded = parseCoherentLoad(Reflect.apply(loadCoherent, undefined, []));
    coherentBox.value = loaded;
    return loaded.projection_load;
  });
  const coherent = coherentBox.value;
  if (!coherent || !isApplicationGrantProjectedTreeInput(projected)) {
    return fail("authorization boundary did not produce a branded coherent projection");
  }
  return Object.freeze({
    authorization_request: attempt.authorization_request,
    projected,
    coherent,
    signature: buildGenerationSignature(projected, coherent.generations, coherent.read_coordinates, coherent.coverage),
  });
};

const CANDIDATE_KEYS = Object.freeze([
  "owner_account_id",
  "projection_authorization_digest",
  "reader_projection_digest",
  "authorization_generation_digest",
  "projection_generation_digest",
  "projected_content_digest",
  "durable_generation_digest",
  "overlay_generation_digest",
  "declared_generation_digest",
  "accepted_generation_digest",
  "stm_generation_digest",
  "candidate_ref",
  "dedupe_ref",
  "dedupe_rank",
  "order_key",
  "stable_visible_key",
  "origin",
  "frontier",
  "supersedes_refs",
  "effective_policy",
  "synthesized_text",
  "citation_provenance_ids",
  "synthesis_provenance",
] as const satisfies readonly (keyof ApplicationSynthesizedCandidateRecord)[]);

const policyIsGeneric = (value: PlainJson): value is {
  readonly subject_class: "generic";
  readonly sensitivity: "generic";
  readonly capture_class: "generic";
} => exactRecord(value, ["subject_class", "sensitivity", "capture_class"])
  && typeof value.subject_class === "string"
  && typeof value.sensitivity === "string"
  && typeof value.capture_class === "string"
  && value.subject_class === "generic"
  && value.sensitivity === "generic"
  && value.capture_class === "generic";

const parseProvenance = (value: PlainJson): ApplicationSynthesisProvenance | null => {
  if (value === null) return null;
  if (!exactRecord(value, ["synthesis_version", "input_digest", "output_digest"])
    || typeof value.synthesis_version !== "string" || !SYNTHESIS_VERSION.test(value.synthesis_version)
    || typeof value.input_digest !== "string" || parseSha256Digest(value.input_digest) === null
    || typeof value.output_digest !== "string" || parseSha256Digest(value.output_digest) === null) {
    return fail("candidate synthesis provenance is invalid");
  }
  return Object.freeze({
    synthesis_version: value.synthesis_version,
    input_digest: value.input_digest,
    output_digest: value.output_digest,
  });
};

const candidateBindingMatches = (value: { readonly [key: string]: PlainJson }, signature: GenerationSignature): boolean =>
  value.projection_authorization_digest === signature.projection_authorization_digest
  && value.reader_projection_digest === signature.reader_projection_digest
  && value.authorization_generation_digest === signature.authorization_generation_digest
  && value.projection_generation_digest === signature.projection_generation_digest
  && value.projected_content_digest === signature.projected_content_digest
  && value.durable_generation_digest === signature.durable_generation_digest
  && value.overlay_generation_digest === signature.overlay_generation_digest
  && value.declared_generation_digest === signature.declared_generation_digest
  && value.accepted_generation_digest === signature.accepted_generation_digest
  && value.stm_generation_digest === signature.stm_generation_digest;

const parseCandidate = (
  value: PlainJson,
  source: CandidateSource,
  read: AuthorizedCoherentRead,
): ApplicationSynthesizedCandidateRecord | null => {
  if (!exactRecord(value, CANDIDATE_KEYS)) return fail("candidate has an invalid exact shape");
  if (typeof value.owner_account_id !== "string" || value.owner_account_id !== read.projected.owner_account_id) {
    return fail("candidate owner binding mismatch");
  }
  if (!candidateBindingMatches(value, read.signature)) return fail("candidate generation binding mismatch");
  const origin = value.origin;
  if (origin !== "durable" && origin !== "stm" && origin !== "accepted_unprocessed") {
    return fail("candidate origin is invalid");
  }
  if ((source === "durable" && origin !== "durable") || (source === "overlay" && origin === "durable")) {
    return fail("candidate source and origin disagree");
  }
  if (!exactRecord(value.effective_policy, ["subject_class", "sensitivity", "capture_class"])
    || typeof value.effective_policy.subject_class !== "string"
    || typeof value.effective_policy.sensitivity !== "string"
    || typeof value.effective_policy.capture_class !== "string") return fail("candidate policy is invalid");
  if (!INTERNAL_REF.test(typeof value.candidate_ref === "string" ? value.candidate_ref : "")
    || !INTERNAL_REF.test(typeof value.dedupe_ref === "string" ? value.dedupe_ref : "")
    || !INTERNAL_REF.test(typeof value.order_key === "string" ? value.order_key : "")
    || !STABLE_VISIBLE_KEY.test(typeof value.stable_visible_key === "string" ? value.stable_visible_key : "")
    || !INTERNAL_REF.test(typeof value.frontier === "string" ? value.frontier : "")
    || typeof value.dedupe_rank !== "number" || !Number.isSafeInteger(value.dedupe_rank)
    || !Array.isArray(value.supersedes_refs) || !value.supersedes_refs.every((ref) => typeof ref === "string" && INTERNAL_REF.test(ref))
    || !uniqueStrings(value.supersedes_refs as string[])
    || value.supersedes_refs.includes(value.candidate_ref)
    || typeof value.synthesized_text !== "string" || parseSynthesizedText(value.synthesized_text) === null
    || !Array.isArray(value.citation_provenance_ids)
    || !value.citation_provenance_ids.every((ref) => typeof ref === "string" && INTERNAL_REF.test(ref))
    || !uniqueStrings(value.citation_provenance_ids as string[])) return fail("candidate values are invalid");
  const provenance = parseProvenance(value.synthesis_provenance);

  // A well-formed, correctly bound non-generic record is outside this reader's
  // projection. It cannot participate in dedupe, supersession, paging or trace.
  if (!policyIsGeneric(value.effective_policy)) return null;

  const candidate: ApplicationSynthesizedCandidateRecord = {
    owner_account_id: value.owner_account_id,
    projection_authorization_digest: value.projection_authorization_digest as string,
    reader_projection_digest: value.reader_projection_digest as string,
    authorization_generation_digest: value.authorization_generation_digest as string,
    projection_generation_digest: value.projection_generation_digest as string,
    projected_content_digest: value.projected_content_digest as string,
    durable_generation_digest: value.durable_generation_digest as string,
    overlay_generation_digest: value.overlay_generation_digest as string,
    declared_generation_digest: value.declared_generation_digest as string,
    accepted_generation_digest: value.accepted_generation_digest as string,
    stm_generation_digest: value.stm_generation_digest as string,
    candidate_ref: value.candidate_ref as string,
    dedupe_ref: value.dedupe_ref as string,
    dedupe_rank: value.dedupe_rank,
    order_key: value.order_key as string,
    stable_visible_key: value.stable_visible_key as string,
    origin,
    frontier: value.frontier as string,
    supersedes_refs: Object.freeze([...(value.supersedes_refs as string[])].sort(compareStrings)),
    effective_policy: Object.freeze({ subject_class: "generic", sensitivity: "generic", capture_class: "generic" }),
    synthesized_text: value.synthesized_text,
    citation_provenance_ids: Object.freeze([...(value.citation_provenance_ids as string[])].sort(compareStrings)),
    synthesis_provenance: provenance,
  };
  return Object.freeze(candidate);
};

const parseCandidateArray = (
  input: unknown,
  source: CandidateSource,
  read: AuthorizedCoherentRead,
): readonly ApplicationSynthesizedCandidateRecord[] => {
  const value = source === "overlay" ? input as PlainJson : detachPlainJsonStrict(input);
  if (!Array.isArray(value)) return fail("candidate port must return an array");
  const output: ApplicationSynthesizedCandidateRecord[] = [];
  for (const item of value) {
    const parsed = parseCandidate(item, source, read);
    if (parsed) output.push(parsed);
  }
  return Object.freeze(output);
};

const toKernelCandidate = (candidate: ApplicationSynthesizedCandidateRecord): AuthorizedRecallCandidate => Object.freeze({
  candidate_ref: candidate.candidate_ref,
  dedupe_ref: candidate.dedupe_ref,
  dedupe_rank: candidate.dedupe_rank,
  order_key: candidate.order_key,
  origin: candidate.origin,
  frontier: candidate.frontier,
  supersedes_refs: candidate.supersedes_refs,
});

const assertOverlayFrontiers = (
  candidates: readonly ApplicationSynthesizedCandidateRecord[],
  completeness: RecallCompletenessResult,
): void => {
  for (const candidate of candidates) {
    const searched = candidate.origin === "stm"
      ? completeness.frontiers.newest_stm_frontier_searched
      : completeness.frontiers.newest_accepted_frontier_searched;
    if (searched === null || candidate.frontier !== searched) return fail("overlay candidate lies outside its searched frontier");
  }
};

const mergeCandidates = (
  durable: readonly ApplicationSynthesizedCandidateRecord[],
  overlay: readonly ApplicationSynthesizedCandidateRecord[],
): readonly ApplicationSynthesizedCandidateRecord[] => {
  const all = [...durable, ...overlay];
  const merged = mergeAuthorizedRecallCandidates(all.map(toKernelCandidate));
  const byRef = new Map(all.map((candidate) => [candidate.candidate_ref, candidate]));
  if (byRef.size !== all.length) return fail("candidate references must be unique");
  const winners = merged.map((candidate) => {
    const winner = byRef.get(candidate.candidate_ref);
    if (!winner) return fail("recall kernel returned an unknown candidate");
    return winner;
  });
  const stableKeys = winners.map((candidate) => candidate.stable_visible_key);
  if (!uniqueStrings(stableKeys)) return fail("visible winners require unique stable keys");
  return Object.freeze(winners);
};

interface PageSlice {
  readonly eligible: readonly ApplicationSynthesizedCandidateRecord[];
  readonly selected: readonly ApplicationSynthesizedCandidateRecord[];
  readonly hasMore: boolean;
}

const pageCandidates = (
  winners: readonly ApplicationSynthesizedCandidateRecord[],
  afterVisibleKey: string | null,
  limit: number,
): PageSlice => {
  let start = 0;
  if (afterVisibleKey !== null) {
    const index = winners.findIndex((candidate) => candidate.stable_visible_key === afterVisibleKey);
    if (index < 0) return fail("received an invalid after-visible key");
    start = index + 1;
  }
  const selected = Object.freeze(winners.slice(start, start + limit));
  const hasMore = selected.length > 0 && start + selected.length < winners.length;
  return Object.freeze({ eligible: winners, selected, hasMore });
};

const collectForbiddenRefs = (
  authorization: ApplicationMemoryReadAuthorizationRequest,
  projected: ApplicationGrantProjectedTreeInputSnapshot,
  candidates: readonly ApplicationSynthesizedCandidateRecord[],
): ReadonlySet<string> => {
  const refs = new Set<string>();
  const add = (value: unknown): void => { if (typeof value === "string" && value.length > 0) refs.add(value); };
  add(authorization.owner_account_id);
  add(authorization.credential.owner_account_id);
  add(authorization.credential.app_id);
  add(authorization.credential.key_id);
  add(authorization.persisted_grant?.owner_account_id);
  add(authorization.persisted_grant?.app_id);
  add(authorization.persisted_grant?.key_id);
  for (const candidate of candidates) {
    add(candidate.owner_account_id);
    add(candidate.projection_authorization_digest);
    add(candidate.reader_projection_digest);
    add(candidate.authorization_generation_digest);
    add(candidate.projection_generation_digest);
    add(candidate.projected_content_digest);
    add(candidate.durable_generation_digest);
    add(candidate.overlay_generation_digest);
    add(candidate.declared_generation_digest);
    add(candidate.accepted_generation_digest);
    add(candidate.stm_generation_digest);
    add(candidate.candidate_ref);
    add(candidate.dedupe_ref);
    add(candidate.order_key);
    add(candidate.stable_visible_key);
    add(candidate.frontier);
    for (const ref of candidate.supersedes_refs) add(ref);
    for (const ref of candidate.citation_provenance_ids) add(ref);
  }
  const visit = (value: unknown, field = ""): void => {
    if (value === null || typeof value !== "object") return;
    if (Array.isArray(value)) {
      for (const item of value) field.endsWith("_ids") || field.endsWith("_refs") ? add(item) : visit(item, field);
      return;
    }
    for (const [key, nested] of Object.entries(value)) {
      if (key === "owner_account_id" || key.endsWith("_id") || key.endsWith("_ref")) add(nested);
      else if ((key.endsWith("_ids") || key.endsWith("_refs")) && Array.isArray(nested)) for (const item of nested) add(item);
      visit(nested, key);
    }
  };
  visit(projected);
  return refs;
};

const leaksForbiddenRef = (value: string, forbidden: ReadonlySet<string>): boolean => {
  for (const raw of forbidden) if (value === raw || (raw.length >= 3 && value.includes(raw))) return true;
  return false;
};

const opaqueItemRef = (value: unknown, forbidden: ReadonlySet<string>): string => {
  if (typeof value !== "string" || parseSynthesizedItemId(value) === null || leaksForbiddenRef(value, forbidden)) {
    return fail("item codec returned a raw or invalid reference");
  }
  return value;
};

const opaqueCitationRef = (value: unknown, forbidden: ReadonlySet<string>): string => {
  if (typeof value !== "string" || parseCitationRef(value) === null || leaksForbiddenRef(value, forbidden)) {
    return fail("citation codec returned a raw or invalid reference");
  }
  return value;
};

const opaqueTraceRef = (value: unknown, forbidden: ReadonlySet<string>): `tr1_${string}` => {
  if (typeof value !== "string" || !TRACE_REF.test(value) || leaksForbiddenRef(value, forbidden)) {
    return fail("trace codec returned a raw or invalid reference");
  }
  return value as `tr1_${string}`;
};

const mapCompleteness = (result: RecallCompletenessResult): PlainJson => ({
  version: result.version,
  status: result.status,
  // Preserve every kernel reason; the ratified contract applies the same
  // degraded > incomplete > partial precedence as the recall kernel.
  reasons: [...result.reasons],
  frontiers: {
    declaredFrontier: result.frontiers.declared_frontier,
    newestSearchedAcceptedFrontier: result.frontiers.newest_accepted_frontier_searched,
    missingAcceptedFrontierReason: result.frontiers.missing_accepted_frontier_reason === "no_eligible_accepted"
      ? "no_accepted_work"
      : result.frontiers.missing_accepted_frontier_reason,
    newestSearchedStmFrontier: result.frontiers.newest_stm_frontier_searched,
    missingStmFrontierReason: result.frontiers.missing_stm_frontier_reason,
  },
});

const limitedWindow = (status: RecallCompletenessResult["status"]): boolean => status !== "complete";

const buildWindow = (hasMore: boolean, cursor: string | null, status: RecallCompletenessResult["status"]): PlainJson => {
  if (hasMore) return {
    status: limitedWindow(status) ? "incomplete" : "more",
    complete: false,
    hasMore: true,
    nextCursor: cursor,
  };
  return {
    status: limitedWindow(status) ? "incomplete" : "complete",
    complete: !limitedWindow(status),
    hasMore: false,
    nextCursor: null,
  };
};

const ownNullJson = (value: PlainJson): PlainJson => {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) {
    const output: PlainJson[] = [];
    for (const item of value) output.push(ownNullJson(item));
    Object.setPrototypeOf(output, null);
    return Object.freeze(output);
  }
  const record = value as { readonly [key: string]: PlainJson };
  const output = Object.create(null) as Record<string, PlainJson>;
  for (const key of Object.keys(record).sort(compareStrings)) defineDataProperty(output, key, ownNullJson(record[key]!));
  return Object.freeze(output);
};

const canonicalOwnedJson = (value: PlainJson): string => {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean" || typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) {
    const members: string[] = [];
    for (let index = 0; index < value.length; index += 1) members.push(canonicalOwnedJson(value[index]!));
    return `[${members.join(",")}]`;
  }
  const record = value as { readonly [key: string]: PlainJson };
  const members: string[] = [];
  for (const key of Object.keys(record)) members.push(`${JSON.stringify(key)}:${canonicalOwnedJson(record[key]!)}`);
  return `{${members.join(",")}}`;
};

interface PreparedApplicationPage {
  readonly page: PlainJson;
  readonly trace: ContentSafeRecallTrace;
  readonly signature: Readonly<GenerationSignature>;
  readonly attestation: Readonly<ApplicationReadAttestation>;
}

const buildSnapshotAttestation = (
  read: AuthorizedCoherentRead,
  coverage: RecallCompletenessInput,
): Readonly<ApplicationReadSnapshotAttestation> => Object.freeze({
  ...read.coherent.read_coordinates,
  synthesized_projection_generation_digest: read.signature.projection_generation_digest,
  projected_content_digest: read.signature.projected_content_digest,
  durable_generation_digest: read.signature.durable_generation_digest,
  overlay_generation_digest: read.signature.overlay_generation_digest,
  declared_generation_digest: read.signature.declared_generation_digest,
  accepted_generation_digest: read.signature.accepted_generation_digest,
  stm_generation_digest: read.signature.stm_generation_digest,
  coverage,
});

const buildReadAttestation = (
  snapshot: ApplicationReadSnapshotAttestation,
  lastVisibleKey: string | null,
): Readonly<ApplicationReadAttestation> => Object.freeze({
  ...snapshot,
  last_visible_key: lastVisibleKey,
});

const buildPreparedApplicationPage = (
  request: ApplicationSynthesizedPageRequest,
  ports: SnapshottedPorts,
): PreparedApplicationPage => {
  const read = loadAuthorizedCoherentRead(ports);
  const completeness = computeRecallCompleteness(read.coherent.coverage);
  if (parseRecallFrontier(completeness.frontiers.declared_frontier) === null
    || (completeness.frontiers.newest_accepted_frontier_searched !== null
      && parseRecallFrontier(completeness.frontiers.newest_accepted_frontier_searched) === null)
    || (completeness.frontiers.newest_stm_frontier_searched !== null
      && parseRecallFrontier(completeness.frontiers.newest_stm_frontier_searched) === null)) {
    return fail("completeness contains an invalid public frontier");
  }

  const snapshotAttestation = buildSnapshotAttestation(read, read.coherent.coverage);
  let afterVisibleKey: string | null = null;
  if (request.cursor !== null) {
    // Codec errors intentionally propagate with their own public invalid-cursor
    // type. A nonthrowing malformed codec result fails closed here.
    const verified = Reflect.apply(ports.verifyCursor, undefined, [request.cursor, snapshotAttestation]);
    if (typeof verified !== "string" || !STABLE_VISIBLE_KEY.test(verified)) {
      return fail("cursor verifier returned an invalid stable visible key");
    }
    afterVisibleKey = verified;
  }

  const loadDurableCandidates = ports.loadDurableCandidates;
  const durableRaw = Reflect.apply(loadDurableCandidates, undefined, [read.projected]);
  const durable = parseCandidateArray(durableRaw, "durable", read);
  const overlay = parseCandidateArray(read.coherent.overlay.candidates, "overlay", read);
  assertOverlayFrontiers(overlay, completeness);
  const winners = mergeCandidates(durable, overlay);
  const page = pageCandidates(winners, afterVisibleKey, request.limit);
  const forbidden = collectForbiddenRefs(read.authorization_request, read.projected, winners);
  const lastVisibleKey = page.selected.at(-1)?.stable_visible_key ?? null;
  const attestation = buildReadAttestation(snapshotAttestation, lastVisibleKey);

  const items: PlainJson[] = [];
  for (const candidate of page.selected) {
    const itemId = opaqueItemRef(Reflect.apply(ports.encodeItemRef, undefined, [candidate.candidate_ref]), forbidden);
    const citations = candidate.citation_provenance_ids.map((provenanceId) =>
      opaqueCitationRef(Reflect.apply(ports.encodeCitationRef, undefined, [provenanceId]), forbidden));
    if (!uniqueStrings(citations)) return fail("citation codec returned duplicate references");
    const item: Record<string, PlainJson> = {
      id: itemId,
      text: candidate.synthesized_text,
    };
    if (citations.length > 0) item.citations = citations;
    if (candidate.synthesis_provenance !== null) item.provenance = {
      synthesisVersion: candidate.synthesis_provenance.synthesis_version,
      inputDigest: candidate.synthesis_provenance.input_digest,
      outputDigest: candidate.synthesis_provenance.output_digest,
    };
    items.push(item);
  }

  let nextCursor: string | null = null;
  if (page.hasMore) {
    if (lastVisibleKey === null) return fail("cannot continue an empty page");
    const issued = Reflect.apply(ports.issueCursor, undefined, [lastVisibleKey, snapshotAttestation]);
    if (typeof issued !== "string" || parseKeysetCursor(issued) === null) return fail("cursor issuer returned an invalid cursor");
    nextCursor = issued;
  }

  const qualifiedAbsence = qualifyRecallAbsence(items.length, page.hasMore, completeness);
  const pageData: PlainJson = {
    contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
    items,
    window: buildWindow(page.hasMore, nextCursor, completeness.status),
    completeness: mapCompleteness(completeness),
    absence: qualifiedAbsence === null ? null : { kind: qualifiedAbsence.kind },
  };

  const traceByCandidate = new Map<string, `tr1_${string}`>();
  for (const candidate of page.eligible) {
    traceByCandidate.set(candidate.candidate_ref, opaqueTraceRef(
      Reflect.apply(ports.encodeTraceRef, undefined, [`candidate:${candidate.candidate_ref}`]),
      forbidden,
    ));
  }
  if (new Set(traceByCandidate.values()).size !== traceByCandidate.size) return fail("trace codec returned duplicate candidate references");
  const eligibleTraceRefs = page.eligible.map((candidate) => traceByCandidate.get(candidate.candidate_ref)!);
  const selectedTraceRefs = page.selected.map((candidate) => traceByCandidate.get(candidate.candidate_ref)!);
  const rootTraceSeed = `attempt:${read.signature.projection_authorization_digest}:${read.signature.projected_content_digest}:${afterVisibleKey ?? "start"}:${request.limit}`;
  const rootTraceRef = opaqueTraceRef(Reflect.apply(ports.encodeTraceRef, undefined, [rootTraceSeed]), forbidden);
  const freshness = read.coherent.coverage.projection_freshness;
  const outcome = selectedTraceRefs.length > 0 ? "grounded"
    : freshness !== "fresh" ? "degraded"
      : eligibleTraceRefs.length === 0 ? "no_eligible_candidates"
        : "no_selection";
  const trace = buildContentSafeRecallTrace({
    version: "recall-trace-v1",
    traceRef: rootTraceRef,
    strategyVersion: "application-read-v1",
    projectionFreshness: freshness,
    outcome,
    latencyMs: 0,
    tokenCounts: { input: 0, output: 0 },
    stages: {
      eligible: eligibleTraceRefs,
      selected: selectedTraceRefs,
      hydrated: selectedTraceRefs,
      policyEligible: selectedTraceRefs,
      cited: selectedTraceRefs,
      grounded: selectedTraceRefs,
    },
  });

  return Object.freeze({
    page: ownNullJson(pageData),
    trace,
    signature: read.signature,
    attestation,
  });
};

const signaturesEqual = (left: GenerationSignature, right: GenerationSignature): boolean =>
  left.projection_authorization_digest === right.projection_authorization_digest
  && left.reader_projection_digest === right.reader_projection_digest
  && left.authorization_generation_digest === right.authorization_generation_digest
  && left.projection_generation_digest === right.projection_generation_digest
  && left.projected_content_digest === right.projected_content_digest
  && left.durable_generation_digest === right.durable_generation_digest
  && left.overlay_generation_digest === right.overlay_generation_digest
  && left.declared_generation_digest === right.declared_generation_digest
  && left.accepted_generation_digest === right.accepted_generation_digest
  && left.stm_generation_digest === right.stm_generation_digest
  && left.coverage_canonical === right.coverage_canonical
  && READ_COORDINATE_DIGEST_KEYS.every((key) => left.read_coordinates[key] === right.read_coordinates[key]);

/**
 * Production-neutral application read core. It accepts only injected,
 * pre-synthesized candidate ports and returns canonical ratified JSON bytes.
 */
export const readApplicationSynthesizedPageWithAttestation = async (
  request: ApplicationSynthesizedPageRequest,
  suppliedPorts: ApplicationReadPorts,
): Promise<Readonly<ApplicationSynthesizedPageResult>> => {
  const pageRequest = parsePageRequest(request);
  const ports = snapshotPorts(suppliedPorts);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const prepared = buildPreparedApplicationPage(pageRequest, ports);

    // The second load crosses the identical authorization boundary. A final
    // denial propagates before bytes or trace are emitted.
    const revalidated = loadAuthorizedCoherentRead(ports);
    if (!signaturesEqual(prepared.signature, revalidated.signature)) {
      if (attempt === 0) continue;
      throw new ApplicationReadInvalidatedError();
    }

    const canonical = canonicalOwnedJson(prepared.page);
    const parsedPage = parseSynthesizedPageJson(canonical);
    if (parsedPage === null) {
      throw new ApplicationReadContractMismatchError();
    }
    await emitRecallTraceSafely(prepared.trace, ports.traceSink);
    return Object.freeze({ canonical_json: canonical, attestation: prepared.attestation });
  }
  throw new ApplicationReadInvalidatedError();
};

/** Wire-facing convenience: no attestation or internal coordinate enters JSON. */
export const readApplicationSynthesizedPage = async (
  request: ApplicationSynthesizedPageRequest,
  suppliedPorts: ApplicationReadPorts,
): Promise<string> => (await readApplicationSynthesizedPageWithAttestation(request, suppliedPorts)).canonical_json;
