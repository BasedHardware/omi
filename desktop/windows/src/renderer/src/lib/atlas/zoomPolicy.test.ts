import { describe, expect, it } from 'vitest'
import {
  DETAIL_ZOOM,
  FOCUS_ZOOM,
  INSPECT_ZOOM,
  MINIMUM_ZOOM,
  NEIGHBOURHOOD_ZOOM,
  SMALL_ATLAS_CEILING,
  canvasLabelZoom,
  departureZoom,
  detailBudget,
  detailLevel,
  fullyLabelledZoom,
  maximumZoom,
  panPreservingCenter,
  zoomToEnter
} from './zoomPolicy'

describe('detailLevel', () => {
  it('climbs through the bands as the camera goes in', () => {
    expect(detailLevel(0.5)).toBe('overview')
    expect(detailLevel(NEIGHBOURHOOD_ZOOM)).toBe('neighbourhood')
    expect(detailLevel(DETAIL_ZOOM)).toBe('detail')
    expect(detailLevel(FOCUS_ZOOM)).toBe('focus')
    expect(detailLevel(INSPECT_ZOOM)).toBe('inspect')
    expect(detailLevel(1000)).toBe('inspect')
  })

  it('has no hysteresis, so the same zoom always shows the same thing', () => {
    // A level that depended on which direction you arrived from would make the
    // map look different at the same magnification.
    const justBelow = NEIGHBOURHOOD_ZOOM - 1e-9
    expect(detailLevel(justBelow)).toBe('overview')
    expect(detailLevel(NEIGHBOURHOOD_ZOOM)).toBe('neighbourhood')
    expect(detailLevel(justBelow)).toBe('overview')
  })
})

describe('detailBudget', () => {
  it('shows more of everything the further in the camera goes', () => {
    const out = detailBudget(0.5, 500)
    const inspect = detailBudget(20, 500)
    expect(inspect.maxNodes).toBeGreaterThan(out.maxNodes)
    expect(inspect.maxEdges).toBeGreaterThan(out.maxEdges)
    expect(inspect.maxLabels).toBeGreaterThan(out.maxLabels)
  })

  it('does not cap labels on a map small enough to read whole', () => {
    // Capping labels on a twelve-entity graph hides things for no reason.
    const budget = detailBudget(0.5, 12)
    expect(budget.maxLabels).toBe(12)
    expect(budget.labelsPerTerritory).toBe(12)
    expect(SMALL_ATLAS_CEILING).toBe(60)
  })

  it('lifts every limit once the camera is past the fully-labelled zoom', () => {
    const nodeCount = 400
    const budget = detailBudget(fullyLabelledZoom(nodeCount), nodeCount)
    expect(budget.maxNodes).toBe(nodeCount)
    expect(budget.maxLabels).toBe(nodeCount)
  })
})

describe('fullyLabelledZoom', () => {
  it('matches the values macOS pins', () => {
    // From MemoryAtlasPerformanceHarnessTests: these are the measured points the
    // ladder was tuned against, so they are the contract rather than a guess.
    expect(fullyLabelledZoom(1)).toBe(16)
    expect(fullyLabelledZoom(1946)).toBe(160)
    expect(fullyLabelledZoom(2400)).toBe(180)
    expect(fullyLabelledZoom(10000)).toBe(360)
  })

  it('never goes below its floor, even for an empty map', () => {
    expect(fullyLabelledZoom(0)).toBe(16)
  })

  it('grows with the square root of the map, not linearly', () => {
    // Four times the entities needs twice the magnification, not four times.
    expect(fullyLabelledZoom(10000) / fullyLabelledZoom(2500)).toBeCloseTo(2, 1)
  })
})

describe('canvasLabelZoom', () => {
  it('matches the values macOS pins', () => {
    expect(canvasLabelZoom(1)).toBe(7.5)
    expect(canvasLabelZoom(1946)).toBe(40)
    expect(canvasLabelZoom(2400)).toBe(45)
    expect(canvasLabelZoom(10000)).toBe(90)
  })
})

describe('maximumZoom', () => {
  it('is tight in the compact card and generous full screen', () => {
    expect(maximumZoom(2400, true)).toBe(NEIGHBOURHOOD_ZOOM)
    expect(maximumZoom(2400, false)).toBe(180)
  })
})

describe('panPreservingCenter', () => {
  it('keeps the point under the middle of the viewport fixed', () => {
    expect(panPreservingCenter(100, 1, 2)).toBe(200)
    expect(panPreservingCenter(200, 2, 1)).toBe(100)
  })

  it('round-trips', () => {
    const there = panPreservingCenter(37, 1.2, 4.4)
    expect(panPreservingCenter(there, 4.4, 1.2)).toBeCloseTo(37, 4)
  })

  it('does not divide by a zoom below the floor', () => {
    expect(Number.isFinite(panPreservingCenter(10, 0, 2))).toBe(true)
  })
})

describe('zoomToEnter', () => {
  it('frames a small region closely and a large one loosely', () => {
    expect(zoomToEnter(0.05, 400)).toBeGreaterThan(zoomToEnter(0.3, 400))
  })

  it('never asks for more magnification than the map allows', () => {
    expect(zoomToEnter(0.0001, 400)).toBeLessThanOrEqual(maximumZoom(400, false))
    expect(zoomToEnter(0.0001, 400, true)).toBeLessThanOrEqual(NEIGHBOURHOOD_ZOOM)
  })

  it('never asks to zoom out past the floor', () => {
    expect(zoomToEnter(10, 400)).toBeGreaterThanOrEqual(MINIMUM_ZOOM)
  })
})

describe('departureZoom', () => {
  it('sits below the zoom you entered at, so a nudge does not eject you', () => {
    const entered = 1.35
    const leave = departureZoom(entered) as number
    expect(leave).toBeLessThan(entered)
    expect(leave).toBeCloseTo(1.35 * 0.85, 12)
  })

  it('is capped at the neighbourhood band however far in you entered', () => {
    expect(departureZoom(50)).toBeCloseTo(NEIGHBOURHOOD_ZOOM * 0.85, 12)
  })

  it('reports no exit rather than one below the floor', () => {
    // Entering at a very low zoom leaves no room to zoom out; inventing a
    // threshold under the minimum would make it unreachable and the region
    // impossible to leave.
    expect(departureZoom(0.8)).toBeNull()
  })
})
