import { describe, expect, it } from 'vitest'
import {
  CAPTION_CEILING,
  TERRITORY_MIN_MEMBERS,
  buildTerritories,
  captionFor,
  centerOf,
  purityOf,
  radiusOf,
  rankMembers,
  territoryAt,
  territorySizeFloor,
  type AtlasMember
} from './territories'
import type { AtlasPoint, Ring } from './islands'

const member = (id: string, label: string, degree: number, x = 0.5, y = 0.5): AtlasMember => ({
  id,
  label,
  degree,
  position: { x, y }
})

const square = (x: number, y: number, size: number): Ring => [
  { x, y },
  { x: x + size, y },
  { x: x + size, y: y + size },
  { x, y: y + size }
]

describe('territorySizeFloor', () => {
  it('never lets a pair of entities become a region', () => {
    expect(territorySizeFloor(10)).toBe(TERRITORY_MIN_MEMBERS)
    expect(territorySizeFloor(0)).toBe(TERRITORY_MIN_MEMBERS)
  })

  it('scales with the map so a big map does not fill with tiny regions', () => {
    expect(territorySizeFloor(1000)).toBe(15)
  })
})

describe('captionFor', () => {
  it('prefers a short unwordy label', () => {
    expect(captionFor(['A rather long-winded description of things', 'Acme'])).toBe('Acme')
  })

  it('takes the first ranked candidate, not the shortest', () => {
    // Ranking is by connectedness; the best-connected entity is what the region
    // is about, and picking the shortest name instead would label a region after
    // an incidental member.
    expect(captionFor(['Acme', 'Bob'])).toBe('Acme')
  })

  it('falls back to a short but wordy label when nothing tidier exists', () => {
    expect(captionFor(['the third quarter plan'])).toBe('the third quarter plan')
  })

  it('truncates a label too long to be a name', () => {
    const long = 'Something far too long to sit on a map as a place name'
    const caption = captionFor([long]) as string
    expect(caption.length).toBeLessThanOrEqual(CAPTION_CEILING)
    expect(caption.endsWith('…')).toBe(true)
    expect(caption.startsWith('Something far too long')).toBe(true)
  })

  it('does not leave a dangling space before the ellipsis', () => {
    // "Quarterly planning" is 18 characters and the cut falls at 25, landing in
    // the run of spaces after it; without the trim the caption would read
    // "Quarterly planning       …".
    expect(captionFor(['Quarterly planning       review of everything'])).toBe(
      'Quarterly planning…'
    )
  })

  it('keeps a truncation that lands mid-word rather than inventing a break', () => {
    // Cutting back to the previous word boundary would sometimes lose the only
    // distinguishing part of the label, so the cut is where it falls.
    expect(captionFor(['Quarterly planning and review notes'])).toBe('Quarterly planning and re…')
  })

  it('returns null when there is nothing to call the place', () => {
    expect(captionFor([])).toBeNull()
    expect(captionFor(['', '   '])).toBeNull()
  })
})

describe('rankMembers', () => {
  it('ranks the best connected first', () => {
    const ranked = rankMembers([member('a', 'Alpha', 1), member('b', 'Beta', 9)])
    expect(ranked.map((m) => m.id)).toEqual(['b', 'a'])
  })

  it('breaks a degree tie on the label, case-insensitively', () => {
    const ranked = rankMembers([member('a', 'zeta', 5), member('b', 'Alpha', 5)])
    expect(ranked.map((m) => m.label)).toEqual(['Alpha', 'zeta'])
  })

  it('breaks a full tie on id so the name does not depend on input order', () => {
    const forward = rankMembers([member('z', 'Same', 1), member('a', 'Same', 1)])
    const reversed = rankMembers([member('a', 'Same', 1), member('z', 'Same', 1)])
    expect(reversed.map((m) => m.id)).toEqual(forward.map((m) => m.id))
    expect(forward.map((m) => m.id)).toEqual(['a', 'z'])
  })
})

describe('centerOf and radiusOf', () => {
  it('centres on the mean', () => {
    expect(
      centerOf([
        { x: 0, y: 0 },
        { x: 1, y: 1 }
      ])
    ).toEqual({ x: 0.5, y: 0.5 })
  })

  it('ignores one far-flung member when measuring reach', () => {
    const tight: AtlasPoint[] = Array.from({ length: 10 }, (_v, i) => ({
      x: 0.5 + i * 0.001,
      y: 0.5
    }))
    const withOutlier = [...tight, { x: 0.99, y: 0.99 }]
    // An 80th-percentile radius keeps the label over the body of the region
    // rather than halfway to a stray member.
    expect(radiusOf({ x: 0.5, y: 0.5 }, withOutlier)).toBeLessThan(0.1)
  })

  it('floors the radius so a tight cluster still has room for a label', () => {
    expect(radiusOf({ x: 0.5, y: 0.5 }, [{ x: 0.5, y: 0.5 }])).toBe(0.01)
  })
})

describe('purityOf', () => {
  it('is one when only the community stands inside its own coastline', () => {
    const rings = [square(0, 0, 1)]
    const members = [{ x: 0.5, y: 0.5 }]
    expect(purityOf(rings, members, [...members, { x: 5, y: 5 }])).toBe(1)
  })

  it('falls when the coastline swallows other entities', () => {
    const rings = [square(0, 0, 1)]
    const members = [{ x: 0.2, y: 0.2 }]
    const everyone = [...members, { x: 0.8, y: 0.8 }]
    expect(purityOf(rings, members, everyone)).toBe(0.5)
  })

  it('is zero when nothing is inside at all', () => {
    expect(purityOf([square(0, 0, 1)], [], [{ x: 9, y: 9 }])).toBe(0)
  })
})

describe('buildTerritories', () => {
  const members = (group: string, count: number, x: number, y: number): AtlasMember[] =>
    Array.from({ length: count }, (_v, i) =>
      member(`${group}${i}`, i === 0 ? `${group} hub` : `${group}${i}`, i === 0 ? 9 : 1, x, y)
    )

  it('builds a named territory from a big enough community with land', () => {
    const built = buildTerritories({
      membersByGroup: new Map([[0, members('work', 8, 0.3, 0.3)]]),
      ringsByGroup: new Map([[0, [square(0.2, 0.2, 0.2)]]]),
      allPositions: members('work', 8, 0.3, 0.3).map((m) => m.position)
    })
    expect(built.length).toBe(1)
    expect(built[0].caption).toBe('work hub')
    expect(built[0].memberIds.length).toBe(8)
    expect(built[0].purity).toBe(1)
  })

  it('drops a community with no coastline', () => {
    // No land, no place. The entities are still drawn; only the region is not.
    const built = buildTerritories({
      membersByGroup: new Map([[0, members('work', 8, 0.3, 0.3)]]),
      ringsByGroup: new Map(),
      allPositions: []
    })
    expect(built).toEqual([])
  })

  it('drops a community too small to be a region', () => {
    const built = buildTerritories({
      membersByGroup: new Map([[0, members('work', 3, 0.3, 0.3)]]),
      ringsByGroup: new Map([[0, [square(0.2, 0.2, 0.2)]]]),
      allPositions: members('work', 3, 0.3, 0.3).map((m) => m.position)
    })
    expect(built).toEqual([])
  })

  it('drops a community nothing in it can name', () => {
    // An unnamed shape on a map is noise; the entities inside it are still
    // visible as entities.
    const unnamed = Array.from({ length: 8 }, (_v, i) => member(`n${i}`, '   ', 1, 0.3, 0.3))
    const built = buildTerritories({
      membersByGroup: new Map([[0, unnamed]]),
      ringsByGroup: new Map([[0, [square(0.2, 0.2, 0.2)]]]),
      allPositions: unnamed.map((m) => m.position)
    })
    expect(built).toEqual([])
  })

  it('orders the biggest region first', () => {
    const built = buildTerritories({
      membersByGroup: new Map([
        [0, members('small', 6, 0.2, 0.2)],
        [1, members('big', 12, 0.8, 0.8)]
      ]),
      ringsByGroup: new Map([
        [0, [square(0.1, 0.1, 0.2)]],
        [1, [square(0.7, 0.7, 0.2)]]
      ]),
      allPositions: [
        ...members('small', 6, 0.2, 0.2).map((m) => m.position),
        ...members('big', 12, 0.8, 0.8).map((m) => m.position)
      ]
    })
    expect(built.map((t) => t.caption)).toEqual(['big hub', 'small hub'])
  })
})

describe('territoryAt', () => {
  it('finds the region a point falls in', () => {
    const territories = buildTerritories({
      membersByGroup: new Map([
        [0, Array.from({ length: 8 }, (_v, i) => member(`n${i}`, 'Acme', 1, 0.3, 0.3))]
      ]),
      ringsByGroup: new Map([[0, [square(0.2, 0.2, 0.2)]]]),
      allPositions: Array.from({ length: 8 }, () => ({ x: 0.3, y: 0.3 }))
    })
    expect(territoryAt(territories, { x: 0.3, y: 0.3 })?.caption).toBe('Acme')
    expect(territoryAt(territories, { x: 0.9, y: 0.9 })).toBeNull()
  })
})
