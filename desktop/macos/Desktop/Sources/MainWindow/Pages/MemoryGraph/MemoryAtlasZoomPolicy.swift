import CoreGraphics

enum MemoryAtlasZoomPolicy {
  /// At or below this entity count the whole atlas fits on one screen, so the
  /// density budgets tuned for thousands of entities stop being a kindness and
  /// start being the reason the page looks empty.
  static let smallAtlasCeiling = 60
  static let minimumZoom: CGFloat = 0.75
  /// Where reading the map as a whole ends and reading one part of it begins.
  /// Named because four places were deciding it independently with the same
  /// literal, and one of them now also decides whether the user is still
  /// inside a neighbourhood.
  static let neighborhoodZoom: CGFloat = 1.35
  static let compactMaximumZoom: CGFloat = 1.35
  static let focusModeZoom: CGFloat = 3.2
  static let inspectModeZoom: CGFloat = 7.5
  static let focusTargetZoom: CGFloat = 4

  /// The final inspection level needs enough screen-space for every entity to
  /// have a readable label. A square-root curve tracks the area required by a
  /// larger graph: four times as many entities need roughly twice the zoom.
  /// This intentionally has no arbitrary product ceiling, so a growing memory
  /// graph always has a reachable all-labelled state.
  static func fullyLabelledZoom(nodeCount: Int) -> CGFloat {
    // Labels need substantially more room than dots. The 3.6x factor comes
    // from the label footprint rather than node radius, then rounds to a
    // usable 500% increment for the zoom control. This yields 16,000% for
    // the sampled ~1,946-entity graph, leaving dense constellations legible.
    let densityScaledZoom = ceil(sqrt(CGFloat(max(nodeCount, 1))) * 3.6 / 5) * 5
    return max(16, densityScaledZoom)
  }

  /// Begins Canvas-based labels before the final all-labelled state. This uses
  /// the same density curve as the maximum zoom, so a larger memory graph
  /// earns more room before every visible dot is named. At this level Canvas
  /// draws labels only for nodes inside the current viewport; it never creates
  /// a SwiftUI label view per entity.
  static func automaticCanvasLabelZoom(nodeCount: Int) -> CGFloat {
    let threshold = fullyLabelledZoom(nodeCount: nodeCount) * 0.25
    return max(inspectModeZoom, ceil(threshold * 2) / 2)
  }

  static func maximumZoom(nodeCount: Int, compact: Bool) -> CGFloat {
    compact ? compactMaximumZoom : fullyLabelledZoom(nodeCount: nodeCount)
  }

  static func panPreservingCenterZoom(
    _ pan: CGSize,
    from currentZoom: CGFloat,
    to nextZoom: CGFloat
  ) -> CGSize {
    let ratio = nextZoom / max(currentZoom, minimumZoom)
    return CGSize(width: pan.width * ratio, height: pan.height * ratio)
  }

  /// Camera that frames a selected entity and the neighbours currently
  /// highlighted with it. A lone node keeps the crosshair's tight focus zoom;
  /// a connected set uses the same coverage rule as entering a neighbourhood
  /// so every highlighted mark stays on screen.
  static func focusedNeighborhood(
    positions: [CGPoint],
    viewport: CGSize,
    currentZoom: CGFloat,
    zoomRange: ClosedRange<CGFloat>
  ) -> (zoom: CGFloat, pan: CGSize) {
    guard let first = positions.first else {
      return (min(max(currentZoom, zoomRange.lowerBound), zoomRange.upperBound), .zero)
    }
    if positions.count == 1 {
      let zoom = min(max(currentZoom, focusTargetZoom), zoomRange.upperBound)
      let span = MemoryAtlasLayoutEngine.projectionSpan(of: viewport)
      return (
        zoom,
        CGSize(
          width: (0.5 - first.x) * span * zoom,
          height: (0.5 - first.y) * span * zoom)
      )
    }

    var minimum = first
    var maximum = first
    for point in positions.dropFirst() {
      minimum = CGPoint(x: min(minimum.x, point.x), y: min(minimum.y, point.y))
      maximum = CGPoint(x: max(maximum.x, point.x), y: max(maximum.y, point.y))
    }
    let center = CGPoint(x: (minimum.x + maximum.x) / 2, y: (minimum.y + maximum.y) / 2)
    let radius = max(hypot(maximum.x - minimum.x, maximum.y - minimum.y) / 2, 0.04)
    return MemoryAtlasNeighbourhoodLabels.entering(
      center: center,
      radius: radius,
      viewport: viewport,
      zoomRange: zoomRange)
  }
}
