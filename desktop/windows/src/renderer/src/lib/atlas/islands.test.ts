// Coastline extraction.
//
// Clusters are generated from a deterministic sequence, never Math.random: the
// module's contract is that the same input gives the same rings, and a test that
// fed it noise could not tell a real regression from a different roll.
import { describe, expect, it } from 'vitest'
import {
  DECISIVE_MARGIN,
  MAX_REACH,
  SEA_LEVEL,
  blur,
  coastlineContains,
  coastlines,
  influenceReach,
  makeStencil,
  ringArea,
  traceRings,
  type AtlasPoint
} from './islands'

/** Deterministic points around a centre: a phyllotaxis spiral, so the spread is
 *  even and reproducible without a random source. */
const cluster = (cx: number, cy: number, count: number, spread: number): AtlasPoint[] =>
  Array.from({ length: count }, (_v, i) => {
    const angle = i * 2.399963229728653
    const radius = spread * Math.sqrt((i + 0.5) / count)
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
  })

const groups = (entries: Array<[number, AtlasPoint[]]>): Map<number, AtlasPoint[]> =>
  new Map(entries)

describe('influenceReach', () => {
  it('is relative to how spread out the map already is', () => {
    // The same absolute spacing means "tight" on a dense map and "scattered" on
    // a sparse one, so reach cannot be an absolute distance.
    const dense = influenceReach(groups([[0, cluster(0.5, 0.5, 60, 0.05)]]))
    const sparse = influenceReach(groups([[0, cluster(0.5, 0.5, 8, 0.4)]]))
    expect(sparse).toBeGreaterThan(dense)
  })

  it('falls back to the widest reach for a map with one point', () => {
    expect(influenceReach(groups([[0, [{ x: 0.5, y: 0.5 }]]]))).toBe(MAX_REACH)
  })

  it('is not collapsed to zero by two entities at the same coordinate', () => {
    // Nearest-neighbour uses value inequality, so a duplicate does not report a
    // spacing of zero and shrink the reach for the entire map.
    const duplicated = [
      { x: 0.3, y: 0.3 },
      { x: 0.3, y: 0.3 },
      { x: 0.7, y: 0.7 }
    ]
    expect(influenceReach(groups([[0, duplicated]]))).toBeGreaterThan(0)
  })

  it('stays inside its clamp however tightly packed the map is', () => {
    const reach = influenceReach(groups([[0, cluster(0.5, 0.5, 200, 0.001)]]))
    expect(reach).toBeGreaterThanOrEqual(0.006)
    expect(reach).toBeLessThanOrEqual(MAX_REACH)
  })
})

describe('makeStencil', () => {
  it('peaks at exactly one in the centre', () => {
    // SEA_LEVEL is calibrated against this: it sits above 1 precisely so a lone
    // entity's peak cannot clear it.
    const stencil = makeStencil(0.05)
    expect(stencil.values[stencil.radius * stencil.span + stencil.radius]).toBeCloseTo(1, 12)
    expect(SEA_LEVEL).toBeGreaterThan(1)
  })

  it('falls away from the centre', () => {
    const stencil = makeStencil(0.05)
    const centre = stencil.values[stencil.radius * stencil.span + stencil.radius]
    expect(stencil.values[0]).toBeLessThan(centre)
  })
})

describe('blur', () => {
  it('spreads a single lit cell into its neighbours', () => {
    const mask = new Array<number>(128 * 128).fill(0)
    mask[64 * 128 + 64] = 1
    const out = blur(mask)
    expect(out[64 * 128 + 64]).toBeGreaterThan(0)
    expect(out[64 * 128 + 65]).toBeGreaterThan(0)
    expect(out[64 * 128 + 70]).toBe(0)
  })

  it('treats out-of-bounds neighbours as empty rather than wrapping', () => {
    const mask = new Array<number>(128 * 128).fill(0)
    mask[0] = 1
    const out = blur(mask)
    // Wrapping would light the opposite corner, drawing land across the map.
    expect(out[127 * 128 + 127]).toBe(0)
  })
})

describe('ringArea', () => {
  it('measures a square', () => {
    const square = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
      { x: 0, y: 2 }
    ]
    expect(Math.abs(ringArea(square))).toBe(4)
  })

  it('is zero for anything with fewer than three points', () => {
    expect(ringArea([{ x: 0, y: 0 }])).toBe(0)
  })
})

describe('traceRings', () => {
  it('finds nothing in an empty field', () => {
    expect(traceRings(new Array<number>(128 * 128).fill(0))).toEqual([])
  })

  it('discards a chain too short to be a region', () => {
    // Two lit cells at the corner trace an open three-point chain. Keeping it
    // would put a sliver on the map with no interior to fill.
    const mask = new Array<number>(128 * 128).fill(0)
    mask[0] = 1
    mask[1] = 1
    expect(traceRings(mask)).toEqual([])
  })

  it('closes a ring around a solid block', () => {
    const mask = new Array<number>(128 * 128).fill(0)
    for (let r = 40; r < 60; r += 1) for (let c = 40; c < 60; c += 1) mask[r * 128 + c] = 1
    const rings = traceRings(mask)
    expect(rings.length).toBe(1)
    expect(rings[0].length).toBeGreaterThanOrEqual(4)
    expect(Math.abs(ringArea(rings[0]))).toBeGreaterThan(100)
  })
})

describe('coastlines', () => {
  it('gives one community in two places two rings, with sea between them', () => {
    const lobes = [...cluster(0.2, 0.5, 30, 0.06), ...cluster(0.8, 0.5, 30, 0.06)]
    const rings = coastlines(groups([[0, lobes]])).get(0)
    expect(rings?.length).toBe(2)
    // An archipelago is the correct answer for a community that lives in two
    // places; a hull would swallow everything between them.
    expect(coastlineContains(rings ?? [], { x: 0.2, y: 0.5 })).toBe(true)
    expect(coastlineContains(rings ?? [], { x: 0.8, y: 0.5 })).toBe(true)
    expect(coastlineContains(rings ?? [], { x: 0.5, y: 0.5 })).toBe(false)
  })

  it('leaves contested ground as water when two communities interleave', () => {
    const blob = cluster(0.5, 0.5, 40, 0.08)
    const even = blob.filter((_p, i) => i % 2 === 0)
    const odd = blob.filter((_p, i) => i % 2 === 1)
    const result = coastlines(
      groups([
        [0, even],
        [1, odd]
      ])
    )
    for (const probe of [
      { x: 0.5, y: 0.5 },
      { x: 0.46, y: 0.52 },
      { x: 0.54, y: 0.48 }
    ]) {
      // Neither community is decisive here, so neither owns it. Awarding it to
      // one would draw a territory over the other's entities.
      expect(coastlineContains(result.get(0) ?? [], probe)).toBe(false)
      expect(coastlineContains(result.get(1) ?? [], probe)).toBe(false)
    }
  })

  it('gives each community its own centre once they are pulled apart', () => {
    const result = coastlines(
      groups([
        [0, cluster(0.28, 0.5, 20, 0.05)],
        [1, cluster(0.72, 0.5, 20, 0.05)]
      ])
    )
    expect(coastlineContains(result.get(0) ?? [], { x: 0.28, y: 0.5 })).toBe(true)
    expect(coastlineContains(result.get(1) ?? [], { x: 0.72, y: 0.5 })).toBe(true)
    expect(coastlineContains(result.get(0) ?? [], { x: 0.5, y: 0.5 })).toBe(false)
    expect(coastlineContains(result.get(1) ?? [], { x: 0.5, y: 0.5 })).toBe(false)
  })

  it('gives a lone entity no land at all', () => {
    // A single bump peaks at exactly 1 and the sea level is above it, so one
    // entity can never mint a territory.
    expect(coastlines(groups([[0, [{ x: 0.5, y: 0.5 }]]])).get(0)).toBeUndefined()
  })

  it('gives scattered entities no land, but a cluster on the same map does get some', () => {
    const scattered = Array.from({ length: 8 }, (_v, i) => ({
      x: 0.1 + 0.1 * i,
      y: 0.15 + 0.09 * i
    }))
    const result = coastlines(
      groups([
        [0, scattered],
        [1, cluster(0.75, 0.3, 20, 0.04)]
      ])
    )
    // "Scattered" is relative to the map's own spacing, which is why both are
    // measured on the same map rather than in isolation.
    expect(result.get(0)).toBeUndefined()
    expect(result.get(1)).toBeDefined()
  })

  it('drops an island too small to be worth drawing', () => {
    // Two entities almost on top of each other do clear the sea level together,
    // but the land they make is a speck; the area floor is what keeps specks off
    // the map. The wider pair, on the same map, survives it.
    const pair = (gap: number): Map<number, AtlasPoint[]> =>
      groups([
        [
          0,
          [
            { x: 0.5 - gap / 2, y: 0.5 },
            { x: 0.5 + gap / 2, y: 0.5 }
          ]
        ]
      ])
    expect(coastlines(pair(0.006)).get(0)).toBeUndefined()
    expect(coastlines(pair(0.01)).get(0)).toBeDefined()
  })

  it('returns exactly the same rings for the same input', () => {
    const input = (): Map<number, AtlasPoint[]> =>
      groups([
        [0, cluster(0.3, 0.3, 25, 0.06)],
        [1, cluster(0.7, 0.7, 25, 0.06)]
      ])
    expect(coastlines(input())).toEqual(coastlines(input()))
  })

  it('does not depend on the order communities were inserted in', () => {
    const a = cluster(0.3, 0.3, 25, 0.06)
    const b = cluster(0.7, 0.7, 25, 0.06)
    const forward = coastlines(
      groups([
        [0, a],
        [1, b]
      ])
    )
    const backward = coastlines(
      groups([
        [1, b],
        [0, a]
      ])
    )
    expect(backward.get(0)).toEqual(forward.get(0))
    expect(backward.get(1)).toEqual(forward.get(1))
  })

  it('never gives one point to two communities', () => {
    const result = coastlines(
      groups([
        [0, cluster(0.25, 0.25, 25, 0.07)],
        [1, cluster(0.75, 0.25, 25, 0.07)],
        [2, cluster(0.5, 0.75, 25, 0.07)]
      ])
    )
    // Territories must tile. A point owned twice draws two labels over the same
    // ground and makes the map unreadable.
    for (let i = 0; i <= 40; i += 1) {
      for (let j = 0; j <= 40; j += 1) {
        const probe = { x: i / 40, y: j / 40 }
        const owners = [...result.values()].filter((rings) => coastlineContains(rings, probe))
        expect(owners.length).toBeLessThanOrEqual(1)
      }
    }
  })

  it('skips a community with no members rather than giving it an empty entry', () => {
    const result = coastlines(
      groups([
        [0, cluster(0.5, 0.5, 25, 0.06)],
        [1, []]
      ])
    )
    expect(result.has(1)).toBe(false)
  })

  it('needs a decisive margin, not just a lead', () => {
    expect(DECISIVE_MARGIN).toBeGreaterThan(1)
  })
})

describe('coastlineContains', () => {
  const square = (x: number, y: number, size: number): AtlasPoint[] => [
    { x, y },
    { x: x + size, y },
    { x: x + size, y: y + size },
    { x, y: y + size }
  ]

  it('reads a ring inside another as a hole', () => {
    // Even-odd, not nonzero: an enclave belongs to whoever is inside it, not to
    // the territory that surrounds it.
    const withHole = [square(0, 0, 10), square(3, 3, 4)]
    expect(coastlineContains(withHole, { x: 1, y: 5 })).toBe(true)
    expect(coastlineContains(withHole, { x: 5, y: 5 })).toBe(false)
  })

  it('is false outside every ring', () => {
    expect(coastlineContains([square(0, 0, 2)], { x: 9, y: 9 })).toBe(false)
  })

  it('ignores a degenerate ring', () => {
    expect(coastlineContains([[{ x: 0, y: 0 }]], { x: 0, y: 0 })).toBe(false)
  })
})
