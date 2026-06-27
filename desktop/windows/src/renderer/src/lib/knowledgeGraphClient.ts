import { omiApi } from './apiClient'
import { mapGraphResponse, mapRebuildResponse } from './knowledgeGraphMap'
import type { KnowledgeGraph, RebuildResult } from '../../../shared/types'

export async function fetchKnowledgeGraph(): Promise<KnowledgeGraph> {
  const r = await omiApi.get('/v1/knowledge-graph')
  return mapGraphResponse(r.data)
}

// Server-side background rebuild from up to 500 memories. Rate-limited.
export async function rebuildKnowledgeGraph(): Promise<RebuildResult> {
  const r = await omiApi.post('/v1/knowledge-graph/rebuild')
  return mapRebuildResponse(r.data)
}

// Exported for a later milestone (delete-graph UI); intentionally unused in Milestone A.
export async function deleteKnowledgeGraph(): Promise<void> {
  await omiApi.delete('/v1/knowledge-graph')
}
