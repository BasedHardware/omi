// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
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
import { sha256CanonicalContent } from "./content-digest";
import type { TreeInputSnapshot } from "./index";
import {
  buildOwnerBoundSynthesizedProjection,
  type OwnerBoundSynthesizedProjectionEnvelope,
  type SynthesizedCitation,
} from "./projection-boundary";
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
import { isProducedRenderNode, type RenderNode } from "./render";

const SHA256_HEX = /^[a-f0-9]{64}$/;
const INTERNAL_REF = /^[\x21-\x7e]{1,512}$/;
const ITEM_REF = /^mem1_[a-f0-9]{64}$/;
const CITATION_REF = /^cit1_[a-f0-9]{64}$/;
const STABLE_VISIBLE_KEY = /^vk1_[a-f0-9]{64}$/;
const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const SYNTHESIS_VERSION = /^[\x21-\x7e]{1,128}$/;
const MAX_PAGE_LIMIT = 100;
const MAX_CURSOR_CODE_UNITS = 4_096;

type PlainJson = null | boolean | number | string | readonly PlainJson[] | { readonly [key: string]: PlainJson };

export interface ApplicationRecallGenerationDigests {
  readonly authorization_generation_digest: string;
  /** Adapter-owned record of the exact validated produced-render set. */
  readonly synthesized_projection_generation_digest: string;
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

/** One adapter-owned coherent read; this file does not define a production store. */
export interface ApplicationRecallCoherentLoad {
  readonly projection_load: ApplicationProjectionLoad;
  /**
   * Accepted/STM state is completeness-only until those sources have the same
   * unforgeable produced-render boundary as durable material.
   */
  readonly coverage: RecallCompletenessInput;
  readonly generations: ApplicationRecallGenerationDigests;
  readonly read_coordinates: ApplicationReadCoherentCoordinates;
}

export interface LegacyApplicationReadAuthorizationAttempt {
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest;
  readonly load_coherent: () => ApplicationRecallCoherentLoad;
}

/**
 * A coherent projection whose authority was established by an external,
 * transaction-revalidated application boundary (for example the sealed
 * Firebase/PostgreSQL runtime).  The projection remains module-branded; a
 * structural clone cannot use this path.
 *
 * This is deliberately not an authorization DTO.  The authority boundary has
 * already run and the read core receives only its branded projection plus the
 * content-free generation coordinates it must compare before releasing bytes.
 */
export interface PreauthorizedApplicationReadAttempt {
  readonly authorized_projection: ApplicationGrantProjectedTreeInputSnapshot;
  readonly coherent: Omit<ApplicationRecallCoherentLoad, "projection_load">;
}

export type ApplicationReadAuthorizationAttempt =
  | LegacyApplicationReadAuthorizationAttempt
  | PreauthorizedApplicationReadAttempt;

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
  /**
   * Receives exactly the branded authorized projection, and no request
   * authority. Every returned value must be a module-branded RenderNode
   * produced by the existing render boundary; clones and structural lookalikes
   * are rejected before projection.
   */
  readonly loadDurableRenders: (
    input: ApplicationGrantProjectedTreeInputSnapshot,
  ) => unknown;
  /** Keyed digest of the canonical [version, order key, candidate ref] tuple. */
  readonly encodeVisibleKey: (canonicalSortTuple: string) => unknown;
  /** Reader-scoped keyed codecs. Raw internal coordinates are never accepted as output. */
  readonly encodeItemRef: (candidateRef: string) => unknown;
  readonly encodeCitationRef: (canonicalEvidenceClosure: string) => unknown;
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
    // THE PLAIN-DATA PROTOTYPE RULE (core-wide, see core/retrieve/plain-json.ts):
    // a plain-data record may carry `Object.prototype` OR a null prototype;
    // an array must carry `Array.prototype`.
    //
    // This module previously accepted only `Object.prototype` while
    // `plain-json.ts` -- and therefore `authorization-boundary.ts` -- accepted
    // null. Drivers legitimately emit null-prototype records
    // (`drivers/sqlite/application-recall-read.ts` builds them with
    // `Object.create(null)` on purpose), so the authorization layer admitted a
    // record this layer then refused. The failure surfaced here, at the read,
    // and read like a read fault rather than the contract mismatch it was.
    //
    // Accepting null is the safe direction, not the lax one: a null-prototype
    // object has strictly fewer inherited members, `__proto__` becomes an
    // ordinary own key that the exact-shape validators reject, and the copy
    // below writes through `defineDataProperty` (Object.defineProperty), which
    // defines an own data property and never triggers a `__proto__` setter.
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
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
  readonly loadDurableRenders: ApplicationReadPorts["loadDurableRenders"];
  readonly encodeVisibleKey: ApplicationReadPorts["encodeVisibleKey"];
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
    "loadDurableRenders",
    "encodeVisibleKey",
    "encodeItemRef",
    "encodeCitationRef",
    "encodeTraceRef",
    "verifyCursor",
    "issueCursor",
    "traceSink",
  ]);
  return Object.freeze({
    resolveAttempt: callbackValue(descriptors.resolveAttempt) as ApplicationReadPorts["resolveAttempt"],
    loadDurableRenders: callbackValue(descriptors.loadDurableRenders) as ApplicationReadPorts["loadDurableRenders"],
    encodeVisibleKey: callbackValue(descriptors.encodeVisibleKey) as ApplicationReadPorts["encodeVisibleKey"],
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
  "synthesized_projection_generation_digest",
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
  if (!exactRecord(value, ["projection_load", "coverage", "generations", "read_coordinates"])) {
    return fail("coherent load has an invalid exact shape");
  }
  if (!isRecord(value.projection_load) || !isRecord(value.coverage)) return fail("coherent load has an invalid shape");
  const generations = parseGenerations(value.generations);
  const readCoordinates = parseReadCoordinates(value.read_coordinates);
  if (readCoordinates.authorization_state_digest !== generations.authorization_generation_digest) {
    return fail("authorization state and generation coordinates disagree");
  }
  return Object.freeze({
    projection_load: value.projection_load as unknown as ApplicationProjectionLoad,
    coverage: value.coverage as unknown as RecallCompletenessInput,
    generations,
    read_coordinates: readCoordinates,
  });
};

interface ParsedLegacyAuthorizationAttempt {
  readonly kind: "legacy";
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest;
  readonly load_coherent: () => ApplicationRecallCoherentLoad;
}

interface ParsedPreauthorizedApplicationReadAttempt {
  readonly kind: "preauthorized";
  readonly authorized_projection: ApplicationGrantProjectedTreeInputSnapshot;
  readonly coherent: ParsedCoherentLoad;
}

type ParsedAuthorizationAttempt =
  | ParsedLegacyAuthorizationAttempt
  | ParsedPreauthorizedApplicationReadAttempt;

const parseAuthorizationAttempt = (input: unknown): ParsedAuthorizationAttempt => {
  if (input !== null && typeof input === "object" && !Array.isArray(input) && !isProxy(input)
    && Object.getPrototypeOf(input) === Object.prototype
    && Object.hasOwn(input, "authorized_projection")) {
    const descriptors = exactDescriptors(input, ["authorized_projection", "coherent"]);
    const projected = ownDescriptorValue(descriptors.authorized_projection);
    if (projected === null || typeof projected !== "object" || Array.isArray(projected)
      || isProxy(projected)
      || !isApplicationGrantProjectedTreeInput(projected as TreeInputSnapshot)) {
      return fail("preauthorized attempt requires a branded authorized projection");
    }
    const coherentValue = detachPlainJsonStrict(ownDescriptorValue(descriptors.coherent));
    if (!exactRecord(coherentValue, ["coverage", "generations", "read_coordinates"])) {
      return fail("preauthorized coherent load has an invalid exact shape");
    }
    const parsed = parseCoherentLoad({
      projection_load: { snapshot: {}, options: {} },
      coverage: coherentValue.coverage,
      generations: coherentValue.generations,
      read_coordinates: coherentValue.read_coordinates,
    });
    return Object.freeze({
      kind: "preauthorized" as const,
      authorized_projection: projected as ApplicationGrantProjectedTreeInputSnapshot,
      coherent: parsed,
    });
  }
  const descriptors = exactDescriptors(input, ["authorization_request", "load_coherent"]);
  const authorizationRequest = detachPlainJsonStrict(ownDescriptorValue(descriptors.authorization_request));
  if (!isRecord(authorizationRequest)) return fail("authorization request must be a plain JSON record");
  return Object.freeze({
    kind: "legacy" as const,
    authorization_request: authorizationRequest as unknown as ApplicationMemoryReadAuthorizationRequest,
    load_coherent: callbackValue(descriptors.load_coherent) as () => ApplicationRecallCoherentLoad,
  });
};

interface CoherentGenerationSignature extends ApplicationRecallGenerationDigests {
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projection_generation_digest: string;
  readonly projected_content_digest: string;
  readonly read_coordinates: Readonly<ApplicationReadCoherentCoordinates>;
  readonly coverage_canonical: string;
}

type GenerationSignature = CoherentGenerationSignature;

const buildGenerationSignature = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  generations: ApplicationRecallGenerationDigests,
  readCoordinates: Readonly<ApplicationReadCoherentCoordinates>,
  coverage: RecallCompletenessInput,
): Readonly<CoherentGenerationSignature> => {
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
  readonly authorization_request: ApplicationMemoryReadAuthorizationRequest | null;
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly coherent: ParsedCoherentLoad;
  readonly signature: Readonly<CoherentGenerationSignature>;
}

const loadAuthorizedCoherentRead = (ports: SnapshottedPorts): AuthorizedCoherentRead => {
  const resolved = Reflect.apply(ports.resolveAttempt, undefined, []);
  const attempt = parseAuthorizationAttempt(resolved);
  if (attempt.kind === "preauthorized") {
    const projected = attempt.authorized_projection;
    const coherent = attempt.coherent;
    return Object.freeze({
      authorization_request: null,
      projected,
      coherent,
      signature: buildGenerationSignature(
        projected,
        coherent.generations,
        coherent.read_coordinates,
        coherent.coverage,
      ),
    });
  }
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

interface AuthorizedRenderedCandidate {
  readonly envelope: OwnerBoundSynthesizedProjectionEnvelope;
  readonly candidate_ref: string;
  readonly dedupe_ref: string;
  readonly dedupe_rank: number;
  readonly order_key: string;
  readonly origin: "durable";
  readonly frontier: string;
  readonly supersedes_refs: readonly string[];
  readonly synthesized_text: string;
  readonly citations: readonly SynthesizedCitation[];
  readonly synthesis_provenance: {
    readonly synthesis_version: string;
    readonly input_digest: string;
    readonly output_digest: string;
  };
}

interface AuthorizedProducedRender {
  readonly render: RenderNode;
  readonly envelope: OwnerBoundSynthesizedProjectionEnvelope;
  readonly candidate_ref: string;
}

interface AuthorizedProducedRenderManifest {
  readonly renders: readonly AuthorizedProducedRender[];
  readonly synthesized_projection_generation_digest: string;
}

/** Preserve RenderNode identity while rejecting hostile arrays and lookalikes. */
const snapshotProducedRenders = (input: unknown): readonly RenderNode[] => {
  if (!Array.isArray(input) || isProxy(input) || Object.getPrototypeOf(input) !== Array.prototype) {
    return fail("durable render port must return a plain array");
  }
  const descriptors = Object.getOwnPropertyDescriptors(input);
  const descriptorRecord = descriptors as unknown as Record<PropertyKey, PropertyDescriptor>;
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) return fail("durable render array rejects symbols");
  const indexKeys = (keys as string[]).filter((key) => key !== "length");
  const lengthDescriptor = descriptorRecord.length;
  if (!lengthDescriptor || !Object.hasOwn(lengthDescriptor, "value") || lengthDescriptor.value !== input.length) {
    return fail("durable render array has an invalid length descriptor");
  }
  if (indexKeys.length !== input.length || indexKeys.some((key, index) => key !== String(index))) {
    return fail("durable render array rejects sparse or decorated values");
  }
  const renders: RenderNode[] = [];
  for (const key of indexKeys) {
    const descriptor = descriptorRecord[key];
    if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, "value")) {
      return fail("durable render array rejects accessors");
    }
    const render = descriptor.value;
    if (isProxy(render) || !isProducedRenderNode(render)) {
      return fail("durable render port requires produced RenderNode identities");
    }
    renders.push(render);
  }
  if (new Set(renders).size !== renders.length) return fail("durable render port rejects aliases");
  return Object.freeze(renders);
};

const synthesizedProjectionGenerationDigest = (
  renders: readonly AuthorizedProducedRender[],
): string => {
  const identities = renders.map(({ render, envelope }) => ({
    node_id: envelope.node_id,
    render_generation: envelope.render_generation,
    render_hash: envelope.render_hash,
    model_version: render.model_version,
  })).sort((left, right) => compareStrings(canonicalPlainJson(left), canonicalPlainJson(right)));
  return sha256CanonicalContent({ version: "application-produced-render-set-v1", identities });
};

const buildAuthorizedProducedRenderManifest = (
  projected: ApplicationGrantProjectedTreeInputSnapshot,
  input: unknown,
): Readonly<AuthorizedProducedRenderManifest> => {
  const renders = snapshotProducedRenders(input);
  const authorized = renders.map((render): AuthorizedProducedRender => {
    const envelope = buildOwnerBoundSynthesizedProjection(projected, render);
    if (parseSynthesizedText(envelope.synthesized_summary) === null
      || envelope.citations.length === 0
      || !INTERNAL_REF.test(envelope.node_id)
      || !SYNTHESIS_VERSION.test(render.model_version)
      || parseSha256Digest(envelope.render_hash) === null
      || parseSha256Digest(envelope.rendered_from_digest) === null) {
      return fail("owner-bound render lacks grounded synthesis provenance");
    }
    const candidateRef = `render:${envelope.render_hash}`;
    return Object.freeze({ render, envelope, candidate_ref: candidateRef });
  });
  if (!uniqueStrings(authorized.map(({ envelope }) => envelope.node_id))) {
    return fail("produced renders require unique node authority");
  }
  if (!uniqueStrings(authorized.map(({ candidate_ref: candidateRef }) => candidateRef))) {
    return fail("produced renders require unique candidate identities");
  }
  return Object.freeze({
    renders: Object.freeze(authorized),
    synthesized_projection_generation_digest: synthesizedProjectionGenerationDigest(authorized),
  });
};

/**
 * Computes the adapter's exact produced-render-set generation receipt for a
 * branded authorized projection. This validates the same owner/evidence
 * boundary as application read, but returns no envelope and grants no read
 * authority. Application read always recomputes and cross-checks the receipt.
 */
export const computeApplicationSynthesizedProjectionGenerationDigest = (
  projected: ApplicationGrantProjectedTreeInputSnapshot,
  renders: readonly RenderNode[],
): string => {
  if (!isApplicationGrantProjectedTreeInput(projected)) {
    return fail("generation digest requires a branded authorized projection");
  }
  return buildAuthorizedProducedRenderManifest(projected, renders)
    .synthesized_projection_generation_digest;
};

interface AuthorizedRenderedSet {
  readonly candidates: readonly AuthorizedRenderedCandidate[];
  readonly synthesized_projection_generation_digest: string;
}

const buildAuthorizedRenderedCandidates = (
  input: unknown,
  read: AuthorizedCoherentRead,
): Readonly<AuthorizedRenderedSet> => {
  const manifest = buildAuthorizedProducedRenderManifest(read.projected, input);
  const candidates = manifest.renders.map(({ render, envelope, candidate_ref: candidateRef }): AuthorizedRenderedCandidate => {
    const nodeRef = `node:${sha256CanonicalContent(envelope.node_id)}`;
    return Object.freeze({
      envelope,
      candidate_ref: candidateRef,
      dedupe_ref: nodeRef,
      dedupe_rank: 0,
      // Hermetic QA/default-fixture ordering only: preserve the existing
      // produced render node-id order. This makes no production ranking-policy
      // claim.
      order_key: envelope.node_id,
      origin: "durable",
      // Hermetic QA/default-fixture frontier only. A production retrieval
      // policy must supply its separately ratified durable frontier semantics.
      frontier: read.signature.durable_generation_digest,
      supersedes_refs: Object.freeze([]),
      synthesized_text: envelope.synthesized_summary,
      citations: envelope.citations,
      synthesis_provenance: Object.freeze({
        synthesis_version: render.model_version,
        input_digest: envelope.rendered_from_digest,
        // The projection boundary recomputes render_hash over the exact
        // summary text and rejects any mismatch before this point.
        output_digest: envelope.render_hash,
      }),
    });
  });
  return Object.freeze({
    candidates: Object.freeze(candidates),
    synthesized_projection_generation_digest: manifest.synthesized_projection_generation_digest,
  });
};

const toKernelCandidate = (candidate: AuthorizedRenderedCandidate): AuthorizedRecallCandidate => Object.freeze({
  candidate_ref: candidate.candidate_ref,
  dedupe_ref: candidate.dedupe_ref,
  dedupe_rank: candidate.dedupe_rank,
  order_key: candidate.order_key,
  origin: candidate.origin,
  frontier: candidate.frontier,
  supersedes_refs: candidate.supersedes_refs,
});

const mergeCandidates = (
  durable: readonly AuthorizedRenderedCandidate[],
): readonly AuthorizedRenderedCandidate[] => {
  const merged = mergeAuthorizedRecallCandidates(durable.map(toKernelCandidate));
  const byRef = new Map(durable.map((candidate) => [candidate.candidate_ref, candidate]));
  if (byRef.size !== durable.length) return fail("produced renders require unique identities");
  const winners = merged.map((candidate) => {
    const winner = byRef.get(candidate.candidate_ref);
    if (!winner) return fail("recall kernel returned an unknown candidate");
    return winner;
  });
  return Object.freeze(winners);
};

const collectForbiddenRefs = (
  authorization: ApplicationMemoryReadAuthorizationRequest | null,
  projected: ApplicationGrantProjectedTreeInputSnapshot,
  candidates: readonly AuthorizedRenderedCandidate[],
): ReadonlySet<string> => {
  const refs = new Set<string>();
  const add = (value: unknown): void => { if (typeof value === "string" && value.length > 0) refs.add(value); };
  if (authorization !== null) {
    add(authorization.owner_account_id);
    add(authorization.credential.owner_account_id);
    add(authorization.credential.app_id);
    add(authorization.credential.key_id);
    add(authorization.persisted_grant?.owner_account_id);
    add(authorization.persisted_grant?.app_id);
    add(authorization.persisted_grant?.key_id);
  }
  for (const candidate of candidates) {
    add(candidate.candidate_ref);
    add(candidate.dedupe_ref);
    add(candidate.order_key);
    add(candidate.frontier);
    for (const value of Object.values(candidate.envelope)) {
      if (typeof value === "string") add(value);
    }
    for (const citation of candidate.citations) {
      add(citation.evidence_id);
      add(citation.event_revision_id);
      add(citation.capture_session_id);
      for (const revision of citation.claim_revision_ids) add(revision);
    }
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

const opaqueVisibleKey = (value: unknown, forbidden: ReadonlySet<string>): `vk1_${string}` => {
  if (typeof value !== "string" || !STABLE_VISIBLE_KEY.test(value) || leaksForbiddenRef(value, forbidden)) {
    return fail("visible-key codec returned a raw or invalid keyed digest");
  }
  return value as `vk1_${string}`;
};

const opaqueItemRef = (value: unknown, forbidden: ReadonlySet<string>): string => {
  if (typeof value !== "string" || !ITEM_REF.test(value)
    || parseSynthesizedItemId(value) === null || leaksForbiddenRef(value, forbidden)) {
    return fail("item codec returned a raw or invalid keyed digest");
  }
  return value;
};

const opaqueCitationRef = (value: unknown, forbidden: ReadonlySet<string>): string => {
  if (typeof value !== "string" || !CITATION_REF.test(value)
    || parseCitationRef(value) === null || leaksForbiddenRef(value, forbidden)) {
    return fail("citation codec returned a raw or invalid keyed digest");
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

interface CoherentApplicationRead {
  readonly read: AuthorizedCoherentRead;
  readonly completeness: RecallCompletenessResult;
  readonly signature: Readonly<GenerationSignature>;
  readonly snapshot_attestation: Readonly<ApplicationReadSnapshotAttestation>;
}

interface LoadedApplicationRead extends CoherentApplicationRead {
  readonly winners: readonly AuthorizedRenderedCandidate[];
}

interface PreparedApplicationRead extends LoadedApplicationRead {
  readonly after_visible_key: string | null;
}

interface FinalizedApplicationPage {
  readonly page: PlainJson;
  readonly trace: ContentSafeRecallTrace;
  readonly attestation: Readonly<ApplicationReadAttestation>;
}

interface VisibleRenderedCandidate {
  readonly candidate: AuthorizedRenderedCandidate;
  readonly visible_key: `vk1_${string}`;
}

interface PageSlice {
  readonly eligible: readonly VisibleRenderedCandidate[];
  readonly selected: readonly VisibleRenderedCandidate[];
  readonly hasMore: boolean;
}

const buildSnapshotAttestation = (
  read: AuthorizedCoherentRead,
  coverage: RecallCompletenessInput,
): Readonly<ApplicationReadSnapshotAttestation> => Object.freeze({
  ...read.coherent.read_coordinates,
  synthesized_projection_generation_digest: read.signature.synthesized_projection_generation_digest,
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

const loadCoherentApplicationRead = (
  ports: SnapshottedPorts,
): CoherentApplicationRead => {
  const read = loadAuthorizedCoherentRead(ports);
  const completeness = computeRecallCompleteness(read.coherent.coverage);
  if (parseRecallFrontier(completeness.frontiers.declared_frontier) === null
    || (completeness.frontiers.newest_accepted_frontier_searched !== null
      && parseRecallFrontier(completeness.frontiers.newest_accepted_frontier_searched) === null)
    || (completeness.frontiers.newest_stm_frontier_searched !== null
      && parseRecallFrontier(completeness.frontiers.newest_stm_frontier_searched) === null)) {
    return fail("completeness contains an invalid public frontier");
  }
  // Accepted/STM positive synthesis has no produced-render authority boundary
  // yet. Until one is ratified, those sources may report honest no-eligible or
  // limitation states, but cannot claim a synthesized searched frontier.
  if (completeness.frontiers.newest_accepted_frontier_searched !== null
    || completeness.frontiers.newest_stm_frontier_searched !== null) {
    return fail("accepted and STM synthesized search requires a produced-render boundary");
  }

  return Object.freeze({
    read,
    completeness,
    signature: read.signature,
    snapshot_attestation: buildSnapshotAttestation(read, read.coherent.coverage),
  });
};

const validateDurableApplicationRead = (
  coherent: CoherentApplicationRead,
  ports: SnapshottedPorts,
): LoadedApplicationRead => {
  const durableRaw = Reflect.apply(ports.loadDurableRenders, undefined, [coherent.read.projected]);
  const durable = buildAuthorizedRenderedCandidates(durableRaw, coherent.read);
  if (durable.synthesized_projection_generation_digest
    !== coherent.signature.synthesized_projection_generation_digest) {
    return fail("coherent synthesized projection generation disagrees with exact produced render set");
  }
  const winners = mergeCandidates(durable.candidates);
  return Object.freeze({ ...coherent, winners });
};

const loadInternalApplicationRead = (
  ports: SnapshottedPorts,
): LoadedApplicationRead => validateDurableApplicationRead(loadCoherentApplicationRead(ports), ports);

const prepareApplicationRead = (
  request: ApplicationSynthesizedPageRequest,
  ports: SnapshottedPorts,
): PreparedApplicationRead => {
  const coherent = loadCoherentApplicationRead(ports);
  let afterVisibleKey: string | null = null;
  if (request.cursor !== null) {
    // Verification binds the adapter's coherent produced-render-set receipt
    // before any render or candidate work. The receipt is recomputed and
    // cross-checked immediately below; codec errors retain their own public
    // invalid-cursor type.
    const verified = Reflect.apply(ports.verifyCursor, undefined, [request.cursor, coherent.snapshot_attestation]);
    if (typeof verified !== "string" || !STABLE_VISIBLE_KEY.test(verified)) {
      return fail("cursor verifier returned an invalid stable visible key");
    }
    afterVisibleKey = verified;
  }
  const loaded = validateDurableApplicationRead(coherent, ports);
  return Object.freeze({ ...loaded, after_visible_key: afterVisibleKey });
};

const attachVisibleKeys = (
  winners: readonly AuthorizedRenderedCandidate[],
  forbidden: ReadonlySet<string>,
  ports: SnapshottedPorts,
): readonly VisibleRenderedCandidate[] => {
  const output = winners.map((candidate): VisibleRenderedCandidate => {
    // These are exactly the two coordinates used by the recall kernel's final
    // post-dedupe ordering. Only their keyed digest becomes pagination state.
    const sortTuple = canonicalPlainJson(["application-visible-order-v1", candidate.order_key, candidate.candidate_ref]);
    const encoded = Reflect.apply(ports.encodeVisibleKey, undefined, [sortTuple]);
    return Object.freeze({ candidate, visible_key: opaqueVisibleKey(encoded, forbidden) });
  });
  const keys = output.map((candidate) => candidate.visible_key);
  if (!uniqueStrings(keys)) return fail("visible-key codec returned duplicate keyed digests");
  return Object.freeze(output);
};

const pageCandidates = (
  winners: readonly VisibleRenderedCandidate[],
  afterVisibleKey: string | null,
  limit: number,
): PageSlice => {
  let start = 0;
  if (afterVisibleKey !== null) {
    const index = winners.findIndex((candidate) => candidate.visible_key === afterVisibleKey);
    if (index < 0) return fail("received an invalid after-visible key");
    start = index + 1;
  }
  const selected = Object.freeze(winners.slice(start, start + limit));
  const hasMore = selected.length > 0 && start + selected.length < winners.length;
  return Object.freeze({ eligible: winners, selected, hasMore });
};

const canonicalCitationClosure = (citation: SynthesizedCitation): string => canonicalPlainJson([
  "application-citation-closure-v1",
  citation.evidence_id,
  citation.event_revision_id,
  citation.capture_session_id,
  [...citation.claim_revision_ids],
]);

/** Called only after the final authorization/coherence signature matches. */
const finalizeApplicationPage = (
  prepared: PreparedApplicationRead,
  request: ApplicationSynthesizedPageRequest,
  ports: SnapshottedPorts,
): FinalizedApplicationPage => {
  const { read, completeness, snapshot_attestation: snapshotAttestation, after_visible_key: afterVisibleKey } = prepared;
  const forbidden = collectForbiddenRefs(read.authorization_request, read.projected, prepared.winners);
  const visibleWinners = attachVisibleKeys(prepared.winners, forbidden, ports);
  const page = pageCandidates(visibleWinners, afterVisibleKey, request.limit);
  const lastVisibleKey = page.selected.at(-1)?.visible_key ?? null;
  const attestation = buildReadAttestation(snapshotAttestation, lastVisibleKey);

  const items: PlainJson[] = [];
  for (const visible of page.selected) {
    const candidate = visible.candidate;
    const itemId = opaqueItemRef(Reflect.apply(ports.encodeItemRef, undefined, [candidate.candidate_ref]), forbidden);
    const citations = candidate.citations.map((citation) => opaqueCitationRef(
      Reflect.apply(ports.encodeCitationRef, undefined, [canonicalCitationClosure(citation)]),
      forbidden,
    ));
    if (citations.length === 0) return fail("positive synthesized items require grounded citations");
    if (!uniqueStrings(citations)) return fail("citation codec returned duplicate references");
    const item: Record<string, PlainJson> = {
      id: itemId,
      text: candidate.synthesized_text,
      citations,
      provenance: {
        synthesisVersion: candidate.synthesis_provenance.synthesis_version,
        inputDigest: candidate.synthesis_provenance.input_digest,
        outputDigest: candidate.synthesis_provenance.output_digest,
      },
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
  for (const visible of page.eligible) {
    const candidate = visible.candidate;
    traceByCandidate.set(candidate.candidate_ref, opaqueTraceRef(
      Reflect.apply(ports.encodeTraceRef, undefined, [`candidate:${candidate.candidate_ref}`]),
      forbidden,
    ));
  }
  if (new Set(traceByCandidate.values()).size !== traceByCandidate.size) return fail("trace codec returned duplicate candidate references");
  const eligibleTraceRefs = page.eligible.map(({ candidate }) => traceByCandidate.get(candidate.candidate_ref)!);
  const selectedTraceRefs = page.selected.map(({ candidate }) => traceByCandidate.get(candidate.candidate_ref)!);
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
    attestation,
  });
};

const signaturesEqual = (left: GenerationSignature, right: GenerationSignature): boolean =>
  left.synthesized_projection_generation_digest === right.synthesized_projection_generation_digest
  && left.projection_authorization_digest === right.projection_authorization_digest
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
  && READ_COORDINATE_DIGEST_KEYS.every((key) => left.read_coordinates[key] === right.read_coordinates[key])
  && left.read_coordinates.read_timestamp_epoch_seconds === right.read_coordinates.read_timestamp_epoch_seconds;

/**
 * Production-neutral application read core. It accepts only module-branded
 * produced renders, revalidates their owner/evidence closure, and returns
 * canonical ratified JSON bytes without running synthesis or a model.
 */
export const readApplicationSynthesizedPageWithAttestation = async (
  request: ApplicationSynthesizedPageRequest,
  suppliedPorts: ApplicationReadPorts,
): Promise<Readonly<ApplicationSynthesizedPageResult>> => {
  const pageRequest = parsePageRequest(request);
  const ports = snapshotPorts(suppliedPorts);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const prepared = prepareApplicationRead(pageRequest, ports);

    // The second load crosses the identical authorization boundary. A final
    // denial propagates before bytes or trace are emitted.
    const revalidated = loadInternalApplicationRead(ports);
    if (!signaturesEqual(prepared.signature, revalidated.signature)) {
      if (attempt === 0) continue;
      throw new ApplicationReadInvalidatedError();
    }

    // No visible-key/item/citation/trace codec, cursor issuer, or trace sink is
    // invoked until this exact final authorization/coherence fence succeeds.
    const finalized = finalizeApplicationPage(prepared, pageRequest, ports);
    const canonical = canonicalOwnedJson(finalized.page);
    const parsedPage = parseSynthesizedPageJson(canonical);
    if (parsedPage === null) {
      throw new ApplicationReadContractMismatchError();
    }
    await emitRecallTraceSafely(finalized.trace, ports.traceSink);
    return Object.freeze({ canonical_json: canonical, attestation: finalized.attestation });
  }
  throw new ApplicationReadInvalidatedError();
};

/** Wire-facing convenience: no attestation or internal coordinate enters JSON. */
export const readApplicationSynthesizedPage = async (
  request: ApplicationSynthesizedPageRequest,
  suppliedPorts: ApplicationReadPorts,
): Promise<string> => (await readApplicationSynthesizedPageWithAttestation(request, suppliedPorts)).canonical_json;
