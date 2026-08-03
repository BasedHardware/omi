import type { Database } from "bun:sqlite";
import { projectTreeInputSnapshot } from "../core/retrieve";
import { retrieveDogfood, type ComposeModelPort, type DogfoodResponse } from "../core/retrieve/dogfood";
import { renderStructuralTree, type RenderModelPort } from "../core/retrieve/render";
import { buildDeterministicAnchors } from "../core/retrieve/tree";
import { SqliteLedger } from "../drivers/sqlite";

/** The owner-facing recall path needs both halves of R0-R4: node summaries are what a
 * question is matched against, and the composed answer is what the owner reads. */
export interface RecallModelPort extends RenderModelPort, ComposeModelPort {}
export interface CitedSpan { evidence_id: string; excerpt: string | null; capture_session_id: string }
export interface RecallAnswer extends DogfoodResponse {
  /** UI provenance for each returned citation, resolved from the same snapshot the answer came from. */
  cited_spans: readonly CitedSpan[];
}
export interface RecallRequest {
  db: Database;
  owner_account_id: string;
  query: string;
  model: RecallModelPort;
  as_of?: string;
  account_timezone?: string;
  /** Render identity is versioned by the caller: the port does not name the model behind it. */
  model_version?: string;
}

export const answerQuestion = async (request: RecallRequest): Promise<RecallAnswer> => {
  const graph = new SqliteLedger(request.db).snapshot(request.owner_account_id);
  const input = projectTreeInputSnapshot(graph, { account_timezone: request.account_timezone ?? "UTC" });
  const model_version = request.model_version ?? "unspecified";
  // The retrieval tree is rebuilt per question rather than cached: `renderStructuralTree`
  // takes a cache keyed by the render digest, and this harness has nowhere durable to keep one.
  const renders = await renderStructuralTree(buildDeterministicAnchors(input), input, request.model, {
    strategy: "retrieval-node-summary", model_version, prompt_version: "retrieval-node-summary-v1", policy_version: input.classifier_version, schema_version: "retrieval-v1",
  });
  // The owner reads their own graph: an empty policy-class grant is the whole-graph
  // grant for them and authorizes nothing for anyone else.
  const response = await retrieveDogfood({
    owner_account_id: request.owner_account_id, query: request.query, as_of: request.as_of,
    request_context: { reader_account_id: request.owner_account_id, grant: { grant_id: "owner-recall", policy_classes: [] } },
  }, graph, input, renders, request.model, model_version);
  const spanById = new Map(input.evidence_index.map((span) => [span.evidence_id, span]));
  return { ...response, cited_spans: response.citations.flatMap((evidence_id) => {
    const span = spanById.get(evidence_id);
    return span ? [{ evidence_id, excerpt: span.excerpt, capture_session_id: span.capture_session_id }] : [];
  }) };
};
