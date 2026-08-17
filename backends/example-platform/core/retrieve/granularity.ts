// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMX-002)
import type { StructuralNode, StructuralTree } from "./tree";

/**
 * Item granularity for the synthesized read.
 *
 * Provisional coordinator ruling, 2026-08-08
 * (`decisions/COORD-item-granularity.md`, REVIEW OWED FROM DAVID):
 *
 *   Item granularity is an EXPLICIT, NAMED PARAMETER of the read — not an
 *   implicit default of the transport.
 *
 * The temporal view is a year/month/day hierarchy, so rollup nodes and leaf
 * nodes both present themselves as candidate items. Two lanes independently
 * chose differently (MCP served rollups and leaves, 12 items for 5 claims; the
 * app REST path served leaves only). Left per-transport, the same query returns
 * different results depending on which door the caller came through — which
 * becomes permanent the first time an agent and a user disagree about "the
 * same" memories.
 *
 * So both surfaces pass this explicitly. Neither hard-codes it and neither
 * infers it from which transport is serving. When David rules, the ruling
 * changes a default in one place instead of rewriting a lane.
 *
 * The NAME of this parameter is unratified vocabulary like everything else in
 * the naming freeze — hence the markers above.
 */
// domain-pending(DIV-DOMCORE-008): "granularity" is a placeholder term.
export type ReadItemGranularity =
  /**
   * Deepest temporal grouping only — one item per local day. The app-facing
   * default: a person scrolling their memories does not want "2026" and
   * "August 2026" as entries.
   */
  | "temporal_leaf"
  /**
   * Every produced structural node: temporal rollups and leaves, plus entity
   * and source views. An agent consumer has a real use for rollups; it has to
   * ask for them rather than receive them by accident of routing.
   */
  | "all_nodes";

/**
 * The default for every surface, per the ruling. A transport that wants the
 * hierarchy must name it; nothing receives rollups by omission.
 */
export const DEFAULT_READ_ITEM_GRANULARITY: ReadItemGranularity = "temporal_leaf";

export const READ_ITEM_GRANULARITIES: readonly ReadItemGranularity[] =
  Object.freeze(["temporal_leaf", "all_nodes"]);

export const isReadItemGranularity = (value: unknown): value is ReadItemGranularity =>
  typeof value === "string" && (READ_ITEM_GRANULARITIES as readonly string[]).includes(value);

/**
 * A temporal leaf is a temporal node with no temporal child.
 *
 * Deliberately computed from the node's own `child_node_ids` rather than from
 * an anchor-key depth heuristic (counting `/` separators in `year/month/day`).
 * The anchor-key shape is an implementation detail of
 * `buildDeterministicAnchors`; child linkage is the structural fact. A depth
 * heuristic would also silently misclassify if the temporal hierarchy ever
 * gained or lost a level.
 */
const isTemporalLeaf = (node: StructuralNode): boolean =>
  node.view_kind === "temporal" && node.child_node_ids.length === 0;

/**
 * Selects the structural nodes that become wire items at a given granularity.
 *
 * Pure and transport-neutral: it takes nodes and a stated granularity, and knows
 * nothing about HTTP, MCP, storage, or authorization. Order is preserved exactly
 * as supplied — this selects, it never reorders, because ordering authority
 * lives in the recall kernel and must not be duplicated here.
 */
export const selectNodesForGranularity = (
  nodes: readonly StructuralNode[],
  granularity: ReadItemGranularity,
): readonly StructuralNode[] => {
  if (granularity === "all_nodes") return Object.freeze([...nodes]);
  return Object.freeze(nodes.filter(isTemporalLeaf));
};

export const selectTreeNodesForGranularity = (
  tree: StructuralTree,
  granularity: ReadItemGranularity,
): readonly StructuralNode[] => selectNodesForGranularity(tree.nodes, granularity);
