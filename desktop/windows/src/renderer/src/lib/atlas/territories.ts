// Which communities become named territories, and what they are called.
//
// Ported from macOS `MemoryAtlasLayoutEngine` and
// `MemoryAtlasNeighbourhoodLabels`. Two decisions live here:
//
//   Which communities get drawn at all. A community too small to matter, or one
//   whose coastline came back empty, is not a place.
//
//   What a place is called. One name, not a list: a region labelled with four
//   entities reads as a list of entities rather than as somewhere.
//
// An island the map cannot name is not drawn. That is the contract rather than a
// bug: an unnamed shape on a map is noise, and the entities inside it are still
// visible as entities.

import { coastlineContains, type AtlasPoint, type Ring } from './islands'

/** Longest caption before it is truncated. */
export const CAPTION_CEILING = 26
/** A candidate name may not be wordier than this. */
export const CAPTION_MAX_WORDS = 3
/** Share of the map a community must hold to be a contender for a territory. */
export const TERRITORY_SIZE_SHARE = 0.015
/** ...and never fewer members than this, however small the map is. */
export const TERRITORY_MIN_MEMBERS = 6

export interface AtlasMember {
  id: string
  label: string
  /** Distinct neighbours in the relatedness graph. Drives which member names the
   *  region: the best-connected entity is the one the region is about. */
  degree: number
  position: AtlasPoint
}

export interface Territory {
  group: number
  caption: string
  rings: Ring[]
  memberIds: string[]
  center: AtlasPoint
  radius: number
  /** Share of everything standing inside this territory that actually belongs to
   *  it. A low value means the coastline swallowed other communities' entities. */
  purity: number
}

/** Communities large enough to be worth drawing. Everything above the floor is a
 *  contender, INCLUDING communities that will never be captioned: they still
 *  compete for land, and leaving one out hands its ground to a named neighbour. */
export function territorySizeFloor(totalPlacements: number): number {
  return Math.max(TERRITORY_MIN_MEMBERS, Math.floor(totalPlacements * TERRITORY_SIZE_SHARE))
}

const wordCount = (label: string): number => label.trim().split(/\s+/).filter(Boolean).length

/**
 * The name for a region, chosen from its members in three tiers.
 *
 * Members arrive ranked by degree desc, then label case-insensitively. A short
 * unwordy label is a name; a short but wordy one is a fallback; a long one is
 * truncated. Returns null when there is nothing to call the place.
 */
export function captionFor(rankedLabels: string[]): string | null {
  const cleaned = rankedLabels.map((l) => l.trim()).filter((l) => l.length > 0)

  const names = cleaned.filter(
    (l) => l.length <= CAPTION_CEILING && wordCount(l) <= CAPTION_MAX_WORDS
  )
  if (names.length > 0) return names[0]

  const shortButWordy = cleaned.filter((l) => l.length <= CAPTION_CEILING)
  if (shortButWordy.length > 0) return shortButWordy[0]

  const long = cleaned.find((l) => l.length > CAPTION_CEILING)
  if (long === undefined) return null
  // One character short of the ceiling, then the ellipsis, so the result is
  // never wider than a name that fit.
  return `${long.slice(0, CAPTION_CEILING - 1).trimEnd()}…`
}

/** Members ranked for captioning: best connected first, then by label so the
 *  choice does not depend on the order members were collected in. */
export function rankMembers(members: AtlasMember[]): AtlasMember[] {
  return [...members].sort((a, b) => {
    if (b.degree !== a.degree) return b.degree - a.degree
    const la = a.label.toLocaleLowerCase()
    const lb = b.label.toLocaleLowerCase()
    if (la !== lb) return la < lb ? -1 : 1
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  })
}

/** Arithmetic mean of the members' positions. */
export function centerOf(points: AtlasPoint[]): AtlasPoint {
  if (points.length === 0) return { x: 0.5, y: 0.5 }
  let x = 0
  let y = 0
  for (const p of points) {
    x += p.x
    y += p.y
  }
  return { x: x / points.length, y: y / points.length }
}

/**
 * How far the region reaches: the 80th-percentile distance from its centre, so a
 * single far-flung member does not inflate it. Floored so a tight cluster still
 * has somewhere to put a label.
 */
export function radiusOf(center: AtlasPoint, points: AtlasPoint[]): number {
  if (points.length === 0) return 0.01
  const distances = points
    .map((p) => Math.hypot(p.x - center.x, p.y - center.y))
    .sort((a, b) => a - b)
  const index = Math.min(distances.length - 1, Math.floor(distances.length * 0.8))
  return Math.max(distances[index], 0.01)
}

/**
 * Share of everything standing inside a coastline that belongs to the community
 * that owns it. Zero when nothing at all is inside.
 */
export function purityOf(rings: Ring[], members: AtlasPoint[], everyone: AtlasPoint[]): number {
  const inside = everyone.filter((p) => coastlineContains(rings, p)).length
  if (inside === 0) return 0
  return members.filter((p) => coastlineContains(rings, p)).length / inside
}

export interface BuildTerritoriesInput {
  /** Members per community, each list in sorted id order. */
  membersByGroup: Map<number, AtlasMember[]>
  /** Coastlines per community; a community absent here has no land. */
  ringsByGroup: Map<number, Ring[]>
  /** Every placed entity on the map, for the purity measure. */
  allPositions: AtlasPoint[]
}

/**
 * Territories, largest first.
 *
 * A community is dropped when it is too small, when it has no coastline, or when
 * nothing in it can name the place.
 */
export function buildTerritories(input: BuildTerritoriesInput): Territory[] {
  const floor = territorySizeFloor(input.allPositions.length)
  const out: Territory[] = []

  for (const group of [...input.membersByGroup.keys()].sort((a, b) => a - b)) {
    const members = input.membersByGroup.get(group) ?? []
    if (members.length < floor) continue
    const rings = input.ringsByGroup.get(group)
    // No land, no place. The entities are still drawn; only the region is not.
    if (rings === undefined || rings.length === 0) continue
    const caption = captionFor(rankMembers(members).map((m) => m.label))
    if (caption === null) continue

    const points = members.map((m) => m.position)
    const center = centerOf(points)
    out.push({
      group,
      caption,
      rings,
      memberIds: members.map((m) => m.id).sort(),
      center,
      radius: radiusOf(center, points),
      purity: purityOf(rings, points, input.allPositions)
    })
  }

  return out.sort((a, b) => {
    if (b.memberIds.length !== a.memberIds.length) return b.memberIds.length - a.memberIds.length
    return a.group - b.group
  })
}

/** The territory a point falls in, or null. Territories tile, so at most one. */
export function territoryAt(territories: Territory[], point: AtlasPoint): Territory | null {
  for (const territory of territories) {
    if (coastlineContains(territory.rings, point)) return territory
  }
  return null
}
