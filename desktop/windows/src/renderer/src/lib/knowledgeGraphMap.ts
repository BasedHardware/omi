import type { KnowledgeGraph, KGNode, KGEdge, RebuildResult } from '../../../shared/types'
import type { KnowledgeGraphResponse } from './omiApi.generated'

type RawNode = { id: string; label?: string; node_type?: string; aliases?: string[]; memory_ids?: string[] }
type RawEdge = { id: string; source_id: string; target_id: string; label?: string; memory_ids?: string[] }
type RawRebuild = { status?: string; nodes_count?: number; edges_count?: number }

export function mapGraphResponse(raw: KnowledgeGraphResponse): KnowledgeGraph {
  const nodes: KGNode[] = (raw.nodes ?? []).map((rec) => {
    const n = rec as unknown as RawNode
    return {
      id: n.id,
      label: n.label ?? n.id,
      nodeType: n.node_type ?? 'concept',
      aliases: n.aliases ?? [],
      memoryIds: n.memory_ids ?? []
    }
  })
  const edges: KGEdge[] = (raw.edges ?? []).map((rec) => {
    const e = rec as unknown as RawEdge
    return {
      id: e.id,
      sourceId: e.source_id,
      targetId: e.target_id,
      label: e.label ?? '',
      memoryIds: e.memory_ids ?? []
    }
  })
  return { nodes, edges }
}

export function mapRebuildResponse(raw: RawRebuild): RebuildResult {
  return { status: raw.status ?? 'unknown', nodesCount: raw.nodes_count ?? 0, edgesCount: raw.edges_count ?? 0 }
}
