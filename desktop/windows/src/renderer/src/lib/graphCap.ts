import type { KnowledgeGraph } from '../../../shared/types'

// Limit a knowledge graph to its most-connected nodes so the 3D brain map stays
// fast. With hundreds of memories the scoped server KG can have many hundreds of
// nodes; rendering them all (each a sphere + a label) blocks the main thread on
// mount. We keep the `max` best-connected nodes — the center node always
// included — and drop any edge whose endpoint was removed. The hidden long tail
// is still fully present in the memory list below the map.
export function capGraphToMostConnected(
  graph: KnowledgeGraph,
  centerNodeId: string | undefined,
  max: number
): KnowledgeGraph {
  if (graph.nodes.length <= max) return graph

  const degree = new Map<string, number>()
  for (const n of graph.nodes) degree.set(n.id, 0)
  for (const e of graph.edges) {
    if (degree.has(e.sourceId)) degree.set(e.sourceId, (degree.get(e.sourceId) ?? 0) + 1)
    if (e.targetId !== e.sourceId && degree.has(e.targetId)) {
      degree.set(e.targetId, (degree.get(e.targetId) ?? 0) + 1)
    }
  }

  // Center is pinned in; rank the rest by degree (desc) and take what's left.
  const center = centerNodeId ? graph.nodes.find((n) => n.id === centerNodeId) : undefined
  const rest = graph.nodes
    .filter((n) => n.id !== center?.id)
    .sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0))

  const keepCount = center ? max - 1 : max
  const kept = [...(center ? [center] : []), ...rest.slice(0, Math.max(0, keepCount))]
  const keptIds = new Set(kept.map((n) => n.id))

  return {
    nodes: kept,
    edges: graph.edges.filter((e) => keptIds.has(e.sourceId) && keptIds.has(e.targetId))
  }
}

// Spoke-edge id prefix, so these synthetic "to the center" links are
// recognisable versus real knowledge-graph edges.
const STAR_PREFIX = '__star__'

// Collapse the graph to a STAR around the central node, matching the macOS
// brain map: drop every inter-node edge and connect each remaining node
// directly to the center with a single spoke. Nodes are untouched (the cap
// already chose which to keep, by real connectivity); only the rendered edges
// change. A no-op when there's no center node to hub around.
export function starGraphToCenter(
  graph: KnowledgeGraph,
  centerNodeId: string | undefined
): KnowledgeGraph {
  if (!centerNodeId || !graph.nodes.some((n) => n.id === centerNodeId)) return graph

  const edges = graph.nodes
    .filter((n) => n.id !== centerNodeId)
    .map((n) => ({
      id: `${STAR_PREFIX}:${centerNodeId}:${n.id}`,
      sourceId: centerNodeId,
      targetId: n.id,
      label: '',
      memoryIds: []
    }))

  return { nodes: graph.nodes, edges }
}
