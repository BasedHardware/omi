import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  isApplicationGrantProjectedTreeInput,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "./authorization-boundary";

export const PRODUCT_PROJECTION_CONTRACT_VERSION = "product-projection-v1" as const;

export type ProductProjectionContractErrorCode =
  | "invalid_shape"
  | "invalid_identity"
  | "invalid_membership"
  | "invalid_projection"
  | "invalid_redirect"
  | "redirect_cycle"
  | "redirect_bound_exceeded"
  | "invalid_migration_mapping"
  | "invalid_group_projection";

export class ProductProjectionContractError extends Error {
  constructor(readonly code: ProductProjectionContractErrorCode) {
    super(code);
    this.name = "ProductProjectionContractError";
  }
}

export type ProductPropositionOrigin = "native" | "legacy_mapping";
export type ProductMembershipCause =
  | "birth"
  | "ledger_consolidation"
  | "correction"
  | "product_successor";

export interface ProductPropositionIdentity {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly proposition_id: string;
  readonly birth_claim_lineage_id: string;
  readonly origin: ProductPropositionOrigin;
  readonly created_at_event_time: number;
}

export interface ProductMembershipRevision {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly proposition_id: string;
  readonly membership_revision_id: string;
  readonly revision_sequence: number;
  readonly parent_membership_revision_id: string | null;
  readonly member_claim_lineage_ids: readonly string[];
  readonly cause: ProductMembershipCause;
  readonly graph_frontier: string;
  readonly input_digest: string;
  readonly result_digest: string;
  readonly created_at_event_time: number;
}

export interface ProductProjectionCitationSupport {
  readonly claim_lineage_id: string;
  readonly claim_revision_id: string;
  readonly evidence_refs: readonly string[];
}

export interface ProductProjectionRevision {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly proposition_id: string;
  readonly projection_revision_id: string;
  readonly projection_sequence: number;
  readonly membership_revision_id: string;
  readonly graph_frontier: string;
  readonly renderer_contract_digest: string;
  readonly rendered_content_digest: string;
  readonly citations: readonly ProductProjectionCitationSupport[];
  readonly created_at_event_time: number;
}

export interface ProductPropositionRedirect {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly redirect_id: string;
  readonly source_proposition_id: string;
  readonly successor_proposition_ids: readonly string[];
  readonly operation: "merge" | "split";
  readonly operation_ref: string;
  readonly created_at_event_time: number;
}

export interface ProductGroupProjection {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly group_projection_id: string;
  readonly proposition_ids: readonly string[];
  readonly input_frontier: string;
  readonly projection_contract_digest: string;
  readonly result_digest: string;
  readonly created_at_event_time: number;
}

export interface LegacyPropositionMapping {
  readonly version: typeof PRODUCT_PROJECTION_CONTRACT_VERSION;
  readonly owner_account_id: string;
  readonly legacy_source_id: string;
  readonly proposition_id: string;
}

export type LegacyPropositionMappingPlan =
  | Readonly<{ kind: "tombstoned" }>
  | Readonly<{ kind: "reuse_mapping"; mapping: LegacyPropositionMapping }>
  | Readonly<{ kind: "allocation_required" }>
  | Readonly<{ kind: "insert_if_absent"; mapping: LegacyPropositionMapping }>;

export interface AuthorizedProductProjectionSet {
  readonly owner_account_id: string;
  readonly graph_frontier: string;
  readonly reader_projection_digest: string;
  readonly projection_authorization_digest: string;
  readonly projections: readonly ProductProjectionRevision[];
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const GROUP_ID = /^grp1_[a-f0-9]{64}$/;
const ARRAY_INDEX = /^(0|[1-9]\d*)$/;
const MAX_MEMBERS = 10_000;
const MAX_CITATIONS = 10_000;
const MAX_EVIDENCE_PER_CITATION = 1_000;
const MAX_REDIRECT_FANOUT = 32;
const MAX_REDIRECT_DEPTH = 64;
const ORIGINS = new Set<ProductPropositionOrigin>(["native", "legacy_mapping"]);
const MEMBERSHIP_CAUSES = new Set<ProductMembershipCause>([
  "birth", "ledger_consolidation", "correction", "product_successor",
]);
const authorizedProductProjectionSets = new WeakSet<object>();

const fail = (code: ProductProjectionContractErrorCode): never => {
  throw new ProductProjectionContractError(code);
};

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: ProductProjectionContractErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object") fail(code);
  if (isProxy(value) || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const objectValue = value as object;
  const ownKeys = Reflect.ownKeys(objectValue);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(objectValue, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (
  value: unknown,
  maximum: number,
  code: ProductProjectionContractErrorCode,
): readonly unknown[] => {
  if (value === null || typeof value !== "object") fail(code);
  if (isProxy(value) || !Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const arrayValue = value as unknown[];
  const keys = Reflect.ownKeys(arrayValue);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const stringKeys = keys as string[];
  if (stringKeys.length !== arrayValue.length + 1
    || stringKeys.some((key) => key !== "length"
      && (!ARRAY_INDEX.test(key) || Number(key) >= arrayValue.length))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < arrayValue.length; index++) {
    const descriptor = Object.getOwnPropertyDescriptor(arrayValue, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push((descriptor as PropertyDescriptor & { value: unknown }).value);
  }
  return output;
};

const token = (value: unknown, code: ProductProjectionContractErrorCode): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const propositionId = (value: unknown, code: ProductProjectionContractErrorCode): string => {
  const parsed = token(value, code);
  if (GROUP_ID.test(parsed)) fail(code);
  return parsed;
};

const digest = (value: unknown, code: ProductProjectionContractErrorCode): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value as string;
};

const eventTime = (value: unknown, code: ProductProjectionContractErrorCode): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail(code);
  return value as number;
};

const positiveSequence = (value: unknown, code: ProductProjectionContractErrorCode): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) fail(code);
  return value as number;
};

const sortedUniqueTokens = (
  value: unknown,
  maximum: number,
  code: ProductProjectionContractErrorCode,
): readonly string[] => {
  const values = exactArray(value, maximum, code).map((entry) => token(entry, code));
  if (values.length === 0) fail(code);
  for (let index = 1; index < values.length; index++) {
    if (values[index - 1]!.localeCompare(values[index]!) >= 0) fail(code);
  }
  return Object.freeze(values);
};

const canonicalDigest = (domain: string, value: unknown): string => createHash("sha256")
  .update(domain, "ascii")
  .update("\0", "ascii")
  .update(JSON.stringify(value), "utf8")
  .digest("hex");

const membershipRevisionId = (value: Omit<ProductMembershipRevision, "membership_revision_id">): string =>
  `pmr1_${canonicalDigest("omi.product-membership.v1", value)}`;

const projectionRevisionId = (value: Omit<ProductProjectionRevision, "projection_revision_id">): string =>
  `pvr1_${canonicalDigest("omi.product-projection.v1", value)}`;

const redirectId = (value: Omit<ProductPropositionRedirect, "redirect_id">): string =>
  `prd1_${canonicalDigest("omi.product-redirect.v1", value)}`;

const groupProjectionId = (value: Omit<ProductGroupProjection, "group_projection_id">): string =>
  `grp1_${canonicalDigest("omi.product-group.v1", value)}`;

export const parseProductPropositionIdentity = (value: unknown): ProductPropositionIdentity => {
  const code = "invalid_identity" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "proposition_id", "birth_claim_lineage_id",
    "origin", "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION
    || typeof input["origin"] !== "string"
    || !ORIGINS.has(input["origin"] as ProductPropositionOrigin)) fail(code);
  const identity = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    proposition_id: propositionId(input["proposition_id"], code),
    birth_claim_lineage_id: token(input["birth_claim_lineage_id"], code),
    origin: input["origin"] as ProductPropositionOrigin,
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  if (identity.proposition_id === identity.birth_claim_lineage_id) fail(code);
  return Object.freeze(identity);
};

const membershipFields = (value: unknown): ProductMembershipRevision => {
  const code = "invalid_membership" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "proposition_id", "membership_revision_id",
    "revision_sequence", "parent_membership_revision_id", "member_claim_lineage_ids",
    "cause", "graph_frontier", "input_digest", "result_digest",
    "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION
    || typeof input["cause"] !== "string"
    || !MEMBERSHIP_CAUSES.has(input["cause"] as ProductMembershipCause)) fail(code);
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    proposition_id: propositionId(input["proposition_id"], code),
    revision_sequence: positiveSequence(input["revision_sequence"], code),
    parent_membership_revision_id: input["parent_membership_revision_id"] === null
      ? null : token(input["parent_membership_revision_id"], code),
    member_claim_lineage_ids: sortedUniqueTokens(input["member_claim_lineage_ids"], MAX_MEMBERS, code),
    cause: input["cause"] as ProductMembershipCause,
    graph_frontier: token(input["graph_frontier"], code),
    input_digest: digest(input["input_digest"], code),
    result_digest: digest(input["result_digest"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  if (withoutId.cause === "birth") {
    if (withoutId.revision_sequence !== 1
      || withoutId.parent_membership_revision_id !== null
      || withoutId.member_claim_lineage_ids.length !== 1) fail(code);
  } else if (withoutId.revision_sequence < 2
    || withoutId.parent_membership_revision_id === null) fail(code);
  const expectedId = membershipRevisionId(withoutId);
  if (input["membership_revision_id"] !== expectedId) fail(code);
  return Object.freeze({ ...withoutId, membership_revision_id: expectedId });
};

export const parseProductMembershipRevision = (value: unknown): ProductMembershipRevision =>
  membershipFields(value);

export interface BirthProductPropositionInput {
  readonly owner_account_id: string;
  readonly proposition_id: string;
  readonly birth_claim_lineage_id: string;
  readonly origin: ProductPropositionOrigin;
  readonly graph_frontier: string;
  readonly input_digest: string;
  readonly result_digest: string;
  readonly created_at_event_time: number;
}

export const birthProductProposition = (inputValue: BirthProductPropositionInput): Readonly<{
  identity: ProductPropositionIdentity;
  membership: ProductMembershipRevision;
}> => {
  const input = exactRecord(inputValue, [
    "owner_account_id", "proposition_id", "birth_claim_lineage_id", "origin",
    "graph_frontier", "input_digest", "result_digest", "created_at_event_time",
  ], "invalid_identity");
  const identity = parseProductPropositionIdentity({
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: input["owner_account_id"],
    proposition_id: input["proposition_id"],
    birth_claim_lineage_id: input["birth_claim_lineage_id"],
    origin: input["origin"],
    created_at_event_time: input["created_at_event_time"],
  });
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: identity.owner_account_id,
    proposition_id: identity.proposition_id,
    revision_sequence: 1,
    parent_membership_revision_id: null,
    member_claim_lineage_ids: Object.freeze([identity.birth_claim_lineage_id]),
    cause: "birth" as const,
    graph_frontier: token(input["graph_frontier"], "invalid_membership"),
    input_digest: digest(input["input_digest"], "invalid_membership"),
    result_digest: digest(input["result_digest"], "invalid_membership"),
    created_at_event_time: identity.created_at_event_time,
  };
  const membership = membershipFields({
    ...withoutId,
    membership_revision_id: membershipRevisionId(withoutId),
  });
  return Object.freeze({ identity, membership });
};

export interface AppendProductMembershipInput {
  readonly identity: ProductPropositionIdentity;
  readonly parent: ProductMembershipRevision;
  readonly member_claim_lineage_ids: readonly string[];
  readonly cause: Exclude<ProductMembershipCause, "birth">;
  readonly graph_frontier: string;
  readonly input_digest: string;
  readonly result_digest: string;
  readonly created_at_event_time: number;
}

export const appendProductMembership = (
  inputValue: AppendProductMembershipInput,
): ProductMembershipRevision => {
  const input = exactRecord(inputValue, [
    "identity", "parent", "member_claim_lineage_ids", "cause", "graph_frontier",
    "input_digest", "result_digest", "created_at_event_time",
  ], "invalid_membership");
  const identity = parseProductPropositionIdentity(input["identity"]);
  const parent = membershipFields(input["parent"]);
  if (parent.owner_account_id !== identity.owner_account_id
    || parent.proposition_id !== identity.proposition_id) fail("invalid_membership");
  if (input["cause"] === "birth" || typeof input["cause"] !== "string"
    || !MEMBERSHIP_CAUSES.has(input["cause"] as ProductMembershipCause)) fail("invalid_membership");
  const createdAt = eventTime(input["created_at_event_time"], "invalid_membership");
  if (createdAt < parent.created_at_event_time) fail("invalid_membership");
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: identity.owner_account_id,
    proposition_id: identity.proposition_id,
    revision_sequence: parent.revision_sequence + 1,
    parent_membership_revision_id: parent.membership_revision_id,
    member_claim_lineage_ids: sortedUniqueTokens(input["member_claim_lineage_ids"], MAX_MEMBERS, "invalid_membership"),
    cause: input["cause"] as Exclude<ProductMembershipCause, "birth">,
    graph_frontier: token(input["graph_frontier"], "invalid_membership"),
    input_digest: digest(input["input_digest"], "invalid_membership"),
    result_digest: digest(input["result_digest"], "invalid_membership"),
    created_at_event_time: createdAt,
  };
  return membershipFields({ ...withoutId, membership_revision_id: membershipRevisionId(withoutId) });
};

const citationFields = (value: unknown): ProductProjectionCitationSupport => {
  const code = "invalid_projection" as const;
  const input = exactRecord(value, [
    "claim_lineage_id", "claim_revision_id", "evidence_refs",
  ], code);
  return Object.freeze({
    claim_lineage_id: token(input["claim_lineage_id"], code),
    claim_revision_id: token(input["claim_revision_id"], code),
    evidence_refs: sortedUniqueTokens(input["evidence_refs"], MAX_EVIDENCE_PER_CITATION, code),
  });
};

const projectionFields = (value: unknown): ProductProjectionRevision => {
  const code = "invalid_projection" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "proposition_id", "projection_revision_id",
    "projection_sequence", "membership_revision_id", "graph_frontier",
    "renderer_contract_digest", "rendered_content_digest", "citations",
    "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION) fail(code);
  const citations = exactArray(input["citations"], MAX_CITATIONS, code).map(citationFields);
  if (citations.length === 0) fail(code);
  const citationKeys = citations.map((citation) =>
    `${citation.claim_lineage_id}\0${citation.claim_revision_id}`);
  for (let index = 1; index < citationKeys.length; index++) {
    if (citationKeys[index - 1]!.localeCompare(citationKeys[index]!) >= 0) fail(code);
  }
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    proposition_id: propositionId(input["proposition_id"], code),
    projection_sequence: positiveSequence(input["projection_sequence"], code),
    membership_revision_id: token(input["membership_revision_id"], code),
    graph_frontier: token(input["graph_frontier"], code),
    renderer_contract_digest: digest(input["renderer_contract_digest"], code),
    rendered_content_digest: digest(input["rendered_content_digest"], code),
    citations: Object.freeze(citations),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  const expectedId = projectionRevisionId(withoutId);
  if (input["projection_revision_id"] !== expectedId) fail(code);
  return Object.freeze({ ...withoutId, projection_revision_id: expectedId });
};

export const parseProductProjectionRevision = (value: unknown): ProductProjectionRevision =>
  projectionFields(value);

export interface BuildProductProjectionInput {
  readonly identity: ProductPropositionIdentity;
  readonly membership: ProductMembershipRevision;
  readonly projection_sequence: number;
  readonly graph_frontier: string;
  readonly renderer_contract_digest: string;
  readonly rendered_content_digest: string;
  readonly citations: readonly ProductProjectionCitationSupport[];
  readonly created_at_event_time: number;
}

export const buildProductProjectionRevision = (
  inputValue: BuildProductProjectionInput,
): ProductProjectionRevision => {
  const input = exactRecord(inputValue, [
    "identity", "membership", "projection_sequence", "graph_frontier",
    "renderer_contract_digest", "rendered_content_digest", "citations",
    "created_at_event_time",
  ], "invalid_projection");
  const identity = parseProductPropositionIdentity(input["identity"]);
  const membership = membershipFields(input["membership"]);
  if (identity.owner_account_id !== membership.owner_account_id
    || identity.proposition_id !== membership.proposition_id
    || input["graph_frontier"] !== membership.graph_frontier) fail("invalid_projection");
  const citations = exactArray(input["citations"], MAX_CITATIONS, "invalid_projection")
    .map(citationFields);
  const citedLineages = [...new Set(citations.map((citation) => citation.claim_lineage_id))].sort();
  if (citedLineages.length !== membership.member_claim_lineage_ids.length
    || citedLineages.some((lineage, index) => lineage !== membership.member_claim_lineage_ids[index])) {
    fail("invalid_projection");
  }
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: identity.owner_account_id,
    proposition_id: identity.proposition_id,
    projection_sequence: positiveSequence(input["projection_sequence"], "invalid_projection"),
    membership_revision_id: membership.membership_revision_id,
    graph_frontier: membership.graph_frontier,
    renderer_contract_digest: digest(input["renderer_contract_digest"], "invalid_projection"),
    rendered_content_digest: digest(input["rendered_content_digest"], "invalid_projection"),
    citations: Object.freeze(citations),
    created_at_event_time: eventTime(input["created_at_event_time"], "invalid_projection"),
  };
  if (withoutId.created_at_event_time < membership.created_at_event_time) fail("invalid_projection");
  return projectionFields({ ...withoutId, projection_revision_id: projectionRevisionId(withoutId) });
};

export const buildAuthorizedProductProjectionSet = (
  authorizedInput: ApplicationGrantProjectedTreeInputSnapshot,
  identityValues: readonly ProductPropositionIdentity[],
  membershipValues: readonly ProductMembershipRevision[],
  projectionValues: readonly ProductProjectionRevision[],
): AuthorizedProductProjectionSet => {
  if (!isApplicationGrantProjectedTreeInput(authorizedInput)) fail("invalid_projection");
  const claimByRevision = new Map(authorizedInput.claims.map((claim) => [claim.claim_revision_id, claim]));
  const identityById = new Map<string, ProductPropositionIdentity>();
  for (const value of exactArray(identityValues, MAX_MEMBERS, "invalid_projection")) {
    const identity = parseProductPropositionIdentity(value);
    if (identity.owner_account_id !== authorizedInput.owner_account_id
      || identityById.has(identity.proposition_id)) fail("invalid_projection");
    identityById.set(identity.proposition_id, identity);
  }
  const membershipById = new Map<string, ProductMembershipRevision>();
  for (const value of exactArray(membershipValues, MAX_MEMBERS, "invalid_projection")) {
    const membership = membershipFields(value);
    if (membership.owner_account_id !== authorizedInput.owner_account_id
      || !identityById.has(membership.proposition_id)
      || membershipById.has(membership.membership_revision_id)) fail("invalid_projection");
    membershipById.set(membership.membership_revision_id, membership);
  }
  const projections = exactArray(projectionValues, MAX_CITATIONS, "invalid_projection")
    .map(projectionFields);
  const seenRevisionIds = new Set<string>();
  const sequenceHeads = new Map<string, string>();
  for (const projection of projections) {
    if (projection.owner_account_id !== authorizedInput.owner_account_id
      || projection.graph_frontier !== authorizedInput.graph_generation) fail("invalid_projection");
    const identity = identityById.get(projection.proposition_id);
    const membership = membershipById.get(projection.membership_revision_id);
    if (!identity || !membership || membership.proposition_id !== projection.proposition_id
      || membership.graph_frontier !== projection.graph_frontier) fail("invalid_projection");
    const boundMembership = membership!;
    const sequenceKey = `${projection.proposition_id}\0${projection.projection_sequence}`;
    const sequenceHead = sequenceHeads.get(sequenceKey);
    if (seenRevisionIds.has(projection.projection_revision_id)
      || (sequenceHead !== undefined && sequenceHead !== projection.projection_revision_id)) {
      fail("invalid_projection");
    }
    seenRevisionIds.add(projection.projection_revision_id);
    sequenceHeads.set(sequenceKey, projection.projection_revision_id);
    const citedLineages = new Set<string>();
    for (const citation of projection.citations) {
      const claim = claimByRevision.get(citation.claim_revision_id);
      if (!claim || claim.claim_lineage_id !== citation.claim_lineage_id) fail("invalid_projection");
      citedLineages.add(citation.claim_lineage_id);
      const expectedEvidence = [...claim!.evidence_refs].sort();
      if (citation.evidence_refs.length !== expectedEvidence.length
        || citation.evidence_refs.some((ref, index) => ref !== expectedEvidence[index])) {
        fail("invalid_projection");
      }
    }
    if (citedLineages.size !== boundMembership.member_claim_lineage_ids.length
      || boundMembership.member_claim_lineage_ids.some((lineage) => !citedLineages.has(lineage))) {
      fail("invalid_projection");
    }
  }
  const result: AuthorizedProductProjectionSet = Object.freeze({
    owner_account_id: String(authorizedInput.owner_account_id),
    graph_frontier: String(authorizedInput.graph_generation),
    reader_projection_digest: String(authorizedInput.reader_projection_digest),
    projection_authorization_digest: String(authorizedInput.projection_authorization_digest),
    projections: Object.freeze(projections),
  });
  authorizedProductProjectionSets.add(result);
  return result;
};

export const selectLatestAuthorizedProductProjection = (
  identityValue: ProductPropositionIdentity,
  authorizedSet: AuthorizedProductProjectionSet,
): ProductProjectionRevision | null => {
  const identity = parseProductPropositionIdentity(identityValue);
  if (!authorizedProductProjectionSets.has(authorizedSet)
    || authorizedSet.owner_account_id !== identity.owner_account_id) fail("invalid_projection");
  const visible: ProductProjectionRevision[] = [];
  for (const value of authorizedSet.projections) {
    const projection = projectionFields(value);
    if (projection.owner_account_id !== identity.owner_account_id) fail("invalid_projection");
    if (projection.proposition_id !== identity.proposition_id) continue;
    visible.push(projection);
  }
  visible.sort((left, right) => right.projection_sequence - left.projection_sequence
    || right.projection_revision_id.localeCompare(left.projection_revision_id));
  if (visible.length > 1 && visible[0]!.projection_sequence === visible[1]!.projection_sequence
    && visible[0]!.projection_revision_id !== visible[1]!.projection_revision_id) fail("invalid_projection");
  return visible[0] ?? null;
};

const redirectFields = (value: unknown): ProductPropositionRedirect => {
  const code = "invalid_redirect" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "redirect_id", "source_proposition_id",
    "successor_proposition_ids", "operation", "operation_ref", "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION
    || (input["operation"] !== "merge" && input["operation"] !== "split")) fail(code);
  const successors = sortedUniqueTokens(input["successor_proposition_ids"], MAX_REDIRECT_FANOUT, code)
    .map((id) => propositionId(id, code));
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    source_proposition_id: propositionId(input["source_proposition_id"], code),
    successor_proposition_ids: Object.freeze(successors),
    operation: input["operation"] as "merge" | "split",
    operation_ref: token(input["operation_ref"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  if (successors.includes(withoutId.source_proposition_id)) fail(code);
  if (withoutId.operation === "split" && successors.length < 2) fail(code);
  const expectedId = redirectId(withoutId);
  if (input["redirect_id"] !== expectedId) fail(code);
  return Object.freeze({ ...withoutId, redirect_id: expectedId });
};

/** Strict persistence/replay parser for an already-derived redirect. */
export const parseProductPropositionRedirect = (value: unknown): ProductPropositionRedirect =>
  redirectFields(value);

export interface BuildProductRedirectInput {
  readonly owner_account_id: string;
  readonly source_proposition_id: string;
  readonly successor_proposition_ids: readonly string[];
  readonly operation: "merge" | "split";
  readonly operation_ref: string;
  readonly created_at_event_time: number;
}

export const buildProductPropositionRedirect = (
  inputValue: BuildProductRedirectInput,
): ProductPropositionRedirect => {
  const input = exactRecord(inputValue, [
    "owner_account_id", "source_proposition_id", "successor_proposition_ids",
    "operation", "operation_ref", "created_at_event_time",
  ], "invalid_redirect");
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_redirect"),
    source_proposition_id: propositionId(input["source_proposition_id"], "invalid_redirect"),
    successor_proposition_ids: sortedUniqueTokens(input["successor_proposition_ids"], MAX_REDIRECT_FANOUT, "invalid_redirect")
      .map((id) => propositionId(id, "invalid_redirect")),
    operation: input["operation"],
    operation_ref: token(input["operation_ref"], "invalid_redirect"),
    created_at_event_time: eventTime(input["created_at_event_time"], "invalid_redirect"),
  };
  if (withoutId.operation !== "merge" && withoutId.operation !== "split") fail("invalid_redirect");
  return redirectFields({ ...withoutId, redirect_id: redirectId(withoutId as Omit<ProductPropositionRedirect, "redirect_id">) });
};

export const resolveTerminalPropositionIds = (inputValue: Readonly<{
  owner_account_id: string;
  start_proposition_ids: readonly string[];
  propositions: readonly ProductPropositionIdentity[];
  redirects: readonly ProductPropositionRedirect[];
}>): readonly string[] => {
  const input = exactRecord(inputValue, [
    "owner_account_id", "start_proposition_ids", "propositions", "redirects",
  ], "invalid_redirect");
  const owner = token(input["owner_account_id"], "invalid_redirect");
  const starts = sortedUniqueTokens(input["start_proposition_ids"], MAX_MEMBERS, "invalid_redirect")
    .map((id) => propositionId(id, "invalid_redirect"));
  const propositions = exactArray(input["propositions"], MAX_MEMBERS, "invalid_redirect")
    .map(parseProductPropositionIdentity);
  const known = new Set<string>();
  for (const proposition of propositions) {
    if (proposition.owner_account_id !== owner || known.has(proposition.proposition_id)) fail("invalid_redirect");
    known.add(proposition.proposition_id);
  }
  const redirectMap = new Map<string, ProductPropositionRedirect>();
  for (const value of exactArray(input["redirects"], MAX_MEMBERS, "invalid_redirect")) {
    const redirect = redirectFields(value);
    if (redirect.owner_account_id !== owner || redirectMap.has(redirect.source_proposition_id)
      || !known.has(redirect.source_proposition_id)
      || redirect.successor_proposition_ids.some((id) => !known.has(id))) fail("invalid_redirect");
    redirectMap.set(redirect.source_proposition_id, redirect);
  }
  if (starts.some((id) => !known.has(id))) fail("invalid_redirect");

  const memo = new Map<string, ReadonlySet<string>>();
  const visiting = new Set<string>();
  const walk = (id: string, depth: number): ReadonlySet<string> => {
    if (depth > MAX_REDIRECT_DEPTH) fail("redirect_bound_exceeded");
    const cached = memo.get(id);
    if (cached) return cached;
    if (visiting.has(id)) fail("redirect_cycle");
    const redirect = redirectMap.get(id);
    if (!redirect) {
      const terminal = new Set([id]);
      memo.set(id, terminal);
      return terminal;
    }
    visiting.add(id);
    const terminals = new Set<string>();
    for (const successor of redirect.successor_proposition_ids) {
      for (const terminal of walk(successor, depth + 1)) {
        terminals.add(terminal);
        if (terminals.size > MAX_MEMBERS) fail("redirect_bound_exceeded");
      }
    }
    visiting.delete(id);
    memo.set(id, terminals);
    return terminals;
  };
  const terminals = new Set<string>();
  for (const start of starts) {
    for (const terminal of walk(start, 0)) terminals.add(terminal);
  }
  return Object.freeze([...terminals].sort());
};

const mappingFields = (value: unknown): LegacyPropositionMapping => {
  const code = "invalid_migration_mapping" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "legacy_source_id", "proposition_id",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION) fail(code);
  const mapping = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    legacy_source_id: token(input["legacy_source_id"], code),
    proposition_id: propositionId(input["proposition_id"], code),
  };
  const legacyLower = mapping.legacy_source_id.toLocaleLowerCase("en-US");
  if (mapping.proposition_id.toLocaleLowerCase("en-US").includes(legacyLower)) fail(code);
  return Object.freeze(mapping);
};

export const planLegacyPropositionMapping = (inputValue: Readonly<{
  owner_account_id: string;
  legacy_source_id: string;
  item_tombstoned: boolean;
  existing_mapping: LegacyPropositionMapping | null;
  proposed_random_opaque_proposition_id: string | null;
}>): LegacyPropositionMappingPlan => {
  const input = exactRecord(inputValue, [
    "owner_account_id", "legacy_source_id", "item_tombstoned", "existing_mapping",
    "proposed_random_opaque_proposition_id",
  ], "invalid_migration_mapping");
  const owner = token(input["owner_account_id"], "invalid_migration_mapping");
  const legacy = token(input["legacy_source_id"], "invalid_migration_mapping");
  if (typeof input["item_tombstoned"] !== "boolean") fail("invalid_migration_mapping");
  if (input["item_tombstoned"]) {
    if (input["proposed_random_opaque_proposition_id"] !== null) fail("invalid_migration_mapping");
    return Object.freeze({ kind: "tombstoned" });
  }
  if (input["existing_mapping"] !== null) {
    if (input["proposed_random_opaque_proposition_id"] !== null) fail("invalid_migration_mapping");
    const mapping = mappingFields(input["existing_mapping"]);
    if (mapping.owner_account_id !== owner || mapping.legacy_source_id !== legacy) fail("invalid_migration_mapping");
    return Object.freeze({ kind: "reuse_mapping", mapping });
  }
  if (input["proposed_random_opaque_proposition_id"] === null) {
    return Object.freeze({ kind: "allocation_required" });
  }
  const mapping = mappingFields({
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: owner,
    legacy_source_id: legacy,
    proposition_id: input["proposed_random_opaque_proposition_id"],
  });
  return Object.freeze({ kind: "insert_if_absent", mapping });
};

export const acceptLegacyMappingWinner = (
  attemptedValue: LegacyPropositionMapping,
  winnerValue: LegacyPropositionMapping,
): LegacyPropositionMapping => {
  const attempted = mappingFields(attemptedValue);
  const winner = mappingFields(winnerValue);
  if (attempted.owner_account_id !== winner.owner_account_id
    || attempted.legacy_source_id !== winner.legacy_source_id) fail("invalid_migration_mapping");
  return winner;
};

const groupFields = (value: unknown): ProductGroupProjection => {
  const code = "invalid_group_projection" as const;
  const input = exactRecord(value, [
    "version", "owner_account_id", "group_projection_id", "proposition_ids",
    "input_frontier", "projection_contract_digest", "result_digest",
    "created_at_event_time",
  ], code);
  if (input["version"] !== PRODUCT_PROJECTION_CONTRACT_VERSION) fail(code);
  const propositionIds = sortedUniqueTokens(input["proposition_ids"], MAX_MEMBERS, code)
    .map((id) => propositionId(id, code));
  if (propositionIds.length < 2) fail(code);
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], code),
    proposition_ids: Object.freeze(propositionIds),
    input_frontier: token(input["input_frontier"], code),
    projection_contract_digest: digest(input["projection_contract_digest"], code),
    result_digest: digest(input["result_digest"], code),
    created_at_event_time: eventTime(input["created_at_event_time"], code),
  };
  const expectedId = groupProjectionId(withoutId);
  if (input["group_projection_id"] !== expectedId) fail(code);
  return Object.freeze({ ...withoutId, group_projection_id: expectedId });
};

/** Strict persistence/replay parser for an already-derived rebuildable group. */
export const parseProductGroupProjection = (value: unknown): ProductGroupProjection =>
  groupFields(value);

export const buildProductGroupProjection = (inputValue: Readonly<{
  owner_account_id: string;
  proposition_ids: readonly string[];
  input_frontier: string;
  projection_contract_digest: string;
  result_digest: string;
  created_at_event_time: number;
}>): ProductGroupProjection => {
  const input = exactRecord(inputValue, [
    "owner_account_id", "proposition_ids", "input_frontier",
    "projection_contract_digest", "result_digest", "created_at_event_time",
  ], "invalid_group_projection");
  const withoutId = {
    version: PRODUCT_PROJECTION_CONTRACT_VERSION,
    owner_account_id: token(input["owner_account_id"], "invalid_group_projection"),
    proposition_ids: sortedUniqueTokens(input["proposition_ids"], MAX_MEMBERS, "invalid_group_projection")
      .map((id) => propositionId(id, "invalid_group_projection")),
    input_frontier: token(input["input_frontier"], "invalid_group_projection"),
    projection_contract_digest: digest(input["projection_contract_digest"], "invalid_group_projection"),
    result_digest: digest(input["result_digest"], "invalid_group_projection"),
    created_at_event_time: eventTime(input["created_at_event_time"], "invalid_group_projection"),
  };
  return groupFields({ ...withoutId, group_projection_id: groupProjectionId(withoutId as Omit<ProductGroupProjection, "group_projection_id">) });
};
