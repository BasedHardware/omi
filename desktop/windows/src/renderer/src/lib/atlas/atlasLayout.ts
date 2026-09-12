// Positions for the atlas.
//
// This is NOT the app's existing `computeLayout`, and the difference is the
// whole reason it exists. That layout spreads entities evenly, which is right
// for a node-link graph. The island algorithm needs the opposite: a community
// has to be denser than the map average, because a coastline is drawn where a
// community's own field beats the sea level, and a community spread as thinly as
// everything else never clears it.
//
// macOS solves this with a bespoke 1,600-line relaxation. Rather than port a
// second force engine, this adds one force to the one already in the tree: every
// entity is pulled toward its community's centre of mass. That is the minimum
// needed to make the ported island algorithm produce land, and it leaves the
// existing brain map untouched.
//
// Determinism: seeds are a phyllotaxis spiral by index, tick count is fixed, and
// no force here consults a random source - d3 only reaches for Math.random when
// a node arrives without coordinates, which is why the seeds are set first.

import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type SimulationNodeDatum
} from 'd3-force'
import type { AtlasLink } from './relatedness'

/** Ticks run before the positions are read. Fixed rather than run-to-convergence
 *  so the same graph always lands in the same place. */
export const LAYOUT_TICKS = 300
/** How hard entities push each other apart. */
export const CHARGE_STRENGTH = -140
/** How hard a community pulls its own members together. Strong enough to make a
 *  community denser than the map, gentle enough that the links still shape it. */
export const COMMUNITY_PULL = 0.22
/** Keeps entities from stacking, so a community has interior rather than a spike. */
export const COLLIDE_RADIUS = 12
/** Nominal space the simulation runs in; the result is normalised afterwards. */
export const LAYOUT_EXTENT = 1000

interface LayoutNode extends SimulationNodeDatum {
  id: string
  community: number
}

export interface LaidOutAtlasNode {
  id: string
  x: number
  y: number
}

/**
 * Seed positions: a phyllotaxis spiral per community, with communities
 * themselves placed on a spiral. Deterministic, and it starts communities apart
 * so the simulation separates them rather than having to tear them apart.
 */
export function seedPositions(
  ids: string[],
  membership: Map<string, number>
): Map<string, { x: number; y: number }> {
  const golden = 2.399963229728653
  const byCommunity = new Map<number, string[]>()
  for (const id of [...ids].sort()) {
    const group = membership.get(id) ?? -1
    const existing = byCommunity.get(group)
    if (existing === undefined) byCommunity.set(group, [id])
    else existing.push(id)
  }

  const out = new Map<string, { x: number; y: number }>()
  const groups = [...byCommunity.keys()].sort((a, b) => a - b)
  groups.forEach((group, groupIndex) => {
    const members = byCommunity.get(group) ?? []
    const groupAngle = groupIndex * golden
    const groupRadius = LAYOUT_EXTENT * (0.12 + 0.06 * groupIndex)
    const cx = LAYOUT_EXTENT / 2 + groupRadius * Math.cos(groupAngle)
    const cy = LAYOUT_EXTENT / 2 + groupRadius * Math.sin(groupAngle)
    members.forEach((id, i) => {
      const angle = i * golden
      const radius = LAYOUT_EXTENT * 0.05 * Math.sqrt((i + 0.5) / Math.max(members.length, 1))
      out.set(id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) })
    })
  })
  return out
}

/**
 * Lays the graph out with communities packed.
 *
 * `membership` decides which entities pull together; an entity with no community
 * (the anchor) is pulled to the centre instead, which is where it belongs.
 */
export function layoutAtlas(
  ids: string[],
  links: AtlasLink[],
  membership: Map<string, number>
): LaidOutAtlasNode[] {
  if (ids.length === 0) return []
  const seeds = seedPositions(ids, membership)
  const nodes: LayoutNode[] = [...ids].sort().map((id) => ({
    id,
    community: membership.get(id) ?? -1,
    x: seeds.get(id)?.x ?? LAYOUT_EXTENT / 2,
    y: seeds.get(id)?.y ?? LAYOUT_EXTENT / 2
  }))

  // Community centres, recomputed each tick so a community that drifts takes its
  // members with it rather than being stretched back to where it started.
  const centres = new Map<number, { x: number; y: number }>()
  const recentreCommunities = (): void => {
    const sums = new Map<number, { x: number; y: number; n: number }>()
    for (const node of nodes) {
      const acc = sums.get(node.community) ?? { x: 0, y: 0, n: 0 }
      acc.x += node.x ?? 0
      acc.y += node.y ?? 0
      acc.n += 1
      sums.set(node.community, acc)
    }
    centres.clear()
    for (const [group, acc] of sums) centres.set(group, { x: acc.x / acc.n, y: acc.y / acc.n })
  }
  recentreCommunities()

  const simulation = forceSimulation(nodes)
    .force('charge', forceManyBody().strength(CHARGE_STRENGTH))
    .force(
      'link',
      forceLink<LayoutNode, { source: string; target: string; weight: number }>(
        links.map((l) => ({ source: l.a, target: l.b, weight: l.weight }))
      )
        .id((n) => n.id)
        .distance(60)
        .strength(0.4)
    )
    .force('collide', forceCollide(COLLIDE_RADIUS))
    // The community pull. An entity with no community is drawn to the middle.
    .force(
      'communityX',
      forceX<LayoutNode>((n) => centres.get(n.community)?.x ?? LAYOUT_EXTENT / 2).strength(
        COMMUNITY_PULL
      )
    )
    .force(
      'communityY',
      forceY<LayoutNode>((n) => centres.get(n.community)?.y ?? LAYOUT_EXTENT / 2).strength(
        COMMUNITY_PULL
      )
    )
    .stop()

  for (let i = 0; i < LAYOUT_TICKS; i += 1) {
    recentreCommunities()
    simulation.tick()
  }

  return nodes.map((n) => ({ id: n.id, x: n.x ?? 0, y: n.y ?? 0 }))
}
