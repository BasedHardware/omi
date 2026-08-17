// Turning a set of positioned entities into coastlines.
//
// Ported from macOS `MemoryAtlasIslands.swift`. Each community's members are
// splatted as Gaussian bumps into a shared 128x128 scalar field; a cell belongs
// to whichever community peaks highest there, provided the peak is decisive; the
// resulting mask is blurred and traced with marching squares into closed rings.
//
// That indirection is the whole point. A convex hull round a community's members
// would swallow every other community standing between them; a field lets two
// interleaved communities own nothing in the contested middle, which is the
// honest answer.
//
// Three constants carry most of the behaviour:
//
//   seaLevel 1.1        A single entity's bump peaks at exactly 1.0, so a lone
//                       entity can never mint a territory. Above 1 is deliberate.
//   decisiveMargin 1.25 A cell only belongs to the leader if it beats the runner
//                       up by a quarter, so contested ground stays water.
//   reach               NOT an absolute distance: the median nearest-neighbour
//                       distance of the whole map times 2.5. "Spread out" is
//                       relative to how spread out everything else is.

/** A point in normalised atlas space, roughly 0..1 on both axes. */
export interface AtlasPoint {
  x: number
  y: number
}

/** A closed ring of points in normalised atlas space. */
export type Ring = AtlasPoint[]

export const FIELD_RESOLUTION = 128
export const FIELD_MARGIN = 0.08
/** A lone entity peaks at exactly 1.0, so this being above 1 is what stops one
 *  entity from minting a territory of its own. */
export const SEA_LEVEL = 1.1
/** The leader must beat the runner up by this factor to own a cell. */
export const DECISIVE_MARGIN = 1.25
/** Rings smaller than this share of the field are dropped. */
export const SMALLEST_ISLAND = 0.0008
/** Reach is clamped into this band however tightly or loosely packed the map is. */
export const MIN_REACH = 0.006
export const MAX_REACH = 0.2
/** Nearest-neighbour samples taken when measuring the map's typical spacing. */
export const REACH_SAMPLES = 300

const CELLS = FIELD_RESOLUTION * FIELD_RESOLUTION
const SCALE = (FIELD_RESOLUTION - 1) / (1 + 2 * FIELD_MARGIN)

const column = (x: number): number => Math.round((x + FIELD_MARGIN) * SCALE)
const row = (y: number): number => Math.round((y + FIELD_MARGIN) * SCALE)
const unscale = (grid: number): number => grid / SCALE - FIELD_MARGIN

/**
 * The map's own sense of "close": the median distance from a point to its
 * nearest other point, times 2.5, clamped.
 *
 * Relative rather than absolute because a map of eight entities and a map of
 * eight hundred are laid out in the same unit square. An absolute radius would
 * make the first all sea and the second all land.
 */
export function influenceReach(pointsByGroup: Map<number, AtlasPoint[]>): number {
  const points: AtlasPoint[] = []
  for (const group of [...pointsByGroup.keys()].sort((a, b) => a - b)) {
    points.push(...(pointsByGroup.get(group) ?? []))
  }
  if (points.length <= 1) return MAX_REACH

  const stride = Math.max(1, Math.floor(points.length / REACH_SAMPLES))
  const gaps: number[] = []
  for (let i = 0; i < points.length; i += stride) {
    let nearest = Number.POSITIVE_INFINITY
    for (const other of points) {
      // Value inequality, not identity: exact duplicates are skipped, so two
      // entities at the same coordinate do not report a spacing of zero and
      // collapse the reach for the whole map.
      if (other.x === points[i].x && other.y === points[i].y) continue
      const dx = other.x - points[i].x
      const dy = other.y - points[i].y
      const distance = Math.sqrt(dx * dx + dy * dy)
      if (distance < nearest) nearest = distance
    }
    if (Number.isFinite(nearest)) gaps.push(nearest)
  }
  if (gaps.length === 0) return MAX_REACH
  gaps.sort((a, b) => a - b)
  const typical = gaps[Math.floor(gaps.length / 2)] * 2.5
  return Math.min(Math.max(typical, MIN_REACH), MAX_REACH)
}

interface Stencil {
  radius: number
  span: number
  values: number[]
}

/** The Gaussian bump one entity contributes, precomputed once. Its centre value
 *  is exactly 1, which is what SEA_LEVEL is calibrated against. */
export function makeStencil(reach: number): Stencil {
  const radius = Math.max(1, Math.round(3 * reach * SCALE))
  const span = 2 * radius + 1
  const values = new Array<number>(span * span).fill(0)
  for (let r = 0; r < span; r += 1) {
    for (let c = 0; c < span; c += 1) {
      const dx = (c - radius) / SCALE
      const dy = (r - radius) / SCALE
      values[r * span + c] = Math.exp(-(dx * dx + dy * dy) / (2 * reach * reach))
    }
  }
  return { radius, span, values }
}

/** Separable [1,2,1]/4 blur. Out-of-bounds neighbours count as zero, so the
 *  field falls off at the edge rather than wrapping. */
export function blur(mask: number[]): number[] {
  const pass = new Array<number>(CELLS).fill(0)
  const out = new Array<number>(CELLS).fill(0)
  for (let r = 0; r < FIELD_RESOLUTION; r += 1) {
    for (let c = 0; c < FIELD_RESOLUTION; c += 1) {
      const left = c > 0 ? mask[r * FIELD_RESOLUTION + c - 1] : 0
      const right = c < FIELD_RESOLUTION - 1 ? mask[r * FIELD_RESOLUTION + c + 1] : 0
      pass[r * FIELD_RESOLUTION + c] = (left + 2 * mask[r * FIELD_RESOLUTION + c] + right) / 4
    }
  }
  for (let r = 0; r < FIELD_RESOLUTION; r += 1) {
    for (let c = 0; c < FIELD_RESOLUTION; c += 1) {
      const below = r > 0 ? pass[(r - 1) * FIELD_RESOLUTION + c] : 0
      const above = r < FIELD_RESOLUTION - 1 ? pass[(r + 1) * FIELD_RESOLUTION + c] : 0
      out[r * FIELD_RESOLUTION + c] = (below + 2 * pass[r * FIELD_RESOLUTION + c] + above) / 4
    }
  }
  return out
}

const horizontalEdge = (r: number, c: number): number => r * FIELD_RESOLUTION + c
const verticalEdge = (r: number, c: number): number => CELLS + r * FIELD_RESOLUTION + c

/**
 * Marching squares at 0.5.
 *
 * Edge identity is an INTEGER, not a coordinate. Stitching segments by integer
 * equality is what closes a ring exactly; comparing interpolated coordinates
 * leaves hairline gaps wherever two cells disagree in the last bit.
 */
export function traceRings(mask: number[]): Ring[] {
  const points = new Map<number, AtlasPoint>()
  const links = new Map<number, number[]>()
  const connect = (p: number, q: number): void => {
    const a = links.get(p)
    if (a === undefined) links.set(p, [q])
    else a.push(q)
    const b = links.get(q)
    if (b === undefined) links.set(q, [p])
    else b.push(p)
  }
  const cross = (a: number, b: number): number => (0.5 - a) / (b - a)

  for (let r = 0; r < FIELD_RESOLUTION - 1; r += 1) {
    for (let c = 0; c < FIELD_RESOLUTION - 1; c += 1) {
      const bl = mask[r * FIELD_RESOLUTION + c]
      const br = mask[r * FIELD_RESOLUTION + c + 1]
      const tr = mask[(r + 1) * FIELD_RESOLUTION + c + 1]
      const tl = mask[(r + 1) * FIELD_RESOLUTION + c]
      const code =
        (bl >= 0.5 ? 1 : 0) | (br >= 0.5 ? 2 : 0) | (tr >= 0.5 ? 4 : 0) | (tl >= 0.5 ? 8 : 0)
      if (code === 0 || code === 15) continue

      // Each crossing point is created ONLY for an edge the contour actually
      // crosses. Computing all four up front divides by zero on an edge whose
      // ends sit on the same side of the level.
      //
      // That NaN turns out to be unreachable rather than dangerous: the two
      // cells sharing an edge read the same two corner values for it, so they
      // always agree on whether the contour crosses it, and a case never
      // references an edge its own corners say is uncrossed. Kept lazy anyway,
      // because a map holding NaN that nothing happens to read is one refactor
      // away from being a map holding NaN that something does.
      const bottom = (): number => {
        const id = horizontalEdge(r, c)
        if (!points.has(id)) points.set(id, { x: c + cross(bl, br), y: r })
        return id
      }
      const top = (): number => {
        const id = horizontalEdge(r + 1, c)
        if (!points.has(id)) points.set(id, { x: c + cross(tl, tr), y: r + 1 })
        return id
      }
      const left = (): number => {
        const id = verticalEdge(r, c)
        if (!points.has(id)) points.set(id, { x: c, y: r + cross(bl, tl) })
        return id
      }
      const right = (): number => {
        const id = verticalEdge(r, c + 1)
        if (!points.has(id)) points.set(id, { x: c + 1, y: r + cross(br, tr) })
        return id
      }

      switch (code) {
        case 1:
        case 14:
          connect(left(), bottom())
          break
        case 2:
        case 13:
          connect(bottom(), right())
          break
        case 3:
        case 12:
          connect(left(), right())
          break
        case 4:
        case 11:
          connect(right(), top())
          break
        case 6:
        case 9:
          connect(bottom(), top())
          break
        case 7:
        case 8:
          connect(left(), top())
          break
        case 5:
          // Ambiguous: the cell's average decides which way the two strands run,
          // so neighbouring saddles agree and the rings stay closed.
          if ((bl + br + tr + tl) / 4 >= 0.5) {
            connect(left(), top())
            connect(bottom(), right())
          } else {
            connect(left(), bottom())
            connect(right(), top())
          }
          break
        case 10:
          if ((bl + br + tr + tl) / 4 >= 0.5) {
            connect(left(), bottom())
            connect(right(), top())
          } else {
            connect(left(), top())
            connect(bottom(), right())
          }
          break
        default:
          break
      }
    }
  }

  const visited = new Set<number>()
  const rings: Ring[] = []
  for (const start of [...links.keys()].sort((a, b) => a - b)) {
    if (visited.has(start)) continue
    const ring: Ring = []
    let current: number | undefined = start
    let previous: number | undefined
    while (current !== undefined && !visited.has(current)) {
      visited.add(current)
      const point = points.get(current)
      if (point !== undefined) ring.push(point)
      const next: number | undefined = (links.get(current) ?? []).find(
        (candidate) => candidate !== previous && !visited.has(candidate)
      )
      previous = current
      current = next
    }
    // Fewer than four points is a sliver, not a region.
    if (ring.length >= 4) rings.push(ring)
  }
  return rings
}

/** Shoelace area over grid coordinates. Sign carries winding, so callers take
 *  the absolute value. */
export function ringArea(ring: Ring): number {
  if (ring.length < 3) return 0
  let total = 0
  for (let i = 0; i < ring.length; i += 1) {
    const a = ring[i]
    const b = ring[(i + 1) % ring.length]
    total += a.x * b.y - b.x * a.y
  }
  return total / 2
}

/**
 * Coastlines per community.
 *
 * EVERY competing community must be passed in, including ones the map will never
 * name. Omitting one hands its land to whichever named community is nearest,
 * which draws a territory over entities that do not belong to it.
 *
 * A community with no surviving ring gets no entry at all; the caller drops it.
 */
export function coastlines(pointsByGroup: Map<number, AtlasPoint[]>): Map<number, Ring[]> {
  const groups = [...pointsByGroup.keys()].sort((a, b) => a - b)
  const reach = influenceReach(pointsByGroup)
  const stencil = makeStencil(reach)

  const best = new Array<number>(CELLS).fill(0)
  const runnerUp = new Array<number>(CELLS).fill(0)
  const owner = new Array<number>(CELLS).fill(-1)
  const field = new Array<number>(CELLS).fill(0)

  for (const group of groups) {
    const members = pointsByGroup.get(group)
    if (members === undefined || members.length === 0) continue
    const touched: number[] = []
    for (const member of members) {
      const centreCol = column(member.x)
      const centreRow = row(member.y)
      for (let r = 0; r < stencil.span; r += 1) {
        const gridRow = centreRow - stencil.radius + r
        if (gridRow < 0 || gridRow >= FIELD_RESOLUTION) continue
        for (let c = 0; c < stencil.span; c += 1) {
          const gridCol = centreCol - stencil.radius + c
          if (gridCol < 0 || gridCol >= FIELD_RESOLUTION) continue
          const index = gridRow * FIELD_RESOLUTION + gridCol
          if (field[index] === 0) touched.push(index)
          field[index] += stencil.values[r * stencil.span + c]
        }
      }
    }
    for (const index of touched) {
      const value = field[index]
      // Strict `>` plus the sorted group walk means the LOWEST group id wins a
      // tie. That rule cannot be observed in the output today: a cell where two
      // communities peak at exactly the same value has best == runnerUp, so it
      // fails the decisive margin below and becomes water whichever community is
      // recorded as its owner. It is written this way so the ownership array is
      // still well defined, and so relaxing the margin later cannot silently
      // start awarding tied ground to whichever community happened to be
      // processed last.
      if (value > best[index]) {
        runnerUp[index] = best[index]
        best[index] = value
        owner[index] = group
      } else if (value > runnerUp[index]) {
        runnerUp[index] = value
      }
      field[index] = 0
    }
  }

  const floor = SMALLEST_ISLAND * CELLS
  const result = new Map<number, Ring[]>()
  for (const group of groups) {
    const members = pointsByGroup.get(group)
    if (members === undefined || members.length === 0) continue
    const mask = new Array<number>(CELLS).fill(0)
    for (let i = 0; i < CELLS; i += 1) {
      mask[i] =
        owner[i] === group && best[i] >= SEA_LEVEL && best[i] >= runnerUp[i] * DECISIVE_MARGIN
          ? 1
          : 0
    }
    const rings = traceRings(blur(mask))
      .filter((ring) => Math.abs(ringArea(ring)) >= floor)
      .map((ring) => ring.map((p) => ({ x: unscale(p.x), y: unscale(p.y) })))
    if (rings.length > 0) result.set(group, rings)
  }
  return result
}

/**
 * Even-odd ray cast across ALL rings of a territory, so a ring enclosed by
 * another reads as a hole rather than as more land.
 */
export function coastlineContains(rings: Ring[], point: AtlasPoint): boolean {
  let inside = false
  for (const ring of rings) {
    if (ring.length < 3) continue
    for (let i = 0; i < ring.length; i += 1) {
      const current = ring[i]
      const previous = ring[(i + ring.length - 1) % ring.length]
      if (current.y > point.y !== previous.y > point.y) {
        const t = (point.y - current.y) / (previous.y - current.y)
        if (point.x < current.x + t * (previous.x - current.x)) inside = !inside
      }
    }
  }
  return inside
}
