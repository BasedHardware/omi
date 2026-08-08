// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMX-001)
import { sha256CanonicalRedacted } from "../ledger";
import type { PolicyClass, TreeInputSnapshot } from "./index";
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-006)
import { APPLICATION_DEFAULT_SYNTHESIZED_POLICY, isApplicationGrantProjectedTreeInput, type ApplicationGrantProjectedTreeInputSnapshot } from "./authorization-boundary";
import { isProducedRenderNode, type RenderNode } from "./render";
import { restrictivePolicyJoin, validateRestrictiveJoin } from "./policy";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export type SynthesizedProjectionDenial =
  | "owner_mismatch"
  | "authorization_binding_mismatch"
  | "generation_mismatch"
  | "render_not_ready"
  | "render_stale"
  | "render_identity_invalid"
  | "claim_revision_mismatch"
  | "citation_mismatch"
  | "policy_mismatch";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export class SynthesizedProjectionDenied extends Error {
  constructor(readonly reason: SynthesizedProjectionDenial) {
    super(`synthesized projection denied: ${reason}`);
    this.name = "SynthesizedProjectionDenied";
  }
}

// domain-pending(DIV-DOMCORE-008)
export interface SynthesizedCitation {
  evidence_id: string;
  event_revision_id: string;
  capture_session_id: string;
  claim_revision_ids: readonly string[];
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMX-005)
export interface OwnerBoundSynthesizedProjectionEnvelope {
  owner_account_id: string;
  graph_generation: string;
  projection_authorization_digest: string;
  reader_projection_digest: string;
  projected_content_digest: string;
  node_id: string;
  render_generation: string;
  render_hash: string;
  rendered_from_digest: string;
  live_claim_revision_ids: readonly string[];
  citations: readonly SynthesizedCitation[];
  effective_policy: Readonly<PolicyClass>;
  synthesized_summary: string;
}

const fail = (reason: SynthesizedProjectionDenial): never => { throw new SynthesizedProjectionDenied(reason); };
const sortedUnique = (values: readonly string[]): string[] => [...new Set(values)].sort();
const exactStrings = (left: readonly string[], right: readonly string[]): boolean =>
  left.length === right.length && left.every((value, index) => value === right[index]);
const samePolicy = (left: PolicyClass, right: PolicyClass): boolean =>
  left.subject_class === right.subject_class && left.sensitivity === right.sensitivity && left.capture_class === right.capture_class;
const policyPartitionLabel = (policy: PolicyClass): string =>
  `subject_class=${policy.subject_class}|sensitivity=${policy.sensitivity}|capture_class=${policy.capture_class}`;
const sameSpan = (
  left: TreeInputSnapshot["evidence_index"][number],
  right: TreeInputSnapshot["evidence_index"][number],
): boolean => left.evidence_id === right.evidence_id
  && left.event_revision_id === right.event_revision_id
  && left.capture_session_id === right.capture_session_id
  && left.excerpt === right.excerpt
  && left.range.start === right.range.start
  && left.range.end === right.range.end
  && exactStrings([...left.policy_labels].sort(), [...right.policy_labels].sort());

const freezeEnvelope = (value: OwnerBoundSynthesizedProjectionEnvelope): OwnerBoundSynthesizedProjectionEnvelope => {
  for (const citation of value.citations) {
    Object.freeze(citation.claim_revision_ids);
    Object.freeze(citation);
  }
  Object.freeze(value.citations);
  Object.freeze(value.live_claim_revision_ids);
  Object.freeze(value.effective_policy);
  return Object.freeze(value);
};

/**
 * Internal L2+ boundary only. It deliberately retains identifiers needed to
 * verify provenance, but never retains excerpts, event payloads, source rows,
 * caller-provided classification labels, or references to mutable input objects.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-007)
// domain-pending(DIV-DOMX-005)
export const buildOwnerBoundSynthesizedProjection = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  render: RenderNode,
): OwnerBoundSynthesizedProjectionEnvelope => {
  if (!isApplicationGrantProjectedTreeInput(input)
    || render.projection_authorization_digest !== input.projection_authorization_digest
    || render.reader_projection_digest !== input.reader_projection_digest
    || render.projected_content_digest !== input.projected_content_digest) fail("authorization_binding_mismatch");
  if (!input.owner_account_id || render.owner_account_id !== input.owner_account_id) fail("owner_mismatch");
  if (!input.graph_generation || render.graph_generation !== input.graph_generation) fail("generation_mismatch");
  if (render.status !== "ready" || render.summary_text === null || render.summary_text.length === 0 || render.failure !== null) fail("render_not_ready");
  if (render.stale) fail("render_stale");
  if (!render.node_id || !render.render_generation || !render.render_hash || !render.rendered_from_digest) fail("render_identity_invalid");

  // domain-pending(DIV-DOMX-001)
  const expectedRenderHash = sha256CanonicalRedacted({
    owner_account_id: render.owner_account_id,
    graph_generation: render.graph_generation,
    reader_projection_digest: render.reader_projection_digest,
    projection_authorization_digest: render.projection_authorization_digest,
    projected_content_digest: render.projected_content_digest,
    node_id: render.node_id,
    rendered_from_digest: render.rendered_from_digest,
    rendered_from_manifest: render.rendered_from_manifest,
    summary_text: render.summary_text,
    citations: [...render.citations].sort(),
    effective_policy: render.effective_policy,
  });
  if (render.render_hash !== expectedRenderHash || render.render_generation !== `render-v1:${render.render_hash}`) fail("render_identity_invalid");
  if (!isProducedRenderNode(render)) fail("render_identity_invalid");

  const memberIds = [...render.rendered_from_manifest.live_member_revisions].sort();
  if (memberIds.length === 0 || !exactStrings(memberIds, sortedUnique(memberIds))) fail("claim_revision_mismatch");
  const claimByRevision = new Map(input.claims.map((claim) => [claim.claim_revision_id, claim]));
  if (claimByRevision.size !== input.claims.length) fail("claim_revision_mismatch");
  const claims = memberIds.map((revision) => claimByRevision.get(revision));
  if (claims.some((claim) => claim === undefined)) fail("claim_revision_mismatch");
  const liveClaims = claims.filter((claim): claim is NonNullable<typeof claim> => claim !== undefined);
  if (input.diagnostics.some((diagnostic) => "claim_revision_id" in diagnostic
    ? memberIds.includes(diagnostic.claim_revision_id)
    : diagnostic.claim_revision_ids.length > 1 && diagnostic.claim_revision_ids.some((revision) => memberIds.includes(revision)))) fail("claim_revision_mismatch");

  const policies = liveClaims.map((claim) => claim.policy_class);
  const effectivePolicy = restrictivePolicyJoin(policies);
  if (!validateRestrictiveJoin(render.effective_policy, policies)
    || !samePolicy(render.effective_policy, effectivePolicy)
    || !samePolicy(effectivePolicy, APPLICATION_DEFAULT_SYNTHESIZED_POLICY)
    || render.policy_partition_label !== policyPartitionLabel(effectivePolicy)) fail("policy_mismatch");

  const evidenceIndex = new Map(input.evidence_index.map((span) => [span.evidence_id, span]));
  if (evidenceIndex.size !== input.evidence_index.length) fail("citation_mismatch");
  const evidenceToClaims = new Map<string, string[]>();
  for (const claim of liveClaims) {
    const refs = [...claim.evidence_refs].sort();
    if (refs.length === 0 || !exactStrings(refs, sortedUnique(refs))) fail("citation_mismatch");
    const spans = [...claim.evidence_spans].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id));
    if (!exactStrings(spans.map((span) => span.evidence_id), refs)) fail("citation_mismatch");
    for (const span of spans) {
      const indexed = evidenceIndex.get(span.evidence_id);
      if (!indexed || !sameSpan(span, indexed)) fail("citation_mismatch");
      evidenceToClaims.set(span.evidence_id, [...(evidenceToClaims.get(span.evidence_id) ?? []), claim.claim_revision_id]);
    }
  }
  const evidenceIds = [...evidenceToClaims.keys()].sort();
  const renderedCitations = [...render.citations].sort();
  if (!exactStrings(renderedCitations, sortedUnique(renderedCitations)) || !exactStrings(renderedCitations, evidenceIds)) fail("citation_mismatch");

  const citations = evidenceIds.map((evidenceId): SynthesizedCitation => {
    const span = evidenceIndex.get(evidenceId)!;
    return {
      evidence_id: String(span.evidence_id),
      event_revision_id: String(span.event_revision_id),
      capture_session_id: String(span.capture_session_id),
      claim_revision_ids: sortedUnique(evidenceToClaims.get(evidenceId) ?? []),
    };
  });
  return freezeEnvelope({
    owner_account_id: String(input.owner_account_id),
    graph_generation: String(input.graph_generation),
    projection_authorization_digest: String(input.projection_authorization_digest),
    reader_projection_digest: String(input.reader_projection_digest),
    projected_content_digest: String(input.projected_content_digest),
    node_id: String(render.node_id),
    render_generation: String(render.render_generation),
    render_hash: String(render.render_hash),
    rendered_from_digest: String(render.rendered_from_digest),
    live_claim_revision_ids: [...memberIds],
    citations,
    effective_policy: { ...effectivePolicy },
    synthesized_summary: String(render.summary_text),
  });
};
