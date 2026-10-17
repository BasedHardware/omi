import { describe, expect, it } from 'vitest'
import { buildAtlas, normalisePositions } from './buildAtlas'
import type { KGEdge, KGNode, KnowledgeGraph } from '../../../../shared/types'

const node = (id: string, label: string, memoryIds: string[] = []): KGNode => ({
  id,
  label,
  nodeType: 'topic',
  aliases: [],
  memoryIds
})

const edge = (a: string, b: string, memoryIds: string[] = []): KGEdge => ({
  id: `${a}-${b}`,
  sourceId: a,
  targetId: b,
  label: '',
  memoryIds
})

/**
 * Three topic clusters joined by thin edges. Each cluster is fully connected,
 * which is what a real topic cluster looks like: the entities in one subject are
 * related to each other, not strung out in a chain.
 */
const threeWorlds = (perCluster = 10): KnowledgeGraph => {
  const nodes: KGNode[] = []
  const edges: KGEdge[] = []
  for (const [prefix, hub] of [
    ['w', 'Acme'],
    ['h', 'Lease'],
    ['t', 'Travel']
  ] as const) {
    for (let i = 0; i < perCluster; i += 1) {
      nodes.push(node(`${prefix}${i}`, i === 0 ? hub : `${prefix} thing ${i}`, [`${prefix}m`]))
    }
    for (let i = 0; i < perCluster; i += 1) {
      for (let j = i + 1; j < perCluster; j += 1) {
        edges.push(edge(`${prefix}${i}`, `${prefix}${j}`, [`${prefix}m`]))
      }
    }
  }
  edges.push(edge('w0', 'h0'))
  edges.push(edge('h0', 't0'))
  return { nodes, edges }
}

describe('normalisePositions', () => {
  it('maps a layout into the unit square', () => {
    const out = normalisePositions([
      { id: 'a', x: 100, y: 200 },
      { id: 'b', x: 300, y: 400 }
    ])
    for (const p of out.values()) {
      expect(p.x).toBeGreaterThanOrEqual(0)
      expect(p.x).toBeLessThanOrEqual(1)
      expect(p.y).toBeGreaterThanOrEqual(0)
      expect(p.y).toBeLessThanOrEqual(1)
    }
  })

  it('uses one scale for both axes so the map is not stretched', () => {
    // A wide, short layout must stay wide and short; scaling each axis to fill
    // the square would distort every region's shape.
    const out = normalisePositions([
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: 100, y: 10 }
    ])
    const a = out.get('a') as { x: number; y: number }
    const b = out.get('b') as { x: number; y: number }
    expect(b.x - a.x).toBeCloseTo(1, 6)
    expect(b.y - a.y).toBeCloseTo(0.1, 6)
  })

  it('centres a degenerate layout rather than dividing by zero', () => {
    const out = normalisePositions([
      { id: 'a', x: 5, y: 5 },
      { id: 'b', x: 5, y: 5 }
    ])
    expect(out.get('a')).toEqual({ x: 0.5, y: 0.5 })
  })

  it('handles an empty layout', () => {
    expect(normalisePositions([]).size).toBe(0)
  })
})

describe('buildAtlas', () => {
  it('returns nothing for an empty graph', () => {
    expect(buildAtlas({ nodes: [], edges: [] })).toEqual({
      nodes: [],
      territories: [],
      unnamedCommunities: 0
    })
  })

  it('places every node and gives each a community', () => {
    const atlas = buildAtlas(threeWorlds())
    expect(atlas.nodes.length).toBe(30)
    for (const n of atlas.nodes) {
      expect(Number.isFinite(n.position.x)).toBe(true)
      expect(Number.isFinite(n.position.y)).toBe(true)
      expect(n.community).toBeGreaterThanOrEqual(0)
    }
  })

  it('separates the two worlds into different communities', () => {
    const atlas = buildAtlas(threeWorlds())
    const communityOf = (id: string): number =>
      atlas.nodes.find((n) => n.id === id)?.community as number
    expect(communityOf('w0')).toBe(communityOf('w5'))
    expect(communityOf('h0')).toBe(communityOf('h5'))
    expect(communityOf('w0')).not.toBe(communityOf('h0'))
  })

  it('draws a named region for each world', () => {
    const atlas = buildAtlas(threeWorlds())
    // The hubs carry every edge in their cluster, so they are what the regions
    // are about. Asserted unconditionally: a guard here would hide a pipeline
    // that had stopped producing regions at all.
    expect(atlas.territories.map((t) => t.caption).sort()).toEqual(['Acme', 'Lease', 'Travel'])
    expect(atlas.unnamedCommunities).toBe(0)
  })

  it('keeps a region over its own members', () => {
    const atlas = buildAtlas(threeWorlds())
    for (const territory of atlas.territories) {
      // A region whose members stand outside it is drawn over the wrong ground.
      expect(territory.purity).toBeGreaterThan(0.5)
    }
  })

  it('never puts the account holder in a region', () => {
    const graph = threeWorlds()
    graph.nodes.push(node('me', 'Zach'))
    for (const n of graph.nodes) {
      if (n.id !== 'me') graph.edges.push(edge('me', n.id))
    }
    const atlas = buildAtlas(graph, 'me')
    // The anchor touches everything, so including it would merge the whole map
    // into one region and could name that region after the user.
    expect(atlas.nodes.find((n) => n.id === 'me')?.community).toBe(-1)
    expect(atlas.territories.some((t) => t.memberIds.includes('me'))).toBe(false)
    expect(atlas.territories.some((t) => t.caption === 'Zach')).toBe(false)
  })

  it('gives the same atlas for the same graph', () => {
    const first = buildAtlas(threeWorlds())
    const second = buildAtlas(threeWorlds())
    expect(second.territories.map((t) => t.caption)).toEqual(
      first.territories.map((t) => t.caption)
    )
    expect(second.nodes.map((n) => n.community)).toEqual(first.nodes.map((n) => n.community))
  })

  it('survives a graph with no edges at all', () => {
    const graph: KnowledgeGraph = {
      nodes: Array.from({ length: 12 }, (_v, i) => node(`n${i}`, `Thing ${i}`)),
      edges: []
    }
    const atlas = buildAtlas(graph)
    expect(atlas.nodes.length).toBe(12)
    // Nothing is related to anything, so there are no regions to draw - but the
    // entities are still placed and still shown.
    expect(atlas.territories).toEqual([])
  })

  it('counts a community that holds land but could not be named', () => {
    // Every member is blank, so the community wins land and then has nothing to
    // call itself. Reported rather than silently dropped, so a caller can say
    // how much of the map is unlabelled instead of pretending it is not there.
    const graph = threeWorlds()
    for (const n of graph.nodes) {
      if (n.id.startsWith('t')) n.label = '   '
    }
    const atlas = buildAtlas(graph)
    expect(atlas.territories.map((t) => t.caption).sort()).toEqual(['Acme', 'Lease'])
    expect(atlas.unnamedCommunities).toBe(1)
  })
})
