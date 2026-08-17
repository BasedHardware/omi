// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMX-005)
import type { ApplicationGrantProjectedTreeInputSnapshot } from "../../core/retrieve/authorization-boundary";
import { renderStructuralTree, type RenderNode } from "../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { createQaDeterministicSynthesizer } from "./synthesizer";

/**
 * QA render production — **granularity-agnostic on purpose**.
 *
 * This used to apply the granularity filter internally, and that was wrong in a
 * way that only showed up once both doors existed: a caller asking for
 * `synthesized_all_nodes` could never get them, because production had already
 * discarded the rollups. The REST door produced 17 nodes and this produced 5, so
 * the two doors could not agree on the same read no matter what the shared
 * selector did.
 *
 * The whole tree is rendered and the caller selects afterwards, via the SHARED
 * selector. Two reasons, and the second is the load-bearing one:
 *
 *  1. Rollup renders depend on `child_render_hashes`, so rendering a pruned tree
 *     changes a surviving node's render hash — the granularities would then
 *     disagree about the bytes of an item they both contain.
 *  2. Selection is a read-parameter concern, not a production concern. Keeping
 *     it out of production is what makes "identical granularity ⇒ identical
 *     items" achievable across doors at all.
 */

export const QA_RENDER_MODEL_VERSION = "qa-deterministic-synthesizer-v1";

/**
 * Render options shared by both doors.
 *
 * These MUST match the REST composition's options exactly. `model_version` is
 * hashed into `render_hash`, which is hashed into the candidate ref, which is
 * keyed into the public item id — so a single differing character here makes
 * item-for-item identity between the doors impossible, while node-level
 * agreement still passes and hides it.
 */
export const QA_RENDER_OPTIONS = Object.freeze({
  strategy: "application-read-qa",
  model_version: QA_RENDER_MODEL_VERSION,
  prompt_version: "qa-prompt-v1",
  policy_version: "qa-policy-v1",
  schema_version: "qa-schema-v1",
});

/**
 * A render is servable only if it is grounded and current. An empty, failed or
 * stale render is not a memory, and presenting one as absence would be a lie.
 *
 * Deliberately the same predicate the shared selector applies, so a render this
 * function returns is never silently dropped later for a different reason.
 */
export const isServableRender = (render: RenderNode): boolean =>
  render.status === "ready"
  && render.render_hash !== null
  && render.summary_text !== null
  && render.summary_text.length > 0
  && !render.stale
  && render.citations.length > 0;

/**
 * Produces the branded render set for one authorized projection — every node of
 * the tree, unfiltered.
 *
 * Renders really do come out of `renderStructuralTree`: the projection boundary
 * rejects anything not in its produced-render WeakSet, so a fabricated lookalike
 * cannot reach the wire.
 */
export const produceQaRenders = async (
  projected: ApplicationGrantProjectedTreeInputSnapshot,
): Promise<readonly RenderNode[]> => {
  const tree = buildDeterministicAnchors(projected);
  const renders = await renderStructuralTree(
    tree,
    projected,
    createQaDeterministicSynthesizer(),
    QA_RENDER_OPTIONS,
  );
  return Object.freeze(renders.filter(isServableRender));
};
