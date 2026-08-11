import { isProxy } from "node:util/types";

import type { CanonicalJson } from "../../../core/ledger";
import {
  buildAuthorizedProductProjectionSet,
  parseProductGroupProjection,
  parseProductMembershipRevision,
  parseProductProjectionRevision,
  parseProductPropositionIdentity,
  parseProductPropositionRedirect,
  selectLatestAuthorizedProductProjection,
  type AuthorizedProductProjectionSet,
  type ProductGroupProjection,
  type ProductMembershipRevision,
  type ProductProjectionRevision,
  type ProductPropositionIdentity,
  type ProductPropositionRedirect,
} from "../../../core/retrieve/product-projection";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  isApplicationGrantProjectedTreeInput,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "../../../core/retrieve/authorization-boundary";
import { deepFreezePlainJson, normalizePlainJson } from "../../../core/retrieve/plain-json";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const WRITE_PORT: unique symbol = Symbol("product-projection-write-repository");
const READ_PORT: unique symbol = Symbol("product-projection-read-repository");
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const MAX_RENDERED_CONTENT_BYTES = 256 * 1024;
const MAX_READ_ROWS = 10_000;
const PROJECTOR_CAPABILITY = "memories.project";

export interface ProductGraphCoordinate {
  readonly owner_account_id: string;
  readonly graph_frontier: string;
  readonly graph_commit_id: string;
  readonly graph_commit_sequence: number;
}

export type ProductRenderedContent = Readonly<Record<string, CanonicalJson>>;

export interface ProductProjectionPayload {
  readonly owner_account_id: string;
  readonly projection_revision_id: string;
  readonly rendered_content_digest: string;
  readonly payload_contract_version: string;
  readonly rendered_content: ProductRenderedContent;
}

export type ProductProjectionWriteBody =
  | Readonly<{
      operation: "birth";
      graph: ProductGraphCoordinate;
      identity: ProductPropositionIdentity;
      membership: ProductMembershipRevision;
    }>
  | Readonly<{
      operation: "membership";
      graph: ProductGraphCoordinate;
      identity: ProductPropositionIdentity;
      membership: ProductMembershipRevision;
    }>
  | Readonly<{
      operation: "projection";
      graph: ProductGraphCoordinate;
      identity: ProductPropositionIdentity;
      membership: ProductMembershipRevision;
      projection: ProductProjectionRevision;
      payload: ProductProjectionPayload;
    }>
  | Readonly<{
      operation: "redirect";
      graph: ProductGraphCoordinate;
      redirect: ProductPropositionRedirect;
    }>
  | Readonly<{
      operation: "group";
      graph: ProductGraphCoordinate;
      group: ProductGroupProjection;
    }>;

export type ProductProjectionWriteRequest = ProductProjectionWriteBody & Readonly<{
  request_digest: string;
}>;

export type ProductProjectionWriteOutcome =
  | Readonly<{ kind: "appended" }>
  | Readonly<{ kind: "replayed" }>
  | Readonly<{ kind: "idempotency_conflict" }>
  | Readonly<{ kind: "stale_graph" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>
  | Readonly<{ kind: "serialization_retryable" }>;

export interface ProductProjectionWriteRepository {
  readonly [WRITE_PORT]: true;
  append(
    context: AuthorizedLedgerWriteContext,
    request: ProductProjectionWriteRequest,
  ): Promise<ProductProjectionWriteOutcome>;
}

export type ProductProjectionWriteImplementation = (
  context: AuthorizedLedgerWriteContext,
  request: ProductProjectionWriteRequest,
) => Promise<ProductProjectionWriteOutcome>;

export interface ProductProjectionReadRows {
  readonly identities: readonly ProductPropositionIdentity[];
  readonly memberships: readonly ProductMembershipRevision[];
  readonly projections: readonly ProductProjectionRevision[];
  readonly payloads: readonly ProductProjectionPayload[];
}

export interface AuthorizedProductProjectionReadSet extends ProductProjectionReadRows {
  readonly owner_account_id: string;
  readonly graph_frontier: string;
  readonly reader_projection_digest: string;
  readonly projection_authorization_digest: string;
  readonly authorized_projections: AuthorizedProductProjectionSet;
}

export interface ProductProjectionReadRepository {
  readonly [READ_PORT]: true;
  loadAuthorized(
    input: ApplicationGrantProjectedTreeInputSnapshot,
  ): Promise<AuthorizedProductProjectionReadSet>;
}

export type ProductProjectionReadImplementation = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
) => Promise<unknown>;

const authorizedReadSets = new WeakSet<object>();
const productProjectionReadRepositories = new WeakSet<object>();

function fail(code: string): never {
  throw new TypeError(`product projection repository ${code}`);
}

const exactRecord = (value: unknown, expected: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, code: string): readonly unknown[] => {
  if (value === null || typeof value !== "object" || isProxy(value) || !Array.isArray(value)
    || Object.getPrototypeOf(value) !== Array.prototype || value.length > MAX_READ_ROWS) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.length !== value.length + 1 || keys.some((key) => typeof key !== "string")
    || (keys as string[]).some((key) => key !== "length"
      && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length))) fail(code);
  const output: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output.push(descriptor.value);
  }
  return output;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const digest = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !DIGEST.test(value)) fail(code);
  return value;
};

const positiveSequence = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) fail(code);
  return value as number;
};

const parseGraph = (value: unknown, owner: string): ProductGraphCoordinate => {
  const input = exactRecord(value, [
    "owner_account_id", "graph_frontier", "graph_commit_id", "graph_commit_sequence",
  ], "invalid_graph");
  if (token(input["owner_account_id"], "invalid_graph") !== owner) fail("owner_mismatch");
  return Object.freeze({
    owner_account_id: owner,
    graph_frontier: token(input["graph_frontier"], "invalid_graph"),
    graph_commit_id: token(input["graph_commit_id"], "invalid_graph"),
    graph_commit_sequence: positiveSequence(input["graph_commit_sequence"], "invalid_graph"),
  });
};

const parsePayload = (value: unknown, owner: string): ProductProjectionPayload => {
  const input = exactRecord(value, [
    "owner_account_id", "projection_revision_id", "rendered_content_digest",
    "payload_contract_version", "rendered_content",
  ], "invalid_payload");
  if (token(input["owner_account_id"], "invalid_payload") !== owner) fail("owner_mismatch");
  let normalized: unknown;
  try {
    normalized = normalizePlainJson(input["rendered_content"]);
  } catch {
    return fail("invalid_payload");
  }
  if (normalized === null || typeof normalized !== "object" || Array.isArray(normalized)) fail("invalid_payload");
  const encoded = JSON.stringify(normalized);
  if (Buffer.byteLength(encoded, "utf8") > MAX_RENDERED_CONTENT_BYTES) fail("payload_too_large");
  const renderedDigest = digest(input["rendered_content_digest"], "invalid_payload");
  if (sha256CanonicalContent(normalized) !== renderedDigest) fail("payload_digest_mismatch");
  return Object.freeze({
    owner_account_id: owner,
    projection_revision_id: token(input["projection_revision_id"], "invalid_payload"),
    rendered_content_digest: renderedDigest,
    payload_contract_version: token(input["payload_contract_version"], "invalid_payload"),
    rendered_content: deepFreezePlainJson(normalized) as ProductRenderedContent,
  });
};

const ownerIdentity = (value: unknown, owner: string): ProductPropositionIdentity => {
  const identity = parseProductPropositionIdentity(value);
  if (identity.owner_account_id !== owner) fail("owner_mismatch");
  return identity;
};

const ownerMembership = (value: unknown, owner: string): ProductMembershipRevision => {
  const membership = parseProductMembershipRevision(value);
  if (membership.owner_account_id !== owner) fail("owner_mismatch");
  return membership;
};

const assertIdentityMembership = (
  identity: ProductPropositionIdentity,
  membership: ProductMembershipRevision,
  graph: ProductGraphCoordinate,
): void => {
  if (identity.proposition_id !== membership.proposition_id
    || membership.graph_frontier !== graph.graph_frontier) fail("coordinate_mismatch");
};

export const productProjectionWriteRequestDigest = (body: ProductProjectionWriteBody): string =>
  sha256CanonicalContent({ contract_version: "product-projection-repository-v1", ...body });

export const assertProductProjectionWriteRequest = (
  contextValue: AuthorizedLedgerWriteContext,
  value: unknown,
): ProductProjectionWriteRequest => {
  const context = assertAuthorizedLedgerWriteContext(contextValue);
  if (context.capability !== PROJECTOR_CAPABILITY) fail("capability_denied");
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_request");
  const operationDescriptor = Object.getOwnPropertyDescriptor(value, "operation");
  if (!operationDescriptor || !("value" in operationDescriptor) || !operationDescriptor.enumerable) {
    fail("invalid_request");
  }
  const requestedOperation = operationDescriptor.value;
  const root = exactRecord(value, [
    "request_digest", "operation", "graph",
    ...(requestedOperation === "projection" ? ["identity", "membership", "projection", "payload"]
      : requestedOperation === "birth" || requestedOperation === "membership"
        ? ["identity", "membership"]
        : requestedOperation === "redirect" ? ["redirect"]
          : requestedOperation === "group" ? ["group"] : []),
  ], "invalid_request");
  const requestDigest = digest(root["request_digest"], "invalid_request");
  const operation = root["operation"];
  if (typeof operation !== "string") fail("invalid_request");
  const graph = parseGraph(root["graph"], context.account_id);
  let body: ProductProjectionWriteBody;
  if (operation === "birth" || operation === "membership") {
    const identity = ownerIdentity(root["identity"], context.account_id);
    const membership = ownerMembership(root["membership"], context.account_id);
    assertIdentityMembership(identity, membership, graph);
    if (operation === "birth") {
      if (membership.cause !== "birth" || membership.revision_sequence !== 1
        || membership.member_claim_lineage_ids.length !== 1
        || membership.member_claim_lineage_ids[0] !== identity.birth_claim_lineage_id) fail("invalid_birth");
      body = Object.freeze({ operation, graph, identity, membership });
    } else {
      if (membership.cause === "birth" || membership.revision_sequence < 2) fail("invalid_membership");
      body = Object.freeze({ operation, graph, identity, membership });
    }
  } else if (operation === "projection") {
    const identity = ownerIdentity(root["identity"], context.account_id);
    const membership = ownerMembership(root["membership"], context.account_id);
    const projection = parseProductProjectionRevision(root["projection"]);
    const payload = parsePayload(root["payload"], context.account_id);
    assertIdentityMembership(identity, membership, graph);
    if (projection.owner_account_id !== context.account_id
      || projection.proposition_id !== identity.proposition_id
      || projection.membership_revision_id !== membership.membership_revision_id
      || projection.graph_frontier !== graph.graph_frontier
      || payload.projection_revision_id !== projection.projection_revision_id
      || payload.rendered_content_digest !== projection.rendered_content_digest) fail("coordinate_mismatch");
    body = Object.freeze({ operation, graph, identity, membership, projection, payload });
  } else if (operation === "redirect") {
    const redirect = parseProductPropositionRedirect(root["redirect"]);
    if (redirect.owner_account_id !== context.account_id) fail("owner_mismatch");
    body = Object.freeze({ operation, graph, redirect });
  } else if (operation === "group") {
    const group = parseProductGroupProjection(root["group"]);
    if (group.owner_account_id !== context.account_id) fail("owner_mismatch");
    if (group.input_frontier !== graph.graph_frontier) fail("coordinate_mismatch");
    body = Object.freeze({ operation, graph, group });
  } else {
    return fail("invalid_request");
  }
  if (productProjectionWriteRequestDigest(body) !== requestDigest) fail("request_digest_mismatch");
  return Object.freeze({ ...body, request_digest: requestDigest });
};

export const defineProductProjectionWriteRepository = (
  implementation: ProductProjectionWriteImplementation,
): ProductProjectionWriteRepository => Object.freeze({
  [WRITE_PORT]: true as const,
  async append(context: AuthorizedLedgerWriteContext, request: ProductProjectionWriteRequest): Promise<ProductProjectionWriteOutcome> {
    const authorized = assertAuthorizedLedgerWriteContext(context);
    return await implementation(authorized, assertProductProjectionWriteRequest(authorized, request));
  },
});

const parseReadRows = (value: unknown, input: ApplicationGrantProjectedTreeInputSnapshot): AuthorizedProductProjectionReadSet => {
  const root = exactRecord(value, ["identities", "memberships", "projections", "payloads"], "invalid_read_rows");
  const identities = exactArray(root["identities"], "invalid_read_rows")
    .map((item) => ownerIdentity(item, input.owner_account_id));
  const memberships = exactArray(root["memberships"], "invalid_read_rows")
    .map((item) => ownerMembership(item, input.owner_account_id));
  const projections = exactArray(root["projections"], "invalid_read_rows")
    .map((item) => parseProductProjectionRevision(item));
  const payloads = exactArray(root["payloads"], "invalid_read_rows")
    .map((item) => parsePayload(item, input.owner_account_id));
  const projectedPropositionIds = new Set(projections.map((projection) => projection.proposition_id));
  const projectedMembershipIds = new Set(projections.map((projection) => projection.membership_revision_id));
  if (identities.length !== projectedPropositionIds.size
    || identities.some((identity) => !projectedPropositionIds.has(identity.proposition_id))
    || memberships.length !== projectedMembershipIds.size
    || memberships.some((membership) => !projectedMembershipIds.has(membership.membership_revision_id))) {
    fail("read_row_closure_mismatch");
  }
  const authorized = buildAuthorizedProductProjectionSet(input, identities, memberships, projections);
  const payloadByProjection = new Map<string, ProductProjectionPayload>();
  for (const payload of payloads) {
    if (payloadByProjection.has(payload.projection_revision_id)) fail("duplicate_payload");
    payloadByProjection.set(payload.projection_revision_id, payload);
  }
  if (payloadByProjection.size !== projections.length
    || projections.some((projection) => {
      const payload = payloadByProjection.get(projection.projection_revision_id);
      return !payload || payload.rendered_content_digest !== projection.rendered_content_digest;
    })) fail("payload_projection_mismatch");
  identities.sort((left, right) => left.proposition_id.localeCompare(right.proposition_id));
  memberships.sort((left, right) => left.membership_revision_id.localeCompare(right.membership_revision_id));
  projections.sort((left, right) => left.projection_revision_id.localeCompare(right.projection_revision_id));
  payloads.sort((left, right) => left.projection_revision_id.localeCompare(right.projection_revision_id));
  const result: AuthorizedProductProjectionReadSet = Object.freeze({
    owner_account_id: String(input.owner_account_id),
    graph_frontier: String(input.graph_generation),
    reader_projection_digest: String(input.reader_projection_digest),
    projection_authorization_digest: String(input.projection_authorization_digest),
    identities: Object.freeze(identities),
    memberships: Object.freeze(memberships),
    projections: Object.freeze(projections),
    payloads: Object.freeze(payloads),
    authorized_projections: authorized,
  });
  authorizedReadSets.add(result);
  return result;
};

export const defineProductProjectionReadRepository = (
  implementation: ProductProjectionReadImplementation,
): ProductProjectionReadRepository => {
  const repository: ProductProjectionReadRepository = Object.freeze({
    [READ_PORT]: true as const,
    async loadAuthorized(input: ApplicationGrantProjectedTreeInputSnapshot): Promise<AuthorizedProductProjectionReadSet> {
      if (!isApplicationGrantProjectedTreeInput(input)) fail("unauthorized_read_input");
      return parseReadRows(await implementation(input), input);
    },
  });
  productProjectionReadRepositories.add(repository);
  return repository;
};

/** Runtime identity check for composition; this grants no read or write authority. */
export const inspectProductProjectionReadRepository = (
  value: unknown,
): ProductProjectionReadRepository => {
  if (value === null || typeof value !== "object" || !productProjectionReadRepositories.has(value)) {
    fail("invalid_read_repository");
  }
  return value as ProductProjectionReadRepository;
};

export const selectLatestAuthorizedProductProjectionPayload = (
  identityValue: ProductPropositionIdentity,
  readSet: AuthorizedProductProjectionReadSet,
): Readonly<{ projection: ProductProjectionRevision; payload: ProductProjectionPayload }> | null => {
  const identity = parseProductPropositionIdentity(identityValue);
  if (!authorizedReadSets.has(readSet) || readSet.owner_account_id !== identity.owner_account_id) {
    return fail("unauthorized_read_set");
  }
  const projection = selectLatestAuthorizedProductProjection(identity, readSet.authorized_projections);
  if (!projection) return null;
  const payload = readSet.payloads.find((item) => item.projection_revision_id === projection.projection_revision_id);
  if (!payload) return fail("payload_projection_mismatch");
  return Object.freeze({ projection, payload });
};
