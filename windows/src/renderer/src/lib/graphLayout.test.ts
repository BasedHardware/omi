import { describe, it, expect } from 'vitest'
import { computeLayout } from './graphLayout'
import type { KnowledgeGraph } from '../../../shared/types'

const graph: KnowledgeGraph = {
  nodes: [
    { id: 'a', label: 'A', nodeType: 'person', aliases: [], memoryIds: [] },
    { id: 'b', label: 'B', nodeType: 'concept', aliases: [], memoryIds: [] },
    { id: 'c', label: 'C', nodeType: 'concept', aliases: [], memoryIds: [] }
  ],
  edges: [
    { id: 'e1', sourceId: 'a', targetId: 'b', label: '', memoryIds: [] },
    { id: 'e2', sourceId: 'a', targetId: 'c', label: '', memoryIds: [] }
  ]
}

describe('computeLayout', () => {
  it('gives every node a finite position', () => {
    const out = computeLayout(graph, { iterations: 50, width: 800, height: 600 })
    for (const n of out.nodes) {
      expect(Number.isFinite(n.x)).toBe(true)
      expect(Number.isFinite(n.y)).toBe(true)
    }
  })

  it('computes degree from edges', () => {
    const out = computeLayout(graph, { iterations: 10, width: 800, height: 600 })
    const byId = Object.fromEntries(out.nodes.map((n) => [n.id, n.degree]))
    expect(byId.a).toBe(2)
    expect(byId.b).toBe(1)
    expect(byId.c).toBe(1)
  })

  it('is deterministic across runs', () => {
    const a = computeLayout(graph, { iterations: 50, width: 800, height: 600 })
    const b = computeLayout(graph, { iterations: 50, width: 800, height: 600 })
    expect(a.nodes.map((n) => [n.id, n.x, n.y])).toEqual(b.nodes.map((n) => [n.id, n.x, n.y]))
  })

  it('does not mutate the input graph nodes', () => {
    const before = JSON.stringify(graph.nodes)
    computeLayout(graph, { iterations: 10, width: 800, height: 600 })
    expect(JSON.stringify(graph.nodes)).toEqual(before)
  })

  it('counts a self-loop edge once', () => {
    const out = computeLayout(
      {
        nodes: [{ id: 'x', label: 'X', nodeType: 'concept', aliases: [], memoryIds: [] }],
        edges: [{ id: 'e', sourceId: 'x', targetId: 'x', label: '', memoryIds: [] }]
      },
      { iterations: 5 }
    )
    expect(out.nodes[0].degree).toBe(1)
  })
})
