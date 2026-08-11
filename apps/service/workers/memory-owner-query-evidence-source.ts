import { isProxy } from "node:util/types";

import {
  genericPolicyClassifier,
  projectTreeInputSnapshot,
  type EvidenceSpan,
  type GraphSnapshot,
  type LiveClaimView,
  type RequestContext,
} from "../../../core/retrieve";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { deepFreezePlainJson, normalizePlainJson } from "../../../core/retrieve/plain-json";
import type { RecallTraceRef } from "../../../core/retrieve/recall-integrity";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import {
  defineMemoryEvaluationEvidenceSource,
  type MemoryEvaluationEvidenceSource,
  type MemoryEvaluationEvidenceSourceRequest,
} from "../stores/memory-evaluation-evidence-source";

const TRACE_REF = /^tr1_[a-f0-9]{64}$/;
const TOKEN = /^[\x21-\x7e]{1,256}$/;
const SUBJECT_CLASS = /^[a-z][a-z0-9_-]{0,63}$/;
const MAX_QUERY_CODE_POINTS = 4_096;
const MAX_CANDIDATE_CODE_POINTS = 65_536;
const MAX_CANDIDATES = 1_000;
const MAX_TOTAL_CANDIDATE_CODE_POINTS = 500_000;
const MAX_GRAPH_BYTES = 64 * 1024 * 1024;
const MAX_GRAPH_DEPTH = 128;
const MAX_GRAPH_NODES = 1_000_000;

type CommonOutcome =
  | Readonly<{ kind: "not_found" | "serialization_retryable" }>
  | Readonly<{
      kind: "stale_context";
      reason: "expired_context" | "stale_epoch" | "destination_inactive" | "lifecycle_inactive";
    }>
  | Readonly<{
      kind: "authorization_denied";
      reason: "credential_inactive" | "grant_inactive" | "capability_denied";
    }>;

export interface MemoryOwnerQueryGraphLoad {
  readonly kind: "found";
  readonly owner_account_id: string;
  readonly account_epoch: number;
  readonly source_ref: string;
  readonly input_frontier: string;
  readonly query_text: string;
  readonly account_timezone: string;
  readonly graph_snapshot: GraphSnapshot;
}

export interface MemoryOwnerQueryTraceRequest {
  readonly reader_projection_digest: string;
  readonly evidence_closure_digest: string;
}

export interface MemoryOwnerQueryEvidenceSourceDependencies {
  readonly load_graph: (
    context: AuthorizedLedgerWriteContext,
    request: MemoryEvaluationEvidenceSourceRequest,
  ) => Promise<MemoryOwnerQueryGraphLoad | CommonOutcome>;
  readonly encode_trace_ref: (request: MemoryOwnerQueryTraceRequest) => unknown;
}

const fail = (code: string): never => { throw new TypeError(`memory owner query source ${code}`); };
const compare = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) fail(code);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const boundedText = (value: unknown, maximum: number, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > maximum || /[\p{Cs}\u0000]/u.test(value)) fail(code);
  return value;
};

const outcomeKind = (value: unknown): string => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_loader_outcome");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !("value" in descriptor) || !descriptor.enumerable
    || typeof descriptor.value !== "string") fail("invalid_loader_outcome");
  return descriptor.value;
};

const commonOutcome = (value: unknown, kind: string): CommonOutcome | null => {
  if (kind === "not_found" || kind === "serialization_retryable") {
    exactRecord(value, ["kind"], "invalid_loader_outcome");
    return Object.freeze({ kind }) as CommonOutcome;
  }
  if (kind === "stale_context" || kind === "authorization_denied") {
    const input = exactRecord(value, ["kind", "reason"], "invalid_loader_outcome");
    const allowed = kind === "stale_context"
      ? ["expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive"]
      : ["credential_inactive", "grant_inactive", "capability_denied"];
    if (typeof input["reason"] !== "string" || !allowed.includes(input["reason"] as string)) {
      fail("invalid_loader_outcome");
    }
    return Object.freeze({ kind, reason: input["reason"] }) as CommonOutcome;
  }
  return null;
};

const detachGraph = (value: unknown, owner: string): GraphSnapshot => {
  const seen = new WeakSet<object>();
  let nodes = 0;
  const inspect = (node: unknown, depth: number): void => {
    nodes += 1;
    if (nodes > MAX_GRAPH_NODES || depth > MAX_GRAPH_DEPTH) fail("graph_budget_exceeded");
    if (node === null || typeof node === "string" || typeof node === "boolean") return;
    if (typeof node === "number") {
      if (!Number.isFinite(node)) fail("invalid_graph");
      return;
    }
    if (typeof node !== "object" || isProxy(node) || seen.has(node)) fail("invalid_graph");
    seen.add(node);
    const array = Array.isArray(node);
    const prototype = Object.getPrototypeOf(node);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) fail("invalid_graph");
    const keys = Reflect.ownKeys(node);
    if (keys.some((key) => typeof key !== "string")) fail("invalid_graph");
    if (array) {
      if (keys.length !== node.length + 1) fail("invalid_graph");
      for (let index = 0; index < node.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(node, String(index));
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_graph");
        inspect(descriptor.value, depth + 1);
      }
      if ((keys as string[]).some((key) => key !== "length"
        && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= node.length))) fail("invalid_graph");
      return;
    }
    for (const key of keys as string[]) {
      const descriptor = Object.getOwnPropertyDescriptor(node, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_graph");
      inspect(descriptor.value, depth + 1);
    }
  };
  inspect(value, 0);
  let detached: GraphSnapshot;
  try {
    detached = deepFreezePlainJson(normalizePlainJson(value)) as unknown as GraphSnapshot;
  } catch {
    return fail("invalid_graph");
  }
  if (Buffer.byteLength(JSON.stringify(detached), "utf8") > MAX_GRAPH_BYTES) fail("graph_budget_exceeded");
  if (detached.owner_account_id !== owner
    || !Array.isArray(detached.claims)
    || !Array.isArray(detached.entities)
    || !Array.isArray(detached.adjacency)) fail("invalid_graph");
  const visit = (node: unknown): void => {
    if (node === null || typeof node !== "object") return;
    if (Object.prototype.hasOwnProperty.call(node, "owner_account_id")
      && (node as { owner_account_id?: unknown }).owner_account_id !== owner) fail("cross_owner_graph");
    for (const nested of Object.values(node)) visit(nested);
  };
  visit(detached);
  return detached;
};

interface EvidenceSupport {
  readonly span: EvidenceSpan;
  readonly claims: LiveClaimView[];
}

const sameSpan = (left: EvidenceSpan, right: EvidenceSpan): boolean =>
  sha256CanonicalContent(left) === sha256CanonicalContent(right);

const leaksInternalCoordinate = (encoded: string, values: readonly string[]): boolean => values.some(
  (value) => value.length >= 8 && encoded.includes(value),
);

export const defineMemoryOwnerQueryEvidenceSource = (
  dependenciesValue: MemoryOwnerQueryEvidenceSourceDependencies,
): MemoryEvaluationEvidenceSource => {
  const dependencies = exactRecord(dependenciesValue, ["load_graph", "encode_trace_ref"], "invalid_dependencies");
  const loadGraph = dependencies["load_graph"];
  const encodeTraceRef = dependencies["encode_trace_ref"];
  if (typeof loadGraph !== "function" || isProxy(loadGraph)
    || typeof encodeTraceRef !== "function" || isProxy(encodeTraceRef)) fail("invalid_dependencies");

  return defineMemoryEvaluationEvidenceSource(async (context, request) => {
    if (request.source_kind !== "authorized_graph_snapshot") fail("invalid_source_kind");
    const raw = await Reflect.apply(loadGraph, undefined, [context, request]);
    const kind = outcomeKind(raw);
    const common = commonOutcome(raw, kind);
    if (common) return common;
    const input = exactRecord(raw, [
      "kind", "owner_account_id", "account_epoch", "source_ref", "input_frontier",
      "query_text", "account_timezone", "graph_snapshot",
    ], "invalid_loader_outcome");
    if (kind !== "found"
      || input["owner_account_id"] !== context.account_id
      || input["account_epoch"] !== context.account_epoch
      || input["source_ref"] !== request.source_ref
      || input["input_frontier"] !== request.input_frontier) fail("loader_coordinate_mismatch");
    const queryText = boundedText(input["query_text"], MAX_QUERY_CODE_POINTS, "invalid_query");
    const timezone = token(input["account_timezone"], "invalid_timezone");
    const graph = detachGraph(input["graph_snapshot"], context.account_id);
    const authorizationDigest = sha256CanonicalContent({
      contract_version: "owner-query-projection-authorization-v1",
      authorized_context: context,
      source_ref: request.source_ref,
      input_frontier: request.input_frontier,
    });
    const ownerContext: RequestContext = Object.freeze({
      reader_account_id: context.account_id,
      grant: Object.freeze({
        grant_id: `owner-shadow:${authorizationDigest}`,
        policy_classes: Object.freeze([]),
      }),
    });
    const projected = projectTreeInputSnapshot(graph, {
      account_timezone: timezone,
      classifier: genericPolicyClassifier,
      request_context: ownerContext,
      graph_generation: graph.graph_generation,
    });
    if (projected.owner_account_id !== context.account_id
      || projected.reader_projection_digest === null
      || projected.projection_authorization_digest !== null
      || projected.diagnostics.length !== 0) fail("invalid_projection");

    const byEvidence = new Map<string, EvidenceSupport>();
    for (const claim of projected.claims) {
      if (claim.placement_status !== "canonical" || claim.scope.locality !== "durable") continue;
      for (const span of claim.evidence_spans) {
        const existing = byEvidence.get(span.evidence_id);
        if (existing && !sameSpan(existing.span, span)) fail("ambiguous_evidence");
        if (existing && existing.claims.some((candidate) => candidate.claim_revision_id === claim.claim_revision_id)) {
          fail("duplicate_claim_evidence");
        }
        if (existing) existing.claims.push(claim);
        else byEvidence.set(span.evidence_id, { span, claims: [claim] });
      }
    }

    let totalCodePoints = 0;
    const candidates = [];
    for (const support of byEvidence.values()) {
      const excerpt = boundedText(support.span.excerpt, MAX_CANDIDATE_CODE_POINTS, "invalid_excerpt");
      totalCodePoints += [...excerpt].length;
      if (totalCodePoints > MAX_TOTAL_CANDIDATE_CODE_POINTS) fail("candidate_budget_exceeded");
      const classes = [...new Set(support.claims.map((claim) => claim.policy_class.subject_class))].sort(compare);
      if (classes.length === 0 || classes.some((value) => !SUBJECT_CLASS.test(value))) fail("invalid_subject_class");
      const supportingClaims = support.claims.map((claim) => claim.claim_revision_id).sort(compare);
      const evidenceClosureDigest = sha256CanonicalContent({
        contract_version: "owner-query-evidence-closure-v1",
        reader_projection_digest: projected.reader_projection_digest,
        evidence_id: support.span.evidence_id,
        event_revision_id: support.span.event_revision_id,
        capture_session_id: support.span.capture_session_id,
        range: support.span.range,
        supporting_claim_revision_ids: supportingClaims,
      });
      const encoded = Reflect.apply(encodeTraceRef, undefined, [Object.freeze({
        reader_projection_digest: projected.reader_projection_digest,
        evidence_closure_digest: evidenceClosureDigest,
      })]);
      const forbidden = [
        support.span.evidence_id, support.span.event_revision_id, support.span.capture_session_id,
        ...supportingClaims,
      ];
      if (typeof encoded !== "string" || !TRACE_REF.test(encoded)
        || leaksInternalCoordinate(encoded, forbidden)) fail("invalid_trace_ref");
      candidates.push(Object.freeze({
        trace_ref: encoded as RecallTraceRef,
        text: excerpt,
        contributing_subject_classes: Object.freeze(classes),
      }));
    }
    if (candidates.length > MAX_CANDIDATES) fail("candidate_budget_exceeded");
    candidates.sort((left, right) => compare(left.trace_ref, right.trace_ref));
    if (new Set(candidates.map((candidate) => candidate.trace_ref)).size !== candidates.length) {
      fail("trace_ref_collision");
    }
    const projectedContentDigest = sha256CanonicalContent({
      contract_version: "owner-query-projected-content-v1",
      projected_content_digest: projected.projected_content_digest,
      projection_generation_digest: projected.graph_generation,
      account_timezone: projected.account_timezone,
      classifier_version: projected.classifier_version,
    });
    return Object.freeze({
      kind: "found" as const,
      owner_account_id: context.account_id,
      account_epoch: context.account_epoch,
      source_kind: request.source_kind,
      source_ref: request.source_ref,
      input_frontier: request.input_frontier,
      payload: Object.freeze({
        version: "authorized-query-evaluation-input-v1" as const,
        query_text: queryText,
        projection_authorization_digest: authorizationDigest,
        reader_projection_digest: projected.reader_projection_digest,
        projected_content_digest: projectedContentDigest,
        classifier_version: projected.classifier_version,
        candidates: Object.freeze(candidates),
      }),
    });
  });
};
