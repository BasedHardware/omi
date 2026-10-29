// How strongly two entities in the knowledge graph are related.
//
// Ported from macOS `MemoryAtlasForceLayout.swift`. Two signals are combined:
// the edges the graph states outright, and the memories two entities keep
// turning up in together.
//
// THE DETERMINISM RULE, which governs this whole package: every traversal that
// can affect an output walks a SORTED array. macOS needs that because Swift
// seeds string hashing per process, so dictionary order is not stable across
// launches; JS object and Map iteration order is insertion-ordered and therefore
// stable, but the sorts are kept anyway. They are what make the output a
// function of the graph rather than of the order the graph happened to arrive
// in, and the graph arrives from two merged sources (an onboarding floor plus a
// server fetch) whose interleaving is not fixed.

import type { KnowledgeGraph, KGNode } from '../../../../shared/types'

/** Canonical undirected link. Endpoints are ordered so `a <= b`, which is what
 *  makes the key stable regardless of which end an edge was seen from. */
export interface AtlasLink {
  a: string
  b: string
  weight: number
}

/** U+0001, constructed rather than written literally: it cannot occur in an id,
 *  so the key is unambiguous, and building it means no editor, formatter or copy
 *  through a terminal can silently eat the control character. */
const SEP = String.fromCharCode(1)

/** Canonical key for an undirected pair. */
export function linkKey(a: string, b: string): string {
  return a <= b ? `${a}${SEP}${b}` : `${b}${SEP}${a}`
}

export function makeLink(x: string, y: string, weight: number): AtlasLink {
  return x <= y ? { a: x, b: y, weight } : { a: y, b: x, weight }
}

/** Strongest links kept per node. */
export const NEIGHBOUR_LIMIT = 6
/** A memory shared by more than this many entities says nothing about any pair
 *  of them, so it is skipped entirely rather than diluted. */
export const MAX_MEMORY_PARTICIPANTS = 20
/** Links touching the anchor are weakened so the account holder does not pull
 *  the whole map into one blob. */
export const ANCHOR_TETHER = 0.1

/**
 * Sums duplicate links, drops self-links, and preserves first-seen key order.
 * Order preservation matters: the sum is floating point, so a different
 * addition order gives a different last bit, and the layout that consumes these
 * is asserted to be bit-identical run to run.
 */
export function mergeLinks(links: AtlasLink[]): AtlasLink[] {
  const byKey = new Map<string, AtlasLink>()
  for (const link of links) {
    if (link.a === link.b) continue
    const key = linkKey(link.a, link.b)
    const existing = byKey.get(key)
    if (existing === undefined) byKey.set(key, { ...link })
    else existing.weight += link.weight
  }
  return [...byKey.values()]
}

/** Explicit graph edges. A link's weight grows with the memories behind it, but
 *  logarithmically: the tenth memory about a pair says much less than the second. */
export function explicitLinks(graph: KnowledgeGraph): AtlasLink[] {
  const links: AtlasLink[] = []
  for (const edge of graph.edges) {
    if (edge.sourceId === edge.targetId) continue
    const memoryCount = Math.max(edge.memoryIds?.length ?? 0, 0)
    links.push(makeLink(edge.sourceId, edge.targetId, 1 + Math.log1p(memoryCount)))
  }
  return mergeLinks(links)
}

/**
 * Links inferred from entities appearing in the same memory.
 *
 * Each memory divides one unit of relatedness among its participants, and each
 * participant is weighted by how rare it is across all memories (inverse
 * document frequency), so two entities that only ever co-occur inside one very
 * common entity's memories are not treated as related to each other.
 */
export function coOccurrenceLinks(nodes: KGNode[], anchorId: string | null): AtlasLink[] {
  const memoryIdsByNode = new Map<string, string[]>()
  for (const node of nodes) {
    if (node.id === anchorId) continue
    memoryIdsByNode.set(node.id, node.memoryIds ?? [])
  }

  const nodeIdsByMemory = new Map<string, string[]>()
  for (const nodeId of [...memoryIdsByNode.keys()].sort()) {
    for (const memoryId of memoryIdsByNode.get(nodeId) ?? []) {
      const existing = nodeIdsByMemory.get(memoryId)
      if (existing === undefined) nodeIdsByMemory.set(memoryId, [nodeId])
      else existing.push(nodeId)
    }
  }

  const totalMemories = Math.max(nodeIdsByMemory.size, 1)
  const evidence = new Map<string, number>()
  for (const nodeId of [...memoryIdsByNode.keys()].sort()) {
    const appearances = new Set(memoryIdsByNode.get(nodeId) ?? []).size
    if (appearances === 0) continue
    evidence.set(nodeId, Math.log(1 + totalMemories / appearances))
  }

  const weights = new Map<string, AtlasLink>()
  for (const memoryId of [...nodeIdsByMemory.keys()].sort()) {
    const participants = [...new Set(nodeIdsByMemory.get(memoryId) ?? [])].sort()
    // A memory about one entity relates nothing; a memory about a crowd relates
    // everything to everything, which is the same as relating nothing.
    if (participants.length < 2 || participants.length > MAX_MEMORY_PARTICIPANTS) continue
    const share = 1 / (participants.length - 1)
    for (let i = 0; i < participants.length; i += 1) {
      for (let j = i + 1; j < participants.length; j += 1) {
        const specific =
          share * (evidence.get(participants[i]) ?? 1) * (evidence.get(participants[j]) ?? 1)
        const key = linkKey(participants[i], participants[j])
        const existing = weights.get(key)
        if (existing === undefined) {
          weights.set(key, makeLink(participants[i], participants[j], specific))
        } else {
          existing.weight += specific
        }
      }
    }
  }
  return strongestPerNode([...weights.values()], NEIGHBOUR_LIMIT)
}

/**
 * Keeps a link when EITHER endpoint ranks it among its strongest. A link that
 * matters to a leaf but not to the hub it hangs off survives, which is what
 * stops sparsification from stranding small entities.
 */
export function strongestPerNode(links: AtlasLink[], limit: number): AtlasLink[] {
  const byNode = new Map<string, AtlasLink[]>()
  const add = (id: string, link: AtlasLink): void => {
    const existing = byNode.get(id)
    if (existing === undefined) byNode.set(id, [link])
    else existing.push(link)
  }
  for (const link of links) {
    add(link.a, link)
    add(link.b, link)
  }

  const kept = new Set<string>()
  for (const nodeId of [...byNode.keys()].sort()) {
    const ranked = [...(byNode.get(nodeId) ?? [])].sort((x, y) => {
      if (y.weight !== x.weight) return y.weight - x.weight
      const kx = linkKey(x.a, x.b)
      const ky = linkKey(y.a, y.b)
      return kx < ky ? -1 : kx > ky ? 1 : 0
    })
    for (const link of ranked.slice(0, limit)) kept.add(linkKey(link.a, link.b))
  }
  return links.filter((link) => kept.has(linkKey(link.a, link.b)))
}

/** Both signals, merged, with the anchor's own links weakened. */
export function atlasLinks(graph: KnowledgeGraph, anchorId: string | null): AtlasLink[] {
  const merged = mergeLinks([...explicitLinks(graph), ...coOccurrenceLinks(graph.nodes, anchorId)])
  if (anchorId === null) return merged
  return merged.map((link) =>
    link.a === anchorId || link.b === anchorId
      ? { ...link, weight: link.weight * ANCHOR_TETHER }
      : link
  )
}

/** Weighted adjacency, each neighbour list sorted by weight desc then id asc. */
export function neighboursOf(
  links: AtlasLink[]
): Map<string, Array<{ id: string; weight: number }>> {
  const out = new Map<string, Array<{ id: string; weight: number }>>()
  const add = (from: string, to: string, weight: number): void => {
    const existing = out.get(from)
    if (existing === undefined) out.set(from, [{ id: to, weight }])
    else existing.push({ id: to, weight })
  }
  for (const link of links) {
    add(link.a, link.b, link.weight)
    add(link.b, link.a, link.weight)
  }
  for (const list of out.values()) {
    list.sort((x, y) => {
      if (y.weight !== x.weight) return y.weight - x.weight
      return x.id < y.id ? -1 : x.id > y.id ? 1 : 0
    })
  }
  return out
}
