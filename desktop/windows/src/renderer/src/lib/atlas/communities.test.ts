import { describe, expect, it } from 'vitest'
import {
  LOUVAIN_EPSILON,
  denseRelabel,
  detectCommunities,
  membersByCommunity,
  mergeByModularity
} from './communities'
import { atlasLinks, neighboursOf } from './relatedness'
import type { KnowledgeGraph } from '../../../../shared/types'

const neighbours = (
  pairs: Array<[string, string, number]>
): Map<string, Array<{ id: string; weight: number }>> => {
  const out = new Map<string, Array<{ id: string; weight: number }>>()
  const add = (from: string, to: string, weight: number): void => {
    const existing = out.get(from)
    if (existing === undefined) out.set(from, [{ id: to, weight }])
    else existing.push({ id: to, weight })
  }
  for (const [a, b, w] of pairs) {
    add(a, b, w)
    add(b, a, w)
  }
  return out
}

/** Two triangles joined by one thin edge - the textbook case for community
 *  detection, and the shape a real graph's regions approximate. */
const TWO_CLIQUES: Array<[string, string, number]> = [
  ['a1', 'a2', 5],
  ['a2', 'a3', 5],
  ['a3', 'a1', 5],
  ['b1', 'b2', 5],
  ['b2', 'b3', 5],
  ['b3', 'b1', 5],
  ['a1', 'b1', 0.1]
]

describe('denseRelabel', () => {
  it('renumbers in first-seen order', () => {
    expect(denseRelabel([7, 7, 3, 9, 3])).toEqual([0, 0, 1, 2, 1])
  })

  it('leaves an already dense labelling alone', () => {
    expect(denseRelabel([0, 1, 2])).toEqual([0, 1, 2])
  })
})

describe('mergeByModularity', () => {
  it('returns the identity partition for a graph with no weight', () => {
    // Inventing groups for an empty graph would draw territories over nothing.
    const adjacency = [new Map<number, number>(), new Map<number, number>()]
    expect(mergeByModularity(adjacency, [0, 0])).toEqual([0, 1])
  })

  it('handles an empty graph', () => {
    expect(mergeByModularity([], [])).toEqual([])
  })

  it('leaves a node where it is when a candidate only ties', () => {
    // A node pulled by an equal-scoring candidate makes the partition oscillate
    // and never settle, so the map would reorganise itself on every run.
    const adjacency = [
      new Map([
        [1, 1],
        [2, 1]
      ]),
      new Map([[0, 1]]),
      new Map([[0, 1]])
    ]
    const first = mergeByModularity(adjacency, [0, 0, 0])
    const second = mergeByModularity(adjacency, [0, 0, 0])
    expect(first).toEqual(second)
    expect(LOUVAIN_EPSILON).toBeGreaterThan(0)
  })
})

describe('detectCommunities', () => {
  it('separates two dense clusters joined by a thin edge', () => {
    const membership = detectCommunities(
      ['a1', 'a2', 'a3', 'b1', 'b2', 'b3'],
      neighbours(TWO_CLIQUES)
    )
    const groupOf = (id: string): number => membership.get(id) as number
    expect(groupOf('a1')).toBe(groupOf('a2'))
    expect(groupOf('a2')).toBe(groupOf('a3'))
    expect(groupOf('b1')).toBe(groupOf('b2'))
    expect(groupOf('b2')).toBe(groupOf('b3'))
    expect(groupOf('a1')).not.toBe(groupOf('b1'))
  })

  it('gives the same answer whatever order the ids arrive in', () => {
    // The graph is merged from an onboarding floor plus a server fetch, whose
    // interleaving is not fixed, so a partition that depended on arrival order
    // would rearrange the map for no reason the user can see.
    const ids = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']
    const forward = detectCommunities(ids, neighbours(TWO_CLIQUES))
    const reversed = detectCommunities([...ids].reverse(), neighbours(TWO_CLIQUES))

    const shape = (m: Map<string, number>): string =>
      [...m.keys()]
        .sort()
        .map((id) => {
          const same = [...m.keys()].filter((other) => m.get(other) === m.get(id)).sort()
          return `${id}:${same.join(',')}`
        })
        .join('|')
    expect(shape(reversed)).toBe(shape(forward))
  })

  it('gives every id a community, including ones with no links', () => {
    const membership = detectCommunities(['a1', 'a2', 'lonely'], neighbours([['a1', 'a2', 1]]))
    // A node dropped here vanishes from the map entirely, which is worse than
    // showing it alone.
    expect(membership.size).toBe(3)
    expect(membership.get('lonely')).toBeDefined()
    expect(membership.get('lonely')).not.toBe(membership.get('a1'))
  })

  it('ignores a self-edge, which says nothing about grouping', () => {
    const membership = detectCommunities(['a', 'b'], neighbours([['a', 'a', 99]]))
    expect(membership.get('a')).not.toBe(membership.get('b'))
  })

  it('is stable across repeated runs', () => {
    const ids = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']
    const once = detectCommunities(ids, neighbours(TWO_CLIQUES))
    const twice = detectCommunities(ids, neighbours(TWO_CLIQUES))
    expect([...twice.entries()]).toEqual([...once.entries()])
  })

  it('handles an empty graph', () => {
    expect(detectCommunities([], new Map()).size).toBe(0)
  })
})

describe('membersByCommunity', () => {
  it('lists members in sorted id order', () => {
    const membership = new Map([
      ['z', 0],
      ['a', 0],
      ['m', 1]
    ])
    const groups = membersByCommunity(membership)
    expect(groups.get(0)).toEqual(['a', 'z'])
    expect(groups.get(1)).toEqual(['m'])
  })
})

describe('end to end from a knowledge graph', () => {
  const graph: KnowledgeGraph = {
    nodes: [
      { id: 'work1', label: 'Acme', nodeType: 'org', aliases: [], memoryIds: ['m1', 'm2'] },
      { id: 'work2', label: 'Q3 Plan', nodeType: 'topic', aliases: [], memoryIds: ['m1'] },
      { id: 'work3', label: 'Dana', nodeType: 'person', aliases: [], memoryIds: ['m2'] },
      { id: 'home1', label: 'Lease', nodeType: 'topic', aliases: [], memoryIds: ['m9'] },
      { id: 'home2', label: 'Landlord', nodeType: 'person', aliases: [], memoryIds: ['m9'] }
    ],
    edges: [
      { id: 'e1', sourceId: 'work1', targetId: 'work2', label: '', memoryIds: ['m1'] },
      { id: 'e2', sourceId: 'work1', targetId: 'work3', label: '', memoryIds: ['m2'] },
      { id: 'e3', sourceId: 'work2', targetId: 'work3', label: '', memoryIds: ['m1'] },
      { id: 'e4', sourceId: 'home1', targetId: 'home2', label: '', memoryIds: ['m9'] }
    ]
  }

  it('finds the work group and the home group', () => {
    const links = atlasLinks(graph, null)
    const membership = detectCommunities(
      graph.nodes.map((n) => n.id),
      neighboursOf(links)
    )
    expect(membership.get('work1')).toBe(membership.get('work2'))
    expect(membership.get('home1')).toBe(membership.get('home2'))
    expect(membership.get('work1')).not.toBe(membership.get('home1'))
  })
})
