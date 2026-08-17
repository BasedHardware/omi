import { liveCommittedClaims, project, retrieveCommittedGraph, type GraphSnapshot, type LiveClaimView, type TreeInputSnapshot } from "./index";
import type { RequestContext } from "./grant";
import type { RenderNode } from "./render";

export interface DogfoodRequest {
  owner_account_id: string;
  query: string;
  entity_id?: string;
  as_of?: string;
  capture_session_id?: string;
  request_context: RequestContext;
}
export interface ComposeModelPort {
  compose(request: { strategy: string; version: string; input: unknown }): Promise<{
    answer_text: string;
    citations: readonly string[];
    /** The compose strategy must make every factual assertion addressable for grounding. */
    assertions: readonly { text: string; citations: readonly string[] }[];
  }>;
  /** Strategy-owned semantic judgment; core supplies only an assertion and cited spans. */
  invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>;
}
export type AbsenceDisclosure =
  | { kind: "query_gap"; message: "no cited memory matched" }
  | { kind: "policy_omission"; grant_class: string; message: "some matching memory is omitted by your grant class" };
export interface DogfoodResponse {
  answer_text: string | null;
  citations: readonly string[];
  /** Final assertion-local grounding after entailment. Empty for every non-grounded outcome. */
  assertions: readonly { text: string; citations: readonly string[] }[];
  hydrated_claim_revision_ids: readonly string[];
  absence: AbsenceDisclosure | null;
  grounding: { status: "grounded" } | { status: "ungrounded"; failures: readonly string[] } | null;
}

const words = (text: string) => text.toLocaleLowerCase().split(/[^\p{L}\p{N}_-]+/u).filter(Boolean);
const matches = (query: string, text: string | null) => {
  const qs = words(query); const haystack = new Set(words(text ?? ""));
  return qs.length > 0 && qs.some((word) => haystack.has(word));
};

/**
 * Grounding manifests are bookkeeping, not a content taxonomy: every sentence
 * emitted in the answer must have an exact, individually judged manifest row.
 * A conservative sentence splitter fails closed for text that the manifest did
 * not explicitly account for.
 */
const assertionUnits = (text: string): readonly string[] => text
  .split(/(?<=[.!?])\s+|\n+/u)
  .map((unit) => unit.trim())
  .filter(Boolean);
const normalizedAssertion = (text: string): string => text.trim().replace(/[.!?]+$/u, "").replace(/\s+/gu, " ").toLocaleLowerCase();

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
  // Authorization is deliberately not evaluated here. The composed answer gets
  // its permission boundary from `project`, the existing D46 projection.
  return { hydrated: candidateClaims.filter((claim) => claim.placement_status === "canonical"), policy_omitted: 0 };
};

export const retrieveDogfood = async (request: DogfoodRequest, graph: GraphSnapshot, input: TreeInputSnapshot, renders: readonly RenderNode[], model: ComposeModelPort, model_version = "fake-compose-v1"): Promise<DogfoodResponse> => {
  if (request.owner_account_id !== graph.owner_account_id || request.owner_account_id !== input.owner_account_id) throw new Error("dogfood owner does not match snapshot");
  const { hydrated: selected } = dogfoodCandidates(request, input, renders);
  // Defense-in-depth: the B5 correction is applied even if a malformed tree contained a provisional member.
  const graphResult = request.entity_id
    ? retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "entity", entity_id: request.entity_id, reader_context: request.request_context })
    : request.capture_session_id
      ? retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "source", capture_session_id: request.capture_session_id, include_provisional: true, reader_context: request.request_context })
      : retrieveCommittedGraph(graph, { owner_account_id: request.owner_account_id, kind: "as_of", date: request.as_of ?? "9999-12-31", reader_context: request.request_context });
  const safe = project(graph, request.request_context);
  const requestEligible = new Set(graphResult.claims.filter((claim) => claim.status === "canonical").map((claim) => claim.revision_id));
  const safeEligible = new Set(safe.claims.filter((claim) => claim.placement_status === "canonical").map((claim) => claim.revision_id));
  const eligible = new Set([...safeEligible].filter((revision_id) => requestEligible.has(revision_id)));
  const hydrated = selected.filter((claim) => eligible.has(claim.claim_revision_id));
  const allLive = new Set(liveCommittedClaims(graph).filter((claim) => claim.placement_status === "canonical").map((claim) => claim.revision_id));
  const policy_omitted = selected.some((claim) => allLive.has(claim.claim_revision_id) && !safeEligible.has(claim.claim_revision_id));
  if (!hydrated.length) return { answer_text: null, citations: [], assertions: [], hydrated_claim_revision_ids: [], absence: policy_omitted ? { kind: "policy_omission", grant_class: request.request_context.grant.grant_id, message: "some matching memory is omitted by your grant class" } : { kind: "query_gap", message: "no cited memory matched" }, grounding: null };
  const spans = hydrated.flatMap((claim) => claim.evidence_spans).filter((span) => span.excerpt !== null);
  const permittedCitations = new Set(spans.map((span) => span.evidence_id));
  const composed = await model.compose({ strategy: "citation-grounded-compose", version: model_version, input: { query: request.query, evidence_spans: spans.map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt })) } });
  const failures: string[] = [];
  const declaredAssertions = new Set(composed.assertions.map((assertion) => normalizedAssertion(assertion.text)).filter(Boolean));
  for (const unit of assertionUnits(composed.answer_text)) {
    if (!declaredAssertions.has(normalizedAssertion(unit))) failures.push(`answer assertion is absent from grounding manifest: ${unit}`);
  }
  // Each assertion is judged against only its own cited spans, so the checks
  // run concurrently; failures are applied in assertion order so the report
  // reads identically to a sequential pass.
  const judgments = await Promise.all(composed.assertions.map(async (assertion) => {
    const cited = assertion.citations.filter((citation) => permittedCitations.has(citation));
    if (!assertion.text || cited.length !== assertion.citations.length || cited.length === 0) return { kind: "uncited" as const };
    const cited_spans = spans.filter((span) => cited.includes(span.evidence_id)).map((span) => ({ evidence_id: span.evidence_id, excerpt: span.excerpt! }));
    return { kind: "judged" as const, judged: await model.invoke({ strategy: "span-entailment", version: "v1", input: { assertion: assertion.text, cited_spans } }) };
  }));
  composed.assertions.forEach((assertion, index) => {
    const outcome = judgments[index]!;
    if (outcome.kind === "uncited") { failures.push(`assertion lacks permitted cited span: ${assertion.text}`); return; }
    if (!(typeof outcome.judged === "object" && outcome.judged !== null && (outcome.judged as { entailed?: unknown }).entailed === true)) failures.push(`cited span does not entail assertion: ${assertion.text}`);
  });
  if (composed.answer_text && composed.assertions.length === 0) failures.push("non-empty answer has no asserted-claim grounding manifest");
  const citations = [...new Set(composed.citations.filter((citation) => permittedCitations.has(citation)))].sort();
  const hydrated_claim_revision_ids = hydrated.map((claim) => claim.claim_revision_id).sort();
  if (failures.length) return { answer_text: null, citations: [], assertions: [], hydrated_claim_revision_ids, absence: null, grounding: { status: "ungrounded", failures } };
  const assertions = composed.assertions.map((assertion) => ({
    text: assertion.text,
    citations: [...new Set(assertion.citations.filter((citation) => permittedCitations.has(citation)))].sort(),
  }));
  return { answer_text: composed.answer_text, citations, assertions, hydrated_claim_revision_ids, absence: null, grounding: { status: "grounded" } };
};
