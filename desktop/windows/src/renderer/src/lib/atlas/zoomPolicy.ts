// What the atlas shows at each zoom.
//
// Ported from macOS `MemoryAtlasZoomPolicy.swift` and the detail ladder in
// `CanonicalMemoryAtlasView`. The map holds far more than can be drawn legibly at
// once, so the answer to "what is on screen" is a function of how far in the
// camera is: territories and a handful of hubs when zoomed out, every entity and
// every label when zoomed all the way in.
//
// There is deliberately NO hysteresis on the bands. They are plain comparisons
// against the live zoom, so the same zoom always shows the same thing - a level
// that depended on which direction you arrived from would make the map look
// different at the same magnification.

export type DetailLevel = 'overview' | 'neighbourhood' | 'detail' | 'focus' | 'inspect'

/** Band boundaries. A zoom below the first is overview; at or above the last is
 *  inspect. */
export const NEIGHBOURHOOD_ZOOM = 1.35
export const DETAIL_ZOOM = 1.9
export const FOCUS_ZOOM = 3.2
export const INSPECT_ZOOM = 7.5
export const MINIMUM_ZOOM = 0.75
/** A map this small is legible whole, so it skips the density limits. */
export const SMALL_ATLAS_CEILING = 60

export function detailLevel(zoom: number): DetailLevel {
  if (zoom < NEIGHBOURHOOD_ZOOM) return 'overview'
  if (zoom < DETAIL_ZOOM) return 'neighbourhood'
  if (zoom < FOCUS_ZOOM) return 'detail'
  if (zoom < INSPECT_ZOOM) return 'focus'
  return 'inspect'
}

export interface DetailBudget {
  /** Entities drawn. */
  maxNodes: number
  /** Connections drawn. */
  maxEdges: number
  /** Labels per territory. */
  labelsPerTerritory: number
  /** Labels on screen in total. */
  maxLabels: number
}

const BUDGETS: Record<DetailLevel, DetailBudget> = {
  overview: { maxNodes: 1200, maxEdges: 2000, labelsPerTerritory: 3, maxLabels: 12 },
  neighbourhood: { maxNodes: 1600, maxEdges: 2400, labelsPerTerritory: 7, maxLabels: 24 },
  detail: { maxNodes: 2400, maxEdges: 3000, labelsPerTerritory: 11, maxLabels: 36 },
  focus: { maxNodes: 3200, maxEdges: 3600, labelsPerTerritory: 24, maxLabels: 72 },
  inspect: { maxNodes: 3200, maxEdges: 4200, labelsPerTerritory: 96, maxLabels: 96 }
}

/**
 * What may be drawn at this zoom.
 *
 * A map small enough to read whole gets no label limits at all: capping labels
 * on a twelve-entity graph hides things for no reason.
 */
export function detailBudget(zoom: number, nodeCount: number): DetailBudget {
  const level = detailLevel(zoom)
  const budget = BUDGETS[level]
  if (nodeCount <= SMALL_ATLAS_CEILING) {
    return { ...budget, labelsPerTerritory: nodeCount, maxLabels: nodeCount }
  }
  if (zoom >= fullyLabelledZoom(nodeCount)) {
    return { ...budget, maxNodes: nodeCount, labelsPerTerritory: nodeCount, maxLabels: nodeCount }
  }
  return budget
}

/**
 * The zoom at which everything is labelled, scaled by how much there is.
 *
 * Denser maps need more magnification before every label fits, so this grows
 * with the square root of the entity count rather than being a fixed number.
 */
export function fullyLabelledZoom(nodeCount: number): number {
  return Math.max(16, Math.ceil((Math.sqrt(Math.max(nodeCount, 1)) * 3.6) / 5) * 5)
}

/** Beyond this, labels are cheaper drawn straight onto the canvas than as
 *  individually laid out elements. */
export function canvasLabelZoom(nodeCount: number): number {
  return Math.max(7.5, Math.ceil(fullyLabelledZoom(nodeCount) * 0.25 * 2) / 2)
}

/** How far the camera may go in. */
export function maximumZoom(nodeCount: number, compact: boolean): number {
  return compact ? NEIGHBOURHOOD_ZOOM : fullyLabelledZoom(nodeCount)
}

/** Keeps the point under the centre of the viewport fixed while zooming. */
export function panPreservingCenter(pan: number, currentZoom: number, nextZoom: number): number {
  return pan * (nextZoom / Math.max(currentZoom, MINIMUM_ZOOM))
}

/** Share of the viewport a territory fills when you enter it. */
export const ENTERED_COVERAGE = 0.62

/** The zoom that frames a territory of this radius. */
export function zoomToEnter(radius: number, nodeCount: number, compact = false): number {
  const extent = Math.max(radius * 2, 0.02)
  const desired = ENTERED_COVERAGE / extent
  return Math.min(Math.max(desired, MINIMUM_ZOOM), maximumZoom(nodeCount, compact))
}

/**
 * The zoom at which leaving a territory takes effect, or null when there is no
 * zoom-out that exits it.
 *
 * This is the one piece of stickiness in the whole policy: without it, nudging
 * the camera a hair past the band boundary would drop you out of the region you
 * just entered.
 */
export function departureZoom(enteredZoom: number): number | null {
  const threshold = Math.min(enteredZoom, NEIGHBOURHOOD_ZOOM) * 0.85
  // Below the floor there is nothing to zoom out TO, so there is no exit rather
  // than an exit nobody can reach.
  return threshold < MINIMUM_ZOOM ? null : threshold
}
