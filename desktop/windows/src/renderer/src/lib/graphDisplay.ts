import type { KnowledgeGraph, KGNode } from '../../../shared/types'

// Pure, framework-free display logic for the brain map: importance ranking, the
// default node cap (with a full-graph escape hatch), and which nodes show a
// label. Extracted from the renderer so it is unit-testable in node and so the
// cap/label rules are one source of truth for the viewer and its tests.
//
// The server knowledge graph carries no per-node importance or timestamp (see
// KGNode: id/label/nodeType/aliases/memoryIds only), so "importance" is derived:
// connection count (degree) first — the structural hubs — then how many memories
// reference the node (a salience/recency proxy), then id for a stable tiebreak.

/** Undirected connection count per node id. Self-loops count once. */
export function nodeDegrees(graph: KnowledgeGraph): Map<string, number> {
  const deg = new Map<string, number>()
  for (const n of graph.nodes) deg.set(n.id, 0)
  for (const e of graph.edges) {
    if (deg.has(e.sourceId)) deg.set(e.sourceId, (deg.get(e.sourceId) ?? 0) + 1)
    if (e.targetId !== e.sourceId && deg.has(e.targetId))
      deg.set(e.targetId, (deg.get(e.targetId) ?? 0) + 1)
  }
  return deg
}

// Nodes ordered most→least important. The center ("you") node, when present,
// always sorts first so no cap can ever drop it. Otherwise: degree desc, then
// memory count desc, then id asc (stable, deterministic — required so the cap and
// the tests agree run to run).
export function rankNodes(graph: KnowledgeGraph, centerNodeId?: string): KGNode[] {
  const deg = nodeDegrees(graph)
  return [...graph.nodes].sort((a, b) => {
    if (a.id === centerNodeId) return b.id === centerNodeId ? 0 : -1
    if (b.id === centerNodeId) return 1
    const da = deg.get(a.id) ?? 0
    const db = deg.get(b.id) ?? 0
    if (db !== da) return db - da
    const ma = a.memoryIds?.length ?? 0
    const mb = b.memoryIds?.length ?? 0
    if (mb !== ma) return mb - ma
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  })
}

// Restrict the graph to its `cap` most important nodes, pruning any edge whose
// endpoints didn't both survive. A non-positive, non-finite, or >= node-count cap
// returns the graph UNCHANGED (same object ref) — that is the "show all" path, so
// the full graph always stays reachable and correct.
export function capGraph(
  graph: KnowledgeGraph,
  cap: number,
  centerNodeId?: string
): KnowledgeGraph {
  if (!Number.isFinite(cap) || cap <= 0 || cap >= graph.nodes.length) return graph
  const keep = new Set(
    rankNodes(graph, centerNodeId)
      .slice(0, cap)
      .map((n) => n.id)
  )
  return {
    nodes: graph.nodes.filter((n) => keep.has(n.id)),
    edges: graph.edges.filter((e) => keep.has(e.sourceId) && keep.has(e.targetId))
  }
}

/** True when `cap` would actually hide nodes (i.e. a "Show all" control is useful). */
export function isCapped(graph: KnowledgeGraph, cap: number): boolean {
  return Number.isFinite(cap) && cap > 0 && cap < graph.nodes.length
}

// The node ids whose labels should render. Declutter kills the "text soup" by
// labeling only the `topK` most important nodes plus, always, the center, the
// hovered node, and the selected node — so every node still names itself the
// instant you point at or pick it, but the idle scene stays legible.
export function labeledNodeIds(
  graph: KnowledgeGraph,
  topK: number,
  opts: { centerNodeId?: string; hoveredId?: string | null; selectedId?: string | null } = {}
): Set<string> {
  const ids = new Set<string>()
  const ranked = rankNodes(graph, opts.centerNodeId)
  for (let i = 0; i < Math.min(Math.max(0, topK), ranked.length); i++) ids.add(ranked[i].id)
  if (opts.centerNodeId) ids.add(opts.centerNodeId)
  if (opts.hoveredId) ids.add(opts.hoveredId)
  if (opts.selectedId) ids.add(opts.selectedId)
  return ids
}

// Default view parameters, justified by the measured real-account graph
// (188 nodes / 474 edges; one 226-degree hub, ~40% of nodes are degree-1 leaves).
// DEFAULT_NODE_CAP keeps the connected core and drops the long tail of
// single-connection leaves that add clutter but no structure; the full graph is
// always one click away. DEFAULT_LABEL_TOPK keeps the scene oriented (the biggest
// hubs stay named) without the 188-label soup.
export const DEFAULT_NODE_CAP = 120
export const DEFAULT_LABEL_TOPK = 20
