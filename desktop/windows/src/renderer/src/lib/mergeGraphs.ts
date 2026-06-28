import type { KnowledgeGraph } from '../../../shared/types'

// Union two knowledge graphs by node/edge id. `base` takes precedence on id
// collisions, so the onboarding floor (the "you" identity, language, apps) is
// never overwritten by the server graph layered on top. Dangling edges (whose
// endpoints aren't present) are left in place — the renderer/simulation only
// draws edges whose endpoints both exist, so they're harmless.
export function mergeGraphs(base: KnowledgeGraph, overlay: KnowledgeGraph): KnowledgeGraph {
  const nodeIds = new Set(base.nodes.map((n) => n.id))
  const edgeIds = new Set(base.edges.map((e) => e.id))
  return {
    nodes: [...base.nodes, ...overlay.nodes.filter((n) => !nodeIds.has(n.id))],
    edges: [...base.edges, ...overlay.edges.filter((e) => !edgeIds.has(e.id))]
  }
}

// Restrict a server KG to the entities tied to a specific set of memories. The
// server graph is account-wide (every entity it ever extracted, from a snapshot
// built off up to 500 memories), so layering it whole shows nodes that don't
// correspond to the memories the user actually has — including phantom nodes
// left behind by deleted memories. Each node/edge carries the memoryIds it was
// derived from, so we keep only those that reference a CURRENT memory, then drop
// any edge whose endpoints didn't survive. Nodes with no memoryIds (untagged
// hubs) are dropped too — if nothing ties them to a memory, they don't belong on
// a memory-scoped map.
export function scopeGraphToMemories(
  graph: KnowledgeGraph,
  memoryIds: Set<string>
): KnowledgeGraph {
  const nodes = graph.nodes.filter((n) => n.memoryIds.some((id) => memoryIds.has(id)))
  const kept = new Set(nodes.map((n) => n.id))
  const edges = graph.edges.filter((e) => kept.has(e.sourceId) && kept.has(e.targetId))
  return { nodes, edges }
}
