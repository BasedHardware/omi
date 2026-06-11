import { describe, it, expect } from 'vitest'
import { mergeGraphs, scopeGraphToMemories } from './mergeGraphs'
import type { KnowledgeGraph, KGNode, KGEdge } from '../../../shared/types'

const node = (id: string, over: Partial<KGNode> = {}): KGNode => ({
  id,
  label: id,
  nodeType: 'concept',
  aliases: [],
  memoryIds: [],
  ...over
})
const edge = (id: string, sourceId: string, targetId: string): KGEdge => ({
  id,
  sourceId,
  targetId,
  label: 'rel',
  memoryIds: []
})
const g = (nodes: KGNode[], edges: KGEdge[]): KnowledgeGraph => ({ nodes, edges })

describe('mergeGraphs', () => {
  it('returns an empty graph when both are empty', () => {
    expect(mergeGraphs(g([], []), g([], []))).toEqual({ nodes: [], edges: [] })
  })

  it('unions disjoint graphs', () => {
    const base = g([node('user', { nodeType: 'person' })], [])
    const overlay = g([node('proj')], [edge('e1', 'user', 'proj')])
    const merged = mergeGraphs(base, overlay)
    expect(merged.nodes.map((n) => n.id)).toEqual(['user', 'proj'])
    expect(merged.edges.map((e) => e.id)).toEqual(['e1'])
  })

  it('dedupes nodes by id with the base winning the collision', () => {
    const base = g([node('user', { label: 'Ander', nodeType: 'person' })], [])
    const overlay = g([node('user', { label: 'someone-else', nodeType: 'concept' })], [])
    const merged = mergeGraphs(base, overlay)
    expect(merged.nodes).toHaveLength(1)
    expect(merged.nodes[0].label).toBe('Ander')
    expect(merged.nodes[0].nodeType).toBe('person')
  })

  it('dedupes edges by id with the base winning the collision', () => {
    const base = g([], [edge('e1', 'a', 'b')])
    const overlay = g([], [{ ...edge('e1', 'x', 'y'), label: 'other' }])
    const merged = mergeGraphs(base, overlay)
    expect(merged.edges).toHaveLength(1)
    expect(merged.edges[0].sourceId).toBe('a')
  })

  it('keeps the onboarding floor when the overlay (server KG) is empty', () => {
    const base = g(
      [node('user', { nodeType: 'person' }), node('language_en'), node('app_slack', { nodeType: 'thing' })],
      [edge('e1', 'user', 'language_en'), edge('e2', 'user', 'app_slack')]
    )
    const merged = mergeGraphs(base, g([], []))
    expect(merged.nodes).toHaveLength(3)
    expect(merged.edges).toHaveLength(2)
  })
})

describe('scopeGraphToMemories', () => {
  const mem = (...ids: string[]): Partial<KGNode> => ({ memoryIds: ids })

  it('keeps only nodes referencing a current memory', () => {
    const graph = g(
      [
        node('keep', mem('m1')),
        node('keep2', mem('m9', 'm2')), // intersects via m2
        node('drop', mem('m8')), // no current memory
        node('untagged', mem()) // no memoryIds at all
      ],
      []
    )
    const scoped = scopeGraphToMemories(graph, new Set(['m1', 'm2', 'm3']))
    expect(scoped.nodes.map((n) => n.id).sort()).toEqual(['keep', 'keep2'])
  })

  it('drops edges whose endpoints did not survive the node filter', () => {
    const graph = g(
      [node('a', mem('m1')), node('b', mem('m1')), node('c', mem('gone'))],
      [
        edge('ab', 'a', 'b'), // both kept
        edge('ac', 'a', 'c') // c dropped -> edge dropped
      ]
    )
    const scoped = scopeGraphToMemories(graph, new Set(['m1']))
    expect(scoped.nodes.map((n) => n.id).sort()).toEqual(['a', 'b'])
    expect(scoped.edges.map((e) => e.id)).toEqual(['ab'])
  })

  it('returns an empty graph when no node references a current memory', () => {
    const graph = g([node('x', mem('old')), node('y', mem('older'))], [edge('xy', 'x', 'y')])
    expect(scopeGraphToMemories(graph, new Set(['current']))).toEqual({ nodes: [], edges: [] })
  })
})
