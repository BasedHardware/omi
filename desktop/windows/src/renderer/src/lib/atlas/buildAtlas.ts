// The whole atlas, from a knowledge graph to something drawable.
//
//   relatedness  ->  communities  ->  positions  ->  coastlines  ->  territories
//
// Communities are detected BEFORE positions are computed, because the layout
// needs them: an island is drawn where a community's own field beats the sea
// level, and a community spread as thinly as the rest of the map never clears
// it. See atlasLayout.ts for why that is its own layout rather than the app's
// existing one.

import type { KnowledgeGraph } from '../../../../shared/types'
import { nodeDegrees } from '../graphDisplay'
import { layoutAtlas } from './atlasLayout'
import { atlasLinks, neighboursOf } from './relatedness'
import { detectCommunities, membersByCommunity } from './communities'
import { coastlines, type AtlasPoint } from './islands'
import { buildTerritories, type AtlasMember, type Territory } from './territories'

export interface AtlasNode {
  id: string
  label: string
  nodeType: string
  /** Normalised atlas space, 0..1 on both axes. */
  position: AtlasPoint
  degree: number
  community: number
}

export interface Atlas {
  nodes: AtlasNode[]
  territories: Territory[]
  /** Communities that hold land but could not be named, so a caller can say how
   *  much of the map is unlabelled rather than silently omitting it. */
  unnamedCommunities: number
}

const EMPTY: Atlas = { nodes: [], territories: [], unnamedCommunities: 0 }

/**
 * Rescales laid-out coordinates into the unit square the island field expects.
 *
 * The field is a fixed 128x128 grid with a margin, so a layout in pixel space
 * would land almost entirely in one cell. Normalising by the actual extent
 * rather than by the nominal viewport keeps the map filling the field however
 * tightly or loosely the layout happened to settle.
 */
export function normalisePositions(
  points: Array<{ id: string; x: number; y: number }>
): Map<string, AtlasPoint> {
  const out = new Map<string, AtlasPoint>()
  if (points.length === 0) return out
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  // A degenerate extent (every node stacked) would divide by zero; centring them
  // is the only sensible answer and produces no land, which is correct.
  const spanX = maxX - minX
  const spanY = maxY - minY
  const span = Math.max(spanX, spanY)
  if (span <= 0) {
    for (const p of points) out.set(p.id, { x: 0.5, y: 0.5 })
    return out
  }
  // One scale for both axes so the map is not stretched; the shorter axis is
  // centred in what is left.
  const offsetX = (span - spanX) / 2
  const offsetY = (span - spanY) / 2
  for (const p of points) {
    out.set(p.id, { x: (p.x - minX + offsetX) / span, y: (p.y - minY + offsetY) / span })
  }
  return out
}

/**
 * Builds the atlas.
 *
 * `anchorId` is the account holder's node when the graph has one. It is excluded
 * from every community, so a region can never end up named after the user.
 */
export function buildAtlas(graph: KnowledgeGraph, anchorId?: string): Atlas {
  if (graph.nodes.length === 0) return EMPTY

  const anchor = anchorId ?? null
  const links = atlasLinks(graph, anchor)
  const neighbours = neighboursOf(links)
  const degrees = nodeDegrees(graph)

  // The anchor is left out of community detection entirely: it touches
  // everything, so including it merges the whole map into one region.
  const groupedIds = graph.nodes.map((n) => n.id).filter((id) => id !== anchor)
  const membership = detectCommunities(groupedIds, neighbours)

  const laidOut = layoutAtlas(
    graph.nodes.map((n) => n.id),
    links,
    membership
  )
  const positions = normalisePositions(laidOut)

  const nodes: AtlasNode[] = graph.nodes.map((node) => ({
    id: node.id,
    label: node.label,
    nodeType: node.nodeType,
    position: positions.get(node.id) ?? { x: 0.5, y: 0.5 },
    degree: degrees.get(node.id) ?? 0,
    // -1 marks the anchor: it belongs to no region by construction.
    community: membership.get(node.id) ?? -1
  }))

  const byGroup = membersByCommunity(membership)
  const pointsByGroup = new Map<number, AtlasPoint[]>()
  const membersByGroup = new Map<number, AtlasMember[]>()
  for (const group of [...byGroup.keys()].sort((a, b) => a - b)) {
    const ids = byGroup.get(group) ?? []
    const members: AtlasMember[] = ids.map((id) => {
      const node = nodes.find((n) => n.id === id)
      return {
        id,
        label: node?.label ?? '',
        degree: node?.degree ?? 0,
        position: node?.position ?? { x: 0.5, y: 0.5 }
      }
    })
    membersByGroup.set(group, members)
    pointsByGroup.set(
      group,
      members.map((m) => m.position)
    )
  }

  // Every community competes for land, including ones that will never be named.
  // Leaving one out hands its ground to whichever named neighbour is closest,
  // which draws a territory over entities that do not belong to it.
  const ringsByGroup = coastlines(pointsByGroup)
  const territories = buildTerritories({
    membersByGroup,
    ringsByGroup,
    allPositions: nodes.map((n) => n.position)
  })

  const named = new Set(territories.map((t) => t.group))
  const unnamedCommunities = [...ringsByGroup.keys()].filter((g) => !named.has(g)).length

  return { nodes, territories, unnamedCommunities }
}
