import type { KnowledgeGraph, KGNode, KGEdge, RebuildResult } from '../../../shared/types'

type RawNode = { id: string; label?: string; node_type?: string; aliases?: string[]; memory_ids?: string[] }
type RawEdge = { id: string; source_id: string; target_id: string; label?: string; memory_ids?: string[] }
type RawGraph = { nodes?: RawNode[]; edges?: RawEdge[] }
type RawRebuild = { status?: string; nodes_count?: number; edges_count?: number }

export function mapGraphResponse(raw: RawGraph): KnowledgeGraph {
  const nodes: KGNode[] = (raw.nodes ?? []).map((n) => ({
    id: n.id,
    label: n.label ?? n.id,
    nodeType: n.node_type ?? 'concept',
    aliases: n.aliases ?? [],
    memoryIds: n.memory_ids ?? []
  }))
  const edges: KGEdge[] = (raw.edges ?? []).map((e) => ({
    id: e.id,
    sourceId: e.source_id,
    targetId: e.target_id,
    label: e.label ?? '',
    memoryIds: e.memory_ids ?? []
  }))
  return { nodes, edges }
}

export function mapRebuildResponse(raw: RawRebuild): RebuildResult {
  return { status: raw.status ?? 'unknown', nodesCount: raw.nodes_count ?? 0, edgesCount: raw.edges_count ?? 0 }
}
