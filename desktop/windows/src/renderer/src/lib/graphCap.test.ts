import { describe, it, expect } from 'vitest'
import { capGraphToMostConnected, starGraphToCenter } from './graphCap'
import type { KnowledgeGraph } from '../../../shared/types'

const node = (id: string): KnowledgeGraph['nodes'][number] => ({
  id,
  label: id,
  nodeType: 'concept',
  aliases: [],
  memoryIds: []
})
const edge = (a: string, b: string): KnowledgeGraph['edges'][number] => ({
  id: `${a}-${b}`,
  sourceId: a,
  targetId: b,
  label: '',
  memoryIds: []
})

describe('capGraphToMostConnected', () => {
  it('returns the graph unchanged when it is already within the cap', () => {
    const g: KnowledgeGraph = { nodes: [node('a'), node('b')], edges: [edge('a', 'b')] }
    expect(capGraphToMostConnected(g, undefined, 10)).toEqual(g)
  })

  it('keeps the most-connected nodes and drops the long tail', () => {
    // hub connects to x,y,z; lonely connects to nothing.
    const g: KnowledgeGraph = {
      nodes: ['hub', 'x', 'y', 'z', 'lonely'].map(node),
      edges: [edge('hub', 'x'), edge('hub', 'y'), edge('hub', 'z')]
    }
    const out = capGraphToMostConnected(g, undefined, 4)
    const ids = out.nodes.map((n) => n.id)
    expect(ids).toContain('hub')
    expect(ids).not.toContain('lonely') // lowest degree dropped
    expect(out.nodes).toHaveLength(4)
  })

  it('always keeps the center node even if it is low-degree', () => {
    const g: KnowledgeGraph = {
      nodes: ['hub', 'x', 'y', 'z', 'me'].map(node),
      edges: [edge('hub', 'x'), edge('hub', 'y'), edge('hub', 'z')]
    }
    const out = capGraphToMostConnected(g, 'me', 3)
    const ids = out.nodes.map((n) => n.id)
    expect(ids).toContain('me')
    expect(out.nodes).toHaveLength(3)
  })

  it('drops edges whose endpoints were removed', () => {
    const g: KnowledgeGraph = {
      nodes: ['hub', 'x', 'y', 'z', 'lonely'].map(node),
      edges: [edge('hub', 'x'), edge('hub', 'lonely')]
    }
    const out = capGraphToMostConnected(g, undefined, 3)
    const keptIds = new Set(out.nodes.map((n) => n.id))
    for (const e of out.edges) {
      expect(keptIds.has(e.sourceId)).toBe(true)
      expect(keptIds.has(e.targetId)).toBe(true)
    }
  })
})

describe('starGraphToCenter', () => {
  it('returns the graph unchanged when the center is absent or undefined', () => {
    const g: KnowledgeGraph = { nodes: [node('a'), node('b')], edges: [edge('a', 'b')] }
    expect(starGraphToCenter(g, undefined)).toEqual(g)
    expect(starGraphToCenter(g, 'missing')).toEqual(g)
  })

  it('connects every other node directly to the center and drops inter-node edges', () => {
    // me is the center; a-b and b-c are inter-node edges that must be replaced.
    const g: KnowledgeGraph = {
      nodes: ['me', 'a', 'b', 'c'].map(node),
      edges: [edge('a', 'b'), edge('b', 'c')]
    }
    const out = starGraphToCenter(g, 'me')
    // One spoke per non-center node, every edge rooted at the center.
    expect(out.edges).toHaveLength(3)
    expect(out.edges.every((e) => e.sourceId === 'me')).toBe(true)
    expect(new Set(out.edges.map((e) => e.targetId))).toEqual(new Set(['a', 'b', 'c']))
  })

  it('leaves the nodes untouched', () => {
    const g: KnowledgeGraph = { nodes: ['me', 'a'].map(node), edges: [] }
    expect(starGraphToCenter(g, 'me').nodes).toEqual(g.nodes)
  })

  it('produces no edges when the center is the only node', () => {
    const g: KnowledgeGraph = { nodes: [node('me')], edges: [] }
    expect(starGraphToCenter(g, 'me').edges).toHaveLength(0)
  })
})
