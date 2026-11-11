import { describe, it, expect } from 'vitest'
import type { KnowledgeGraph, KGNode, KGEdge } from '../../../shared/types'
import {
  nodeDegrees,
  rankNodes,
  capGraph,
  isCapped,
  topRankedIds,
  labeledNodeIds,
  DEFAULT_NODE_CAP,
  DEFAULT_LABEL_TOPK
} from './graphDisplay'

const node = (id: string, over: Partial<KGNode> = {}): KGNode => ({
  id,
  label: id,
  nodeType: 'concept',
  aliases: [],
  memoryIds: [],
  ...over
})
const edge = (sourceId: string, targetId: string): KGEdge => ({
  id: `${sourceId}-${targetId}`,
  sourceId,
  targetId,
  label: '',
  memoryIds: []
})

// A tiny star: hub connected to a,b,c; plus an isolated node z.
const star: KnowledgeGraph = {
  nodes: [node('hub'), node('a'), node('b'), node('c'), node('z')],
  edges: [edge('hub', 'a'), edge('hub', 'b'), edge('hub', 'c')]
}

describe('nodeDegrees', () => {
  it('counts undirected connections and zeroes isolated nodes', () => {
    const d = nodeDegrees(star)
    expect(d.get('hub')).toBe(3)
    expect(d.get('a')).toBe(1)
    expect(d.get('z')).toBe(0)
  })

  it('counts a self-loop once, not twice', () => {
    const d = nodeDegrees({ nodes: [node('x')], edges: [edge('x', 'x')] })
    expect(d.get('x')).toBe(1)
  })

  it('ignores edges to nodes not in the graph', () => {
    const d = nodeDegrees({ nodes: [node('x')], edges: [edge('x', 'ghost')] })
    expect(d.get('x')).toBe(1)
  })
})

describe('rankNodes', () => {
  it('orders by degree desc', () => {
    expect(rankNodes(star).map((n) => n.id)).toEqual(['hub', 'a', 'b', 'c', 'z'])
  })

  it('always sorts the center node first regardless of degree', () => {
    expect(rankNodes(star, 'z').map((n) => n.id)[0]).toBe('z')
  })

  it('breaks degree ties by memory count desc, then id asc', () => {
    const g: KnowledgeGraph = {
      nodes: [node('a', { memoryIds: ['m1'] }), node('b', { memoryIds: ['m1', 'm2'] }), node('c')],
      edges: []
    }
    // all degree 0 → b (2 mems) > a (1 mem) > c (0 mems)
    expect(rankNodes(g).map((n) => n.id)).toEqual(['b', 'a', 'c'])
  })

  it('is a pure sort — does not mutate the input node array', () => {
    const ids = star.nodes.map((n) => n.id)
    rankNodes(star)
    expect(star.nodes.map((n) => n.id)).toEqual(ids)
  })
})

describe('capGraph', () => {
  it('keeps the top-cap nodes and prunes dangling edges', () => {
    const capped = capGraph(star, 2)
    expect(capped.nodes.map((n) => n.id).sort()).toEqual(['a', 'hub'])
    // hub-b and hub-c drop (b,c gone); hub-a survives
    expect(capped.edges.map((e) => e.id)).toEqual(['hub-a'])
  })

  it('never drops the center node even when it is low-degree', () => {
    const capped = capGraph(star, 1, 'z')
    expect(capped.nodes.map((n) => n.id)).toEqual(['z'])
  })

  it('returns the SAME graph ref when the cap does not bite (show-all path)', () => {
    expect(capGraph(star, 5)).toBe(star)
    expect(capGraph(star, Infinity)).toBe(star)
    expect(capGraph(star, 0)).toBe(star)
    expect(capGraph(star, -1)).toBe(star)
  })
})

describe('isCapped', () => {
  it('is true only when the cap actually hides nodes', () => {
    expect(isCapped(star, 3)).toBe(true)
    expect(isCapped(star, 5)).toBe(false)
    expect(isCapped(star, Infinity)).toBe(false)
    expect(isCapped(star, 0)).toBe(false)
  })
})

describe('topRankedIds', () => {
  it('returns the top-K node ids and is invariant to hover/selection (memoizable base)', () => {
    expect([...topRankedIds(star, 2)].sort()).toEqual(['a', 'hub'])
    // center pinned first even at low degree
    expect(topRankedIds(star, 1, 'z').has('z')).toBe(true)
  })
  it('clamps K to the node count and handles 0', () => {
    expect(topRankedIds(star, 999).size).toBe(star.nodes.length)
    expect(topRankedIds(star, 0).size).toBe(0)
  })
})

describe('labeledNodeIds', () => {
  it('labels the top-K most important nodes', () => {
    const ids = labeledNodeIds(star, 2)
    expect(ids.has('hub')).toBe(true)
    expect(ids.has('a')).toBe(true)
    expect(ids.has('z')).toBe(false)
  })

  it('always labels center, hovered, and selected even outside top-K', () => {
    // No center override → top-1 is the hub. Center 'c', hovered 'z' (isolated),
    // and selected 'b' are all added despite being outside the top-1.
    const ids = labeledNodeIds(star, 1, { centerNodeId: 'c', hoveredId: 'z', selectedId: 'b' })
    expect(ids.has('c')).toBe(true) // center (also ranks first, so top-1)
    expect(ids.has('z')).toBe(true) // hovered — outside top-K
    expect(ids.has('b')).toBe(true) // selected — outside top-K
    expect(ids.has('a')).toBe(false) // untouched, outside top-K
  })

  it('handles topK of 0 (label only interaction targets)', () => {
    const ids = labeledNodeIds(star, 0, { hoveredId: 'a' })
    expect([...ids]).toEqual(['a'])
  })
})

describe('defaults', () => {
  it('exposes sane defaults justified by the measured graph scale', () => {
    expect(DEFAULT_NODE_CAP).toBeGreaterThanOrEqual(100)
    expect(DEFAULT_LABEL_TOPK).toBeGreaterThanOrEqual(10)
    expect(DEFAULT_LABEL_TOPK).toBeLessThan(DEFAULT_NODE_CAP)
  })
})
