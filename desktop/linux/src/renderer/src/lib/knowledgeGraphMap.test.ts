import { describe, it, expect } from 'vitest'
import { mapGraphResponse, mapRebuildResponse } from './knowledgeGraphMap'

describe('mapGraphResponse', () => {
  it('maps snake_case nodes and edges to camelCase', () => {
    const raw = {
      nodes: [{ id: 'n1', label: 'Alice', node_type: 'person', aliases: ['Al'], memory_ids: ['m1', 'm2'] }],
      edges: [{ id: 'e1', source_id: 'n1', target_id: 'n2', label: 'knows', memory_ids: ['m1'] }]
    }
    const g = mapGraphResponse(raw)
    expect(g.nodes[0]).toEqual({ id: 'n1', label: 'Alice', nodeType: 'person', aliases: ['Al'], memoryIds: ['m1', 'm2'] })
    expect(g.edges[0]).toEqual({ id: 'e1', sourceId: 'n1', targetId: 'n2', label: 'knows', memoryIds: ['m1'] })
  })

  it('defaults missing arrays and node_type, and tolerates absent nodes/edges', () => {
    const g = mapGraphResponse({ nodes: [{ id: 'n1', label: 'X' }] })
    expect(g.nodes[0]).toEqual({ id: 'n1', label: 'X', nodeType: 'concept', aliases: [], memoryIds: [] })
    expect(g.edges).toEqual([])
  })

  it('falls back to node id when label is absent', () => {
    const g = mapGraphResponse({ nodes: [{ id: 'n9' }] })
    expect(g.nodes[0].label).toBe('n9')
  })

  it('defaults edge label to empty string when absent', () => {
    const g = mapGraphResponse({ edges: [{ id: 'e1', source_id: 'n1', target_id: 'n2' }] })
    expect(g.edges[0].label).toBe('')
  })
})

describe('mapRebuildResponse', () => {
  it('maps counts', () => {
    expect(mapRebuildResponse({ status: 'ok', nodes_count: 3, edges_count: 5 }))
      .toEqual({ status: 'ok', nodesCount: 3, edgesCount: 5 })
  })
})
