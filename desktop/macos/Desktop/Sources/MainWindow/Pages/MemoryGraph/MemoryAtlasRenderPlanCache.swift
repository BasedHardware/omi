import SwiftUI

/// Reuses the camera-invariant portion of an Atlas render plan during a live
/// pan or magnification gesture.
///
/// `MemoryAtlasRenderPlanner` deliberately keeps a stable entity cohort for a
/// detail level. Its node and edge selection therefore does not depend on pan
/// or on the exact zoom within that level, but calculating it still walks the
/// full graph and allocates priority/fairness buckets. SwiftUI can evaluate the
/// body many times per second while either gesture is active, so doing that
/// work per frame becomes visible on production-scale graphs.
///
/// The cache is intentionally narrow: it only reuses a plan while
/// `isCameraMoving` is true and the graph has no active search or timeline
/// filter. The surface hides SwiftUI labels and hit targets during that state;
/// Canvas continues to project the cached entity cohort using the current
/// zoom/pan. When the gesture settles, the planner runs again so collision
/// admitted labels and interactive targets exactly match the final viewport.
/// This preserves continuous node fidelity while removing repeated sorting and
/// cohort-layout work from the gesture hot path.
final class MemoryAtlasRenderPlanCache {
  private struct CohortKey: Hashable {
    let detailLevel: Int
    let compact: Bool
    let isFullyLabelled: Bool
    let usesCanvasLabels: Bool
    let selectedNodeID: String?
  }

  private let snapshot: MemoryAtlasSnapshot
  private var transientPlans: [CohortKey: MemoryAtlasRenderPlan] = [:]

  /// Exposed for deterministic performance-harness assertions. These count
  /// planner calls rather than wall-clock time, so they are stable across Macs.
  private(set) var plannerInvocationCount = 0
  private(set) var transientReuseCount = 0

  init(snapshot: MemoryAtlasSnapshot) {
    self.snapshot = snapshot
  }

  /// Returns the current plan, reusing only a camera-invariant plan while a
  /// pan/zoom gesture is active. Search and time-travel plans intentionally
  /// bypass reuse because those states change membership as the user types or
  /// scrubs the timeline.
  func makePlan(
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]?,
    asOf: Date?,
    timeline: MemoryAtlasTimeline? = nil,
    timeCursor: Double? = nil,
    isCameraMoving: Bool
  ) -> MemoryAtlasRenderPlan {
    let isTimelineFiltered = timeline != nil && (timeCursor ?? 1) < 0.9995
    guard
      isCameraMoving,
      selectedNodeID == nil,
      matchingNodeIDs == nil,
      matchingEdges == nil,
      asOf == nil,
      !isTimelineFiltered
    else {
      return makeFreshPlan(
        viewportSize: viewportSize,
        zoom: zoom,
        pan: pan,
        compact: compact,
        selectedNodeID: selectedNodeID,
        matchingNodeIDs: matchingNodeIDs,
        matchingEdges: matchingEdges,
        asOf: asOf,
        timeline: timeline,
        timeCursor: timeCursor
      )
    }

    let key = CohortKey(
      detailLevel: detailLevel(for: zoom),
      compact: compact,
      isFullyLabelled: isFullyLabelled(zoom: zoom, compact: compact),
      usesCanvasLabels: usesCanvasLabels(zoom: zoom, compact: compact),
      selectedNodeID: selectedNodeID
    )
    if let plan = transientPlans[key] {
      transientReuseCount += 1
      return plan
    }

    let plan = makeFreshPlan(
      viewportSize: viewportSize,
      zoom: zoom,
      pan: pan,
      compact: compact,
      selectedNodeID: selectedNodeID,
      matchingNodeIDs: nil,
      matchingEdges: nil,
      asOf: nil,
      timeline: nil,
      timeCursor: nil
    )
    transientPlans[key] = plan
    return plan
  }

  private func makeFreshPlan(
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]?,
    asOf: Date?,
    timeline: MemoryAtlasTimeline?,
    timeCursor: Double?
  ) -> MemoryAtlasRenderPlan {
    plannerInvocationCount += 1
    return MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: viewportSize,
      zoom: zoom,
      pan: pan,
      compact: compact,
      selectedNodeID: selectedNodeID,
      matchingNodeIDs: matchingNodeIDs,
      matchingEdges: matchingEdges,
      asOf: asOf,
      timeline: timeline,
      timeCursor: timeCursor
    )
  }

  private func detailLevel(for zoom: CGFloat) -> Int {
    if zoom < 1.35 { return 0 }
    if zoom < 1.9 { return 1 }
    if zoom < MemoryAtlasZoomPolicy.focusModeZoom { return 2 }
    if zoom < MemoryAtlasZoomPolicy.inspectModeZoom { return 3 }
    return 4
  }

  private func isFullyLabelled(zoom: CGFloat, compact: Bool) -> Bool {
    !compact && zoom >= MemoryAtlasZoomPolicy.fullyLabelledZoom(nodeCount: snapshot.nodes.count)
  }

  private func usesCanvasLabels(zoom: CGFloat, compact: Bool) -> Bool {
    !compact
      && zoom >= MemoryAtlasZoomPolicy.automaticCanvasLabelZoom(nodeCount: snapshot.nodes.count)
  }
}
