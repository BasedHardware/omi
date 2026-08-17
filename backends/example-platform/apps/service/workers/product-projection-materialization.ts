import { isProxy } from "node:util/types";

import {
  buildProductProjectionRevision,
  parseProductMembershipRevision,
  parseProductPropositionIdentity,
  type ProductMembershipRevision,
  type ProductProjectionCitationSupport,
  type ProductPropositionIdentity,
} from "../../../core/retrieve/product-projection";
import {
  buildOwnerBoundSynthesizedProjection,
} from "../../../core/retrieve/projection-boundary";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  isApplicationGrantProjectedTreeInput,
  type ApplicationGrantProjectedTreeInputSnapshot,
} from "../../../core/retrieve/authorization-boundary";
import { isProducedRenderNode, type RenderNode } from "../../../core/retrieve/render";
import { deepFreezePlainJson } from "../../../core/retrieve/plain-json";
import type {
  ProductGraphCoordinate,
  ProductProjectionPayload,
  ProductProjectionWriteBody,
  ProductProjectionWriteRequest,
} from "../stores/product-projection-repository";
import { productProjectionWriteRequestDigest } from
  "../stores/product-projection-repository";

export const PRODUCT_RENDERED_CONTENT_VERSION = "product-rendered-content-v1" as const;

export interface AuthorizedProductProjectionMaterializationInput {
  readonly authorized_input: ApplicationGrantProjectedTreeInputSnapshot;
  readonly render: RenderNode;
  readonly identity: ProductPropositionIdentity;
  readonly membership: ProductMembershipRevision;
  readonly graph: ProductGraphCoordinate;
  readonly projection_sequence: number;
  readonly created_at_event_time: number;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const LANGUAGE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const MAX_PAYLOAD_BYTES = 256 * 1024;

const fail = (code: string): never => {
  throw new TypeError(`product projection materialization ${code}`);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.some((key) => typeof key !== "string")) fail(code);
  const actual = (ownKeys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value as object, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value as string;
};

const positive = (value: unknown, code: string): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 1) fail(code);
  return value as number;
};

const eventTime = (value: unknown): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0) fail("invalid_event_time");
  return value as number;
};

const parseGraph = (
  value: unknown,
  owner: string,
  frontier: string,
): Readonly<ProductGraphCoordinate> => {
  const graph = exactRecord(value, [
    "owner_account_id", "graph_frontier", "graph_commit_id", "graph_commit_sequence",
  ], "invalid_graph");
  if (token(graph["owner_account_id"], "invalid_graph") !== owner
    || token(graph["graph_frontier"], "invalid_graph") !== frontier) {
    fail("graph_coordinate_mismatch");
  }
  return Object.freeze({
    owner_account_id: owner,
    graph_frontier: frontier,
    graph_commit_id: token(graph["graph_commit_id"], "invalid_graph"),
    graph_commit_sequence: positive(graph["graph_commit_sequence"], "invalid_graph"),
  });
};

export const buildAuthorizedProductProjectionWriteRequest = (
  inputValue: AuthorizedProductProjectionMaterializationInput,
): ProductProjectionWriteRequest => {
  const input = exactRecord(inputValue, [
    "authorized_input", "render", "identity", "membership", "graph",
    "projection_sequence", "created_at_event_time",
  ], "invalid_input");
  const authorizedCandidate = input["authorized_input"] as ApplicationGrantProjectedTreeInputSnapshot;
  if (!isApplicationGrantProjectedTreeInput(authorizedCandidate)
    || !isProducedRenderNode(input["render"])) fail("untrusted_input");

  const authorizedInput = authorizedCandidate;
  const render = input["render"] as RenderNode;
  const synthesized = buildOwnerBoundSynthesizedProjection(authorizedInput, render);
  const identity = parseProductPropositionIdentity(input["identity"]);
  const membership = parseProductMembershipRevision(input["membership"]);
  if (identity.owner_account_id !== synthesized.owner_account_id
    || membership.owner_account_id !== synthesized.owner_account_id
    || membership.proposition_id !== identity.proposition_id
    || membership.graph_frontier !== synthesized.graph_generation) {
    fail("product_coordinate_mismatch");
  }
  const graph = parseGraph(input["graph"], synthesized.owner_account_id, synthesized.graph_generation);

  const claimByRevision = new Map<string, ApplicationGrantProjectedTreeInputSnapshot["claims"][number]>();
  for (const claim of authorizedInput.claims) {
    if (claimByRevision.has(claim.claim_revision_id)) fail("duplicate_claim_revision");
    claimByRevision.set(claim.claim_revision_id, claim);
  }
  const citations: ProductProjectionCitationSupport[] = [];
  const seenLineages = new Set<string>();
  for (const claimRevisionId of synthesized.live_claim_revision_ids) {
    const claim = claimByRevision.get(claimRevisionId) ?? fail("missing_claim_revision");
    if (seenLineages.has(claim.claim_lineage_id)) fail("duplicate_lineage_revision");
    seenLineages.add(claim.claim_lineage_id);
    citations.push(Object.freeze({
      claim_lineage_id: String(claim.claim_lineage_id),
      claim_revision_id: String(claim.claim_revision_id),
      evidence_refs: Object.freeze([...claim.evidence_refs].sort()),
    }));
  }
  citations.sort((left, right) => left.claim_lineage_id.localeCompare(right.claim_lineage_id)
    || left.claim_revision_id.localeCompare(right.claim_revision_id));
  if (seenLineages.size !== membership.member_claim_lineage_ids.length
    || membership.member_claim_lineage_ids.some((lineage) => !seenLineages.has(lineage))) {
    fail("membership_render_mismatch");
  }
  if (!LANGUAGE.test(render.source_language)) fail("invalid_source_language");

  const renderedContent = deepFreezePlainJson({
    version: PRODUCT_RENDERED_CONTENT_VERSION,
    summary_text: synthesized.synthesized_summary,
    source_language: render.source_language,
    effective_policy: {
      subject_class: synthesized.effective_policy.subject_class,
      sensitivity: synthesized.effective_policy.sensitivity,
      capture_class: synthesized.effective_policy.capture_class,
    },
  });
  if (Buffer.byteLength(JSON.stringify(renderedContent), "utf8") > MAX_PAYLOAD_BYTES) {
    fail("payload_too_large");
  }
  const renderedContentDigest = sha256CanonicalContent(renderedContent);
  const projection = buildProductProjectionRevision({
    identity,
    membership,
    projection_sequence: positive(input["projection_sequence"], "invalid_projection_sequence"),
    graph_frontier: synthesized.graph_generation,
    renderer_contract_digest: synthesized.renderer_contract_digest,
    rendered_content_digest: renderedContentDigest,
    citations,
    created_at_event_time: eventTime(input["created_at_event_time"]),
  });
  const payload: ProductProjectionPayload = Object.freeze({
    owner_account_id: synthesized.owner_account_id,
    projection_revision_id: projection.projection_revision_id,
    rendered_content_digest: renderedContentDigest,
    payload_contract_version: PRODUCT_RENDERED_CONTENT_VERSION,
    rendered_content: renderedContent,
  });
  const body: Extract<ProductProjectionWriteBody, { operation: "projection" }> = Object.freeze({
    operation: "projection",
    graph,
    identity,
    membership,
    projection,
    payload,
  });
  return Object.freeze({
    ...body,
    request_digest: productProjectionWriteRequestDigest(body),
  });
};
