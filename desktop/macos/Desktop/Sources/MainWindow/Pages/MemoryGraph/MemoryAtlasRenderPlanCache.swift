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
/// `isCameraMoving` is true and the graph has no active search filter. The
/// surface hides SwiftUI labels and hit targets during that state; Canvas
/// continues to project the cached entity cohort using the current
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
  /// pan/zoom gesture is active. Search plans intentionally bypass reuse
  /// because membership changes as the user types.
  func makePlan(
    viewportSize: CGSize,
    zoom: CGFloat,
    pan: CGSize,
    compact: Bool,
    selectedNodeID: String?,
    matchingNodeIDs: Set<String>?,
    matchingEdges: [MemoryAtlasEdgePlacement]?,
    isCameraMoving: Bool
  ) -> MemoryAtlasRenderPlan {
    guard
      isCameraMoving,
      selectedNodeID == nil,
      matchingNodeIDs == nil,
      matchingEdges == nil
    else {
      return makeFreshPlan(
        viewportSize: viewportSize,
        zoom: zoom,
        pan: pan,
        compact: compact,
        selectedNodeID: selectedNodeID,
        matchingNodeIDs: matchingNodeIDs,
        matchingEdges: matchingEdges
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
      matchingEdges: nil
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
    matchingEdges: [MemoryAtlasEdgePlacement]?
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
      matchingEdges: matchingEdges
    )
  }

  private func detailLevel(for zoom: CGFloat) -> Int {
    if zoom < MemoryAtlasZoomPolicy.neighborhoodZoom { return 0 }
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

/// The immutable, expensive part of one Brain Map revision.
///
/// A graph response can be large enough that calculating a content digest,
/// relaxing its layout, and rebuilding the camera-plan cache is real work. A
/// SwiftUI view initializer is not a safe owner for any of it: initializers
/// run again whenever unrelated observed state publishes (for example, a memory sync while the Brain Map is open).
///
/// This object is prepared once for a fetched graph revision and then passed
/// unchanged through every render of that revision. It deliberately owns the
/// mutable render-plan cache as well, so a gesture retains its cached cohort
/// instead of recreating it for each frame.
final class MemoryAtlasProjection: @unchecked Sendable {
  let graph: KnowledgeGraphResponse
  let snapshot: MemoryAtlasSnapshot
  let renderPlanCache: MemoryAtlasRenderPlanCache

  init(graph: KnowledgeGraphResponse, userName: String?) {
    self.graph = graph
    let snapshot = MemoryAtlasSnapshotCache.shared.snapshot(for: graph, userName: userName)
    self.snapshot = snapshot
    renderPlanCache = MemoryAtlasRenderPlanCache(snapshot: snapshot)
  }
}
