import { describe, expect, it } from 'vitest'
import {
  ANCHOR_TETHER,
  MAX_MEMORY_PARTICIPANTS,
  NEIGHBOUR_LIMIT,
  atlasLinks,
  coOccurrenceLinks,
  explicitLinks,
  linkKey,
  makeLink,
  mergeLinks,
  neighboursOf,
  strongestPerNode
} from './relatedness'
import type { KGNode, KnowledgeGraph } from '../../../../shared/types'

const node = (id: string, memoryIds: string[] = []): KGNode => ({
  id,
  label: id,
  nodeType: 'topic',
  aliases: [],
  memoryIds
})

const graph = (nodes: KGNode[], edges: Array<[string, string, string[]]>): KnowledgeGraph => ({
  nodes,
  edges: edges.map(([sourceId, targetId, memoryIds], i) => ({
    id: `e${i}`,
    sourceId,
    targetId,
    label: '',
    memoryIds
  }))
})

describe('linkKey', () => {
  it('is the same whichever end the pair is seen from', () => {
    expect(linkKey('a', 'b')).toBe(linkKey('b', 'a'))
  })

  it('cannot be forged by an id containing the separator', () => {
    // The separator is U+0001, which an entity id cannot contain, so "ab" + "c"
    // can never collide with "a" + "bc".
    expect(linkKey('ab', 'c')).not.toBe(linkKey('a', 'bc'))
  })

  it('orders endpoints canonically', () => {
    expect(makeLink('z', 'a', 1)).toEqual({ a: 'a', b: 'z', weight: 1 })
  })
})

describe('mergeLinks', () => {
  it('sums duplicates and drops self-links', () => {
    const merged = mergeLinks([makeLink('a', 'b', 1), makeLink('b', 'a', 2), makeLink('c', 'c', 9)])
    expect(merged).toEqual([{ a: 'a', b: 'b', weight: 3 }])
  })

  it('preserves first-seen order', () => {
    // The weights are floating point, so a different addition order gives a
    // different last bit and the layout stops being reproducible.
    const merged = mergeLinks([makeLink('m', 'n', 1), makeLink('a', 'b', 1)])
    expect(merged.map((l) => l.a)).toEqual(['m', 'a'])
  })
})

describe('explicitLinks', () => {
  it('weights a link by its memories, but logarithmically', () => {
    const [one] = explicitLinks(graph([node('a'), node('b')], [['a', 'b', ['m1']]]))
    const [many] = explicitLinks(
      graph([node('a'), node('b')], [['a', 'b', ['m1', 'm2', 'm3', 'm4', 'm5']]])
    )
    // The fifth memory about a pair says much less than the second.
    expect(many.weight).toBeGreaterThan(one.weight)
    expect(many.weight).toBeLessThan(one.weight * 3)
    expect(one.weight).toBeCloseTo(1 + Math.log1p(1), 12)
  })

  it('drops a self-edge', () => {
    expect(explicitLinks(graph([node('a')], [['a', 'a', ['m1']]]))).toEqual([])
  })

  it('merges parallel edges between the same pair', () => {
    const links = explicitLinks(
      graph(
        [node('a'), node('b')],
        [
          ['a', 'b', []],
          ['b', 'a', []]
        ]
      )
    )
    expect(links.length).toBe(1)
    expect(links[0].weight).toBe(2)
  })
})

describe('coOccurrenceLinks', () => {
  it('relates two entities that share a memory', () => {
    const links = coOccurrenceLinks([node('a', ['m1']), node('b', ['m1'])], null)
    expect(links.map((l) => [l.a, l.b])).toEqual([['a', 'b']])
    expect(links[0].weight).toBeGreaterThan(0)
  })

  it('ignores a memory nobody shares', () => {
    expect(coOccurrenceLinks([node('a', ['m1']), node('b', ['m2'])], null)).toEqual([])
  })

  it('skips a memory shared by a crowd', () => {
    // A memory naming everyone relates everything to everything, which carries
    // the same information as relating nothing.
    const many = Array.from({ length: MAX_MEMORY_PARTICIPANTS + 1 }, (_v, i) =>
      node(`n${i}`, ['crowd'])
    )
    expect(coOccurrenceLinks(many, null)).toEqual([])
  })

  it('weights a rare entity above a ubiquitous one', () => {
    // `hub` appears in every memory, so co-occurring with it says little; `rare`
    // appears once, so co-occurring with it says a lot.
    const nodes = [
      node('hub', ['m1', 'm2', 'm3']),
      node('rare', ['m1']),
      node('common', ['m1', 'm2', 'm3'])
    ]
    const links = coOccurrenceLinks(nodes, null)
    const weightOf = (a: string, b: string): number =>
      links.find((l) => linkKey(l.a, l.b) === linkKey(a, b))?.weight ?? 0
    expect(weightOf('hub', 'rare')).toBeGreaterThan(0)
    expect(weightOf('hub', 'rare')).toBeGreaterThan(weightOf('hub', 'common') / 3)
  })

  it('excludes the anchor so the account holder does not co-occur with everything', () => {
    const links = coOccurrenceLinks(
      [node('me', ['m1']), node('a', ['m1']), node('b', ['m1'])],
      'me'
    )
    expect(links.some((l) => l.a === 'me' || l.b === 'me')).toBe(false)
    expect(links.length).toBe(1)
  })
})

describe('strongestPerNode', () => {
  it('keeps a link that matters to either endpoint', () => {
    // The hub ranks this link last, but it is the leaf's only link; dropping it
    // would strand the leaf.
    const hubLinks = Array.from({ length: NEIGHBOUR_LIMIT }, (_v, i) =>
      makeLink('hub', `strong${i}`, 10)
    )
    const kept = strongestPerNode([...hubLinks, makeLink('hub', 'leaf', 0.001)], NEIGHBOUR_LIMIT)
    expect(kept.some((l) => l.a === 'leaf' || l.b === 'leaf')).toBe(true)
  })

  it('breaks weight ties on the key so the result does not depend on input order', () => {
    const links = [makeLink('n', 'z', 1), makeLink('n', 'a', 1)]
    const forward = strongestPerNode(links, 1).map((l) => linkKey(l.a, l.b))
    const reversed = strongestPerNode([...links].reverse(), 1).map((l) => linkKey(l.a, l.b))
    expect(new Set(reversed)).toEqual(new Set(forward))
  })
})

describe('atlasLinks', () => {
  it('weakens the anchor so it does not pull the map into one blob', () => {
    const g = graph([node('me'), node('a')], [['me', 'a', ['m1']]])
    const untethered = atlasLinks(g, null)[0].weight
    const tethered = atlasLinks(g, 'me')[0].weight
    expect(tethered).toBeCloseTo(untethered * ANCHOR_TETHER, 12)
  })

  it('combines both signals for the same pair', () => {
    const g = graph([node('a', ['m1']), node('b', ['m1'])], [['a', 'b', ['m1']]])
    const [link] = atlasLinks(g, null)
    // The pair is both stated by an edge and observed in a shared memory.
    expect(link.weight).toBeGreaterThan(1 + Math.log1p(1))
  })
})

describe('neighboursOf', () => {
  it('lists both directions, strongest first', () => {
    const map = neighboursOf([makeLink('a', 'b', 1), makeLink('a', 'c', 5)])
    expect(map.get('a')?.map((n) => n.id)).toEqual(['c', 'b'])
    expect(map.get('b')?.map((n) => n.id)).toEqual(['a'])
  })

  it('breaks a weight tie on id so the order is not input order', () => {
    const map = neighboursOf([makeLink('a', 'z', 1), makeLink('a', 'b', 1)])
    expect(map.get('a')?.map((n) => n.id)).toEqual(['b', 'z'])
  })
})
