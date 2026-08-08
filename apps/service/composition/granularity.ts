// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import type { RenderNode } from "../../../core/retrieve/render";
import type { StructuralTree } from "../../../core/retrieve/tree";

/**
 * Which synthesized nodes count as served memories.
 *
 * This is an EXPLICIT, NAMED parameter of the read - never an implicit default
 * of whichever transport happens to be serving. Two doors (the app-facing REST
 * binding and the MCP path) reach the same read, and they independently chose
 * different granularities: leaves-only here, rollups-and-leaves there. A query
 * that returns different results depending on which transport answered it does
 * not stay a backend detail; it becomes visible the first time an agent and a
 * person disagree about "the same" memories, and by then two client generations
 * depend on both behaviours.
 *
 * So the caller states the granularity, and both doors must return the same
 * items when given the same one. When David rules, the default changes in one
 * place instead of one implementation being rewritten.
 *
 * The vocabulary here is unratified - `leaf`, `rollup` and "memory" are all
 * pending naming decisions.
 */
// domain-pending(DIV-DOMCORE-008)
export type MemoryReadGranularity =
  /**
   * Only the deepest temporal grouping - one synthesized memory per local day.
   * The right default for a product surface: a person scrolling their memories
   * does not want "2026" and "August 2026" as separate entries.
   */
  | "synthesized_temporal_leaf"
  /**
   * Every ready synthesized node, rollups included. Useful to an agent that
   * wants the hierarchy, and it is what the MCP path selected independently.
   */
  | "synthesized_all_nodes";

/**
 * The app-facing default. Stated here rather than inlined at the route so the
 * choice is one named constant, not a property of the handler that is running.
 */
// domain-pending(DIV-DOMCORE-008)
export const DEFAULT_APP_FACING_MEMORY_READ_GRANULARITY: MemoryReadGranularity =
  "synthesized_temporal_leaf";

/** The temporal view is the hierarchical one: year -> month -> day. */
const TEMPORAL_VIEW_KIND = "temporal";

/**
 * A render is servable only if it is grounded and current. An empty, failed or
 * stale render is not a memory - and presenting one as absence would be a lie.
 */
const isServable = (render: RenderNode): boolean =>
  render.status === "ready"
  && render.render_hash !== null
  && render.summary_text !== null
  && render.summary_text.length > 0
  && !render.stale
  && render.citations.length > 0;

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

/**
 * Applies a granularity to a produced render set.
 *
 * Both doors are expected to call THIS function so the selection cannot drift.
 * Ordering is by node id, which is deterministic and host-independent; it makes
 * no production ranking claim, exactly as the recall core says of its own.
 */
export const selectRendersForGranularity = (
  renders: readonly RenderNode[],
  tree: StructuralTree,
  granularity: MemoryReadGranularity,
): readonly RenderNode[] => {
  const nodesById = new Map(tree.nodes.map((node) => [node.node_id, node]));
  const servable = renders.filter(isServable);
  const selected = granularity === "synthesized_all_nodes"
    ? servable
    : servable.filter((render) => {
      const node = nodesById.get(render.node_id);
      return node !== undefined
        && (node.view_kind as string) === TEMPORAL_VIEW_KIND
        && node.child_node_ids.length === 0;
    });
  return Object.freeze([...selected].sort((left, right) =>
    compareStrings(left.node_id, right.node_id)));
};
