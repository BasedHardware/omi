import { retrieveCommittedGraph, type GraphSnapshot, type LiveClaimView, type TreeInputSnapshot } from "./index";
import type { RenderNode } from "./render";

export interface DogfoodRequest {
  owner_account_id: string;
  query: string;
  entity_id?: string;
  as_of?: string;
  capture_session_id?: string;
  /** Grant evaluation is deferred; this explicit class is only the safe compose partition. */
  grant_class: string;
}
export interface ComposeModelPort {
  compose(request: { strategy: string; version: string; input: unknown }): Promise<{ answer_text: string; citations: readonly string[] }>;
}
export type AbsenceDisclosure =
  | { kind: "query_gap"; message: "no cited memory matched" }
  | { kind: "policy_omission"; grant_class: string; message: "some matching memory is omitted by your grant class" };
export interface DogfoodResponse { answer_text: string | null; citations: readonly string[]; hydrated_claim_revision_ids: readonly string[]; absence: AbsenceDisclosure | null; }

const words = (text: string) => text.toLocaleLowerCase().split(/[^\p{L}\p{N}_-]+/u).filter(Boolean);
const matches = (query: string, text: string | null) => {
  const qs = words(query); const haystack = new Set(words(text ?? ""));
  return qs.length > 0 && qs.some((word) => haystack.has(word));
};
const policyAllowed = (claim: LiveClaimView, grant: string) => grant === "all" || claim.policy_class.sensitivity === "generic" || claim.policy_class.sensitivity === grant;

/**
 * Pure candidate + hydration core. Node traversal may see partitions, but returned claim
 * content is selected only after the corrected graph query and policy partition filter.
 */
export const dogfoodCandidates = (request: DogfoodRequest, input: TreeInputSnapshot, renders: readonly RenderNode[]): { hydrated: readonly LiveClaimView[]; policy_omitted: number } => {
  // Traversal sees opaque matching partitions; selection below decides whether their claim
  // content can be returned. This permits the allowed policy-omission disclosure.
  const renderedIds = new Set(renders.filter((render) => render.status !== "failed" && matches(request.query, render.summary_text)).map((render) => render.node_id));
  const claimIds = new Set<string>();
  // Render node membership is deliberately not repeated in a summary; look up node ownership through renders' manifests.
  for (const render of renders) if (renderedIds.has(render.node_id)) for (const id of render.rendered_from_manifest.live_member_revisions) claimIds.add(id);
  const candidateClaims = input.claims.filter((claim) => claimIds.has(claim.claim_revision_id));
  const permitted = candidateClaims.filter((claim) => claim.placement_status === "canonical" && policyAllowed(claim, request.grant_class));
  return { hydrated: permitted, policy_omitted: candidateClaims.filter((claim) => claim.placement_status === "canonical" && !policyAllowed(claim, request.grant_class)).length };
};

export const retrieveDogfood = async (request: DogfoodRequest, graph: GraphSnapshot, input: TreeInputSnapshot, renders: readonly RenderNode[], model: ComposeModelPort, model_version = "fake-compose-v1"): Promise<DogfoodResponse> => {
  if (request.owner_account_id !== graph.owner_account_id || request.owner_account_id !== input.owner_account_id) throw new Error("dogfood owner does not match snapshot");
  const { hydrated: selected, policy_omitted } = dogfoodCandidates(request, input, renders);
  // Defense-in-depth: the B5 correction is applied even if a malformed tree contained a withheld member.
  const graphResult = request.entity_id
    ? retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "entity", entity_id: request.entity_id })
    : request.capture_session_id
      ? retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "source", capture_session_id: request.capture_session_id, include_provisional: true })
      : retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "as_of", date: request.as_of ?? "9999-12-31" });
  const eligible = new Set(graphResult.claims.filter((claim) => claim.status === "canonical").map((claim) => claim.revision_id));
  const hydrated = selected.filter((claim) => eligible.has(claim.claim_revision_id));
  if (!hydrated.length) return { answer_text: null, citations: [], hydrated_claim_revision_ids: [], absence: policy_omitted > 0 ? { kind: "policy_omission", grant_class: request.grant_class, message: "some matching memory is omitted by your grant class" } : { kind: "query_gap", message: "no cited memory matched" } };
  const spans = hydrated.flatMap((claim) => claim.evidence_spans).filter((span) => span.excerpt !== null);
  const permittedCitations = new Set(spans.map((span) => span.evidence_id));
  const composed = await model.compose({ strategy: "citation-grounded-compose", version: model_version, input: { query: request.query, evidence_spans: spans.map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt })) } });
  const citations = composed.citations.filter((citation) => permittedCitations.has(citation));
  return { answer_text: composed.answer_text, citations, hydrated_claim_revision_ids: hydrated.map((claim) => claim.claim_revision_id).sort(), absence: null };
};
