// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMX-001)
import { isProxy } from "node:util/types";

import {
  isApplicationGrantProjectedTreeInput,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "./authorization-boundary";
import { sha256CanonicalContent } from "./content-digest";
import {
  inspectAuthorizedProductProjectionSet,
  type AuthorizedProductProjectionSet,
  type ProductProjectionRevision,
} from "./product-projection";

export const SOURCE_IMPACT_CONTRACT_VERSION = "source-impact-v1" as const;

export type SourceImpactErrorCode =
  | "invalid_request"
  | "invalid_codecs"
  | "unauthorized_input"
  | "coordinate_mismatch"
  | "invalid_cursor"
  | "invalid_opaque_ref"
  | "impact_limit_exceeded";

export class SourceImpactError extends Error {
  constructor(readonly code: SourceImpactErrorCode) {
    super(code);
    this.name = "SourceImpactError";
  }
}

export type SourceImpactTarget =
  | Readonly<{ kind: "capture_session"; capture_session_id: string }>
  | Readonly<{ kind: "evidence"; evidence_id: string }>;

export interface SourceImpactPageRequest {
  readonly target: SourceImpactTarget;
  readonly limit: number;
  readonly cursor: string | null;
}

export type SourceImpactItemKind =
  | "event"
  | "evidence"
  | "provisional_claim"
  | "canonical_claim"
  | "product_projection";

export type SourceImpactItemState = "current" | "historical";
export type SourceImpactRecomputability = "recomputable" | "source_absent";

export interface SourceImpactItem {
  readonly kind: SourceImpactItemKind;
  readonly ref: string;
  readonly state: SourceImpactItemState;
  readonly recomputability: SourceImpactRecomputability;
}

export interface SourceImpactPage {
  readonly version: typeof SOURCE_IMPACT_CONTRACT_VERSION;
  readonly query_digest: string;
  readonly snapshot_digest: string;
  readonly items: readonly SourceImpactItem[];
  readonly has_more: boolean;
  readonly next_cursor: string | null;
}

export interface SourceImpactCodecs {
  readonly encode_ref: (input: Readonly<{
    kind: SourceImpactItemKind;
    internal_ref: string;
  }>) => unknown;
  readonly verify_cursor: (input: Readonly<{
    cursor: string;
    binding_digest: string;
    after_key: string;
  }>) => unknown;
  readonly issue_cursor: (input: Readonly<{
    binding_digest: string;
    after_key: string;
  }>) => unknown;
}

const MAX_PAGE_LIMIT = 100;
const MAX_TARGET_CODE_UNITS = 512;
const MAX_CURSOR_CODE_UNITS = 4_096;
const MAX_IMPACT_ROWS = 10_000;
const OPAQUE_REF = /^si1_[a-f0-9]{64}$/;
const OPAQUE_CURSOR = /^sic1_[a-f0-9]{64}$/;
const AFTER_KEY = /^[0-4]:[a-f0-9]{64}$/;
const DIGEST = /^[a-f0-9]{64}$/;

const kindRank: Readonly<Record<SourceImpactItemKind, number>> = Object.freeze({
  event: 0,
  evidence: 1,
  provisional_claim: 2,
  canonical_claim: 3,
  product_projection: 4,
});

const fail = (code: SourceImpactErrorCode): never => {
  throw new SourceImpactError(code);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: SourceImpactErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
  }
  return value as Record<string, unknown>;
};

const boundedCoordinate = (value: unknown): string => {
  if (typeof value !== "string" || value.length < 1
    || value.length > MAX_TARGET_CODE_UNITS || value.includes("\0")) fail("invalid_request");
  return value as string;
};

const parseTarget = (value: unknown): SourceImpactTarget => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_request");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  const kind = descriptor && descriptor.enumerable && "value" in descriptor
    ? descriptor.value : fail("invalid_request");
  if (kind === "capture_session") {
    const input = exactRecord(value, ["kind", "capture_session_id"], "invalid_request");
    return Object.freeze({
      kind: "capture_session" as const,
      capture_session_id: boundedCoordinate(input["capture_session_id"]),
    });
  }
  if (kind === "evidence") {
    const input = exactRecord(value, ["kind", "evidence_id"], "invalid_request");
    return Object.freeze({
      kind: "evidence" as const,
      evidence_id: boundedCoordinate(input["evidence_id"]),
    });
  }
  return fail("invalid_request");
};

const parseRequest = (value: unknown): SourceImpactPageRequest => {
  const input = exactRecord(value, ["target", "limit", "cursor"], "invalid_request");
  if (!Number.isSafeInteger(input["limit"]) || (input["limit"] as number) < 1
    || (input["limit"] as number) > MAX_PAGE_LIMIT) fail("invalid_request");
  if (input["cursor"] !== null
    && (typeof input["cursor"] !== "string" || input["cursor"].length < 1
      || input["cursor"].length > MAX_CURSOR_CODE_UNITS
      || !OPAQUE_CURSOR.test(input["cursor"]))) fail("invalid_cursor");
  return Object.freeze({
    target: parseTarget(input["target"]),
    limit: input["limit"] as number,
    cursor: input["cursor"] as string | null,
  });
};

/** Validates and detaches a page request without touching authorization or storage. */
export const assertSourceImpactPageRequest = (value: unknown): SourceImpactPageRequest =>
  parseRequest(value);

type CodecFunction = (...args: never[]) => unknown;

const codecFunction = (value: unknown): CodecFunction => {
  if (typeof value !== "function" || isProxy(value)) fail("invalid_codecs");
  return value as CodecFunction;
};

const parseCodecs = (value: unknown): SourceImpactCodecs => {
  const input = exactRecord(value, ["encode_ref", "verify_cursor", "issue_cursor"], "invalid_codecs");
  return Object.freeze({
    encode_ref: codecFunction(input["encode_ref"]) as SourceImpactCodecs["encode_ref"],
    verify_cursor: codecFunction(input["verify_cursor"]) as SourceImpactCodecs["verify_cursor"],
    issue_cursor: codecFunction(input["issue_cursor"]) as SourceImpactCodecs["issue_cursor"],
  });
};

interface InternalImpactItem {
  readonly kind: SourceImpactItemKind;
  readonly internal_ref: string;
  readonly state: SourceImpactItemState;
  readonly recomputability: SourceImpactRecomputability;
  readonly after_key: string;
}

const internalItem = (
  kind: SourceImpactItemKind,
  internalRef: string,
  state: SourceImpactItemState,
  recomputability: SourceImpactRecomputability = "recomputable",
): InternalImpactItem => Object.freeze({
  kind,
  internal_ref: internalRef,
  state,
  recomputability,
  after_key: `${kindRank[kind]}:${sha256CanonicalContent({
    version: SOURCE_IMPACT_CONTRACT_VERSION,
    kind,
    internal_ref: internalRef,
  })}`,
});

const targetDigest = (target: SourceImpactTarget): string => sha256CanonicalContent({
  version: SOURCE_IMPACT_CONTRACT_VERSION,
  target,
});

const compareText = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

interface AuthorizedSourceImpactInputs {
  readonly authorized: AuthorizedProductProjectionSet;
  readonly snapshot_digest: string;
  readonly input_digest: string;
}

const inspectAuthorizedInputs = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  authorizedProjectionValue: AuthorizedProductProjectionSet,
): AuthorizedSourceImpactInputs => {
  if (!isApplicationGrantProjectedTreeInput(input)) fail("unauthorized_input");
  let authorized: AuthorizedProductProjectionSet;
  try {
    authorized = inspectAuthorizedProductProjectionSet(authorizedProjectionValue);
  } catch {
    return fail("unauthorized_input");
  }
  if (authorized.owner_account_id !== input.owner_account_id
    || authorized.graph_frontier !== input.graph_generation
    || authorized.reader_projection_digest !== input.reader_projection_digest
    || authorized.projection_authorization_digest !== input.projection_authorization_digest) {
    fail("coordinate_mismatch");
  }
  const projectionDigest = sha256CanonicalContent(
    [...authorized.projections].sort((left, right) =>
      compareText(left.projection_revision_id, right.projection_revision_id)),
  );
  const snapshotDigest = sha256CanonicalContent({
    version: SOURCE_IMPACT_CONTRACT_VERSION,
    graph_frontier: input.graph_generation,
    projected_content_digest: input.projected_content_digest,
    product_projection_digest: projectionDigest,
    reader_projection_digest: input.reader_projection_digest,
    projection_authorization_digest: input.projection_authorization_digest,
  });
  const inputDigest = sha256CanonicalContent({
    version: SOURCE_IMPACT_CONTRACT_VERSION,
    snapshot_digest: snapshotDigest,
    reader_projection_digest: input.reader_projection_digest,
    projection_authorization_digest: input.projection_authorization_digest,
  });
  if (!DIGEST.test(snapshotDigest) || !DIGEST.test(inputDigest)) fail("coordinate_mismatch");
  return Object.freeze({
    authorized,
    snapshot_digest: snapshotDigest,
    input_digest: inputDigest,
  });
};

/**
 * Content-safe equality coordinate for a complete authorized source-impact
 * input. This grants no authority and accepts only the two runtime brands.
 */
export const computeAuthorizedSourceImpactInputDigest = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  authorizedProjectionValue: AuthorizedProductProjectionSet,
): string => inspectAuthorizedInputs(input, authorizedProjectionValue).input_digest;

const projectionIsCurrent = (
  projection: ProductProjectionRevision,
  projections: readonly ProductProjectionRevision[],
): boolean => !projections.some((candidate) => candidate.proposition_id === projection.proposition_id
  && (candidate.projection_sequence > projection.projection_sequence
    || (candidate.projection_sequence === projection.projection_sequence
      && compareText(candidate.projection_revision_id, projection.projection_revision_id) > 0)));

const impactedRows = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  projections: readonly ProductProjectionRevision[],
  target: SourceImpactTarget,
): readonly InternalImpactItem[] => {
  const spans = input.evidence_index.filter((span) => target.kind === "capture_session"
    ? span.capture_session_id === target.capture_session_id
    : span.evidence_id === target.evidence_id);
  const evidenceIds = new Set(spans.map((span) => span.evidence_id));
  const eventIds = new Set(spans.map((span) => span.event_revision_id));
  const claims = input.claims.filter((claim) => claim.evidence_refs.some((ref) => evidenceIds.has(ref)));
  const claimIds = new Set(claims.map((claim) => claim.claim_revision_id));
  const rows: InternalImpactItem[] = [
    ...[...eventIds].map((ref) => internalItem("event", ref, "current")),
    ...[...evidenceIds].map((ref) => internalItem("evidence", ref, "current")),
    ...claims.map((claim) => internalItem(
      claim.canonical_claim_id === null ? "provisional_claim" : "canonical_claim",
      claim.claim_revision_id,
      "current",
    )),
    ...projections.filter((projection) => projection.citations.some((citation) =>
      claimIds.has(citation.claim_revision_id)
      && citation.evidence_refs.some((ref) => evidenceIds.has(ref))))
      .map((projection) => internalItem(
        "product_projection",
        projection.projection_revision_id,
        projectionIsCurrent(projection, projections) ? "current" : "historical",
      )),
  ];
  if (rows.length > MAX_IMPACT_ROWS) fail("impact_limit_exceeded");
  const seen = new Set<string>();
  for (const row of rows) {
    if (seen.has(row.after_key)) fail("coordinate_mismatch");
    seen.add(row.after_key);
  }
  return Object.freeze(rows.sort((left, right) => compareText(left.after_key, right.after_key)));
};

const encodedRef = (
  codecs: SourceImpactCodecs,
  row: InternalImpactItem,
  seen: Set<string>,
): string => {
  let encoded: unknown;
  try {
    encoded = codecs.encode_ref(Object.freeze({
      kind: row.kind,
      internal_ref: row.internal_ref,
    }));
  } catch {
    return fail("invalid_opaque_ref");
  }
  if (typeof encoded !== "string" || !OPAQUE_REF.test(encoded)
    || encoded === row.internal_ref || seen.has(encoded)) fail("invalid_opaque_ref");
  const encodedString = encoded as string;
  seen.add(encodedString);
  return encodedString;
};

/**
 * Deterministic read-only dependency page over existing authorized projections.
 * It accepts no raw graph, store, logger, clock, model, or mutation capability.
 */
export const enumerateAuthorizedSourceImpact = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  authorizedProjectionValue: AuthorizedProductProjectionSet,
  requestValue: SourceImpactPageRequest,
  codecsValue: SourceImpactCodecs,
): SourceImpactPage => {
  const inspected = inspectAuthorizedInputs(input, authorizedProjectionValue);
  const authorized = inspected.authorized;
  const request = parseRequest(requestValue);
  const codecs = parseCodecs(codecsValue);
  const snapshotDigest = inspected.snapshot_digest;
  const queryDigest = sha256CanonicalContent({
    version: SOURCE_IMPACT_CONTRACT_VERSION,
    reader_projection_digest: input.reader_projection_digest,
    projection_authorization_digest: input.projection_authorization_digest,
    graph_frontier: input.graph_generation,
    target_digest: targetDigest(request.target),
    snapshot_digest: snapshotDigest,
  });
  if (!DIGEST.test(queryDigest)) fail("coordinate_mismatch");
  const rows = impactedRows(input, authorized.projections, request.target);

  let afterKey: string | null = null;
  if (request.cursor !== null) {
    const matches: string[] = [];
    for (const row of rows) {
      let verified: unknown;
      try {
        verified = codecs.verify_cursor(Object.freeze({
          cursor: request.cursor,
          binding_digest: queryDigest,
          after_key: row.after_key,
        }));
      } catch {
        return fail("invalid_cursor");
      }
      if (verified === true) matches.push(row.after_key);
      else if (verified !== false) fail("invalid_cursor");
    }
    if (matches.length !== 1) fail("invalid_cursor");
    afterKey = matches[0]!;
  }
  const start = afterKey === null ? 0 : rows.findIndex((row) => row.after_key === afterKey) + 1;
  const selected = rows.slice(start, start + request.limit);
  const hasMore = start + selected.length < rows.length;
  const seenRefs = new Set<string>();
  const items = selected.map((row): SourceImpactItem => Object.freeze({
    kind: row.kind,
    ref: encodedRef(codecs, row, seenRefs),
    state: row.state,
    recomputability: row.recomputability,
  }));
  let nextCursor: string | null = null;
  if (hasMore) {
    const last = selected.at(-1) ?? fail("invalid_cursor");
    let issued: unknown;
    try {
      issued = codecs.issue_cursor(Object.freeze({
        binding_digest: queryDigest,
        after_key: last.after_key,
      }));
    } catch {
      return fail("invalid_cursor");
    }
    if (typeof issued !== "string" || !OPAQUE_CURSOR.test(issued)
      || issued === last.after_key) fail("invalid_cursor");
    nextCursor = issued as string;
  }
  return Object.freeze({
    version: SOURCE_IMPACT_CONTRACT_VERSION,
    query_digest: queryDigest,
    snapshot_digest: snapshotDigest,
    items: Object.freeze(items),
    has_more: hasMore,
    next_cursor: nextCursor,
  });
};
