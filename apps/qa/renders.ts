// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMX-005)
import type { ApplicationGrantProjectedTreeInputSnapshot } from "../../core/retrieve/authorization-boundary";
import {
  DEFAULT_READ_ITEM_GRANULARITY,
  selectNodesForGranularity,
  type ReadItemGranularity,
} from "../../core/retrieve/granularity";
import { renderStructuralTree, type RenderNode } from "../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";

/**
 * Hermetic QA render production. No model is called: the "synthesis" is a pure
 * function of the structural node, so the same projection always yields the same
 * render hashes on any host.
 *
 * This makes no production synthesis-policy claim. It exists so the rest of the
 * flow can be exercised against genuinely produced, module-branded RenderNodes
 * rather than fabricated lookalikes — the projection boundary rejects anything
 * that did not come out of `renderStructuralTree`.
 */

export const QA_RENDER_MODEL_VERSION = "qa-deterministic-render-v1";

export const QA_RENDER_OPTIONS = Object.freeze({
  strategy: "qa-application-read",
  model_version: QA_RENDER_MODEL_VERSION,
  prompt_version: "qa-prompt-v1",
  policy_version: "qa-policy-v1",
  schema_version: "qa-schema-v1",
});

interface RenderRequestInput {
  readonly node: { readonly node_id: string };
  readonly claims: readonly {
    readonly claim_revision_id: string;
    readonly evidence_refs: readonly string[];
  }[];
}

/**
 * The citation set is not decorative: `buildOwnerBoundSynthesizedProjection`
 * requires the render's citations to be exactly the sorted unique evidence ids
 * of the node's live member claims, and rejects the render otherwise.
 */
const citationsFor = (claims: RenderRequestInput["claims"]): readonly string[] =>
  [...new Set(claims.flatMap((claim) => [...claim.evidence_refs]))].sort();

/**
 * Deterministic surface text. It is derived from structural identity only, so it
 * carries no excerpt, payload, or source content into the synthesized wire text.
 */
const summaryFor = (input: RenderRequestInput): string => {
  const members = [...input.claims.map((claim) => claim.claim_revision_id)].sort();
  return `QA synthesized proposition ${input.node.node_id} over ${members.length} claim(s)`;
};

/**
 * Produces the branded render set for one authorized projection.
 *
 * Rendering the same projection twice returns structurally identical renders
 * with identical `render_hash` values, which is what lets the application read
 * revalidate its produced-render receipt without re-deriving the page.
 */
export const produceQaRenders = async (
  projected: ApplicationGrantProjectedTreeInputSnapshot,
  granularity: ReadItemGranularity = DEFAULT_READ_ITEM_GRANULARITY,
): Promise<readonly RenderNode[]> => {
  const tree = buildDeterministicAnchors(projected);
  // Render the WHOLE tree, then select. Rollup renders depend on their children
  // (`child_render_hashes`), so rendering a pruned tree would either fail
  // provenance validation or silently change a surviving node's render hash --
  // which would make the two granularities disagree about the bytes of an item
  // they both contain. Selection is a projection concern, not a render concern.
  const selected = new Set(
    selectNodesForGranularity(tree.nodes, granularity).map((node) => node.node_id),
  );
  const renders = await renderStructuralTree(tree, projected, {
    render: async (request) => {
      const input = request.input as RenderRequestInput;
      return {
        summary_text: summaryFor(input),
        citations: citationsFor(input.claims),
      };
    },
  }, QA_RENDER_OPTIONS);

  // Only "ready" renders carry a summary and a render hash. An empty or failed
  // render has no synthesized projection to publish, and the projection boundary
  // would deny it; drop it here rather than let it surface as an opaque failure.
  return Object.freeze(renders.filter((render) =>
    selected.has(render.node_id)
    && render.status === "ready"
    && render.render_hash !== null
    && render.summary_text !== null
    && render.summary_text.length > 0
    && !render.stale
    && render.citations.length > 0));
};
