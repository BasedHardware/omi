import XCTest

@testable import Omi_Computer

/// Deterministic production-scale input for Memory Atlas performance loops.
///
/// The fixture intentionally sits above the sampled account graph (about
/// 1,946 nodes and 2,784 edges), so a passing optimization is not accidentally
/// tuned only for a small unit-test graph. Work-budget assertions belong here;
/// wall-clock measurements are diagnostic because runner hardware varies.
///
/// The edge budgets are deliberately larger than the mesh a real account has,
/// because the whole mesh is now what shows the map's structure and rationing
/// it hid exactly the thing it was drawn to show. What actually bounds the
/// paint is one level up — the node cohort, since an edge needs both of its
/// endpoints on the map — and the segments batch into one path per type per
/// weight, so these numbers cap the cohort's worst case rather than the number
/// of draw calls. Keep them as the tripwire against a budget going unbounded.
final class MemoryAtlasPerformanceHarnessTests: XCTestCase {
  private let productionScaleNodeCount = 2_400
  private let productionScaleEdgeCount = 3_600

  func testProductionScaleFixtureAndLayoutAreCompleteAndDeterministic() {
    let graph = makeProductionScaleGraph()

    XCTAssertEqual(graph.nodes.count, productionScaleNodeCount)
    XCTAssertEqual(graph.edges.count, productionScaleEdgeCount)

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "Atlas Owner")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "Atlas Owner")

    XCTAssertEqual(first.anchorNodeID, "owner")
    XCTAssertEqual(first.nodes.count, productionScaleNodeCount)
    XCTAssertEqual(first.edges.count, productionScaleEdgeCount)
    XCTAssertEqual(first.nodes.map(\.id), second.nodes.map(\.id))
    XCTAssertEqual(first.nodes.map(\.normalizedPosition), second.nodes.map(\.normalizedPosition))
    XCTAssertEqual(
      first.activeClusters,
      [.person, .organization, .place, .thing, .concept]
    )
    // Constellation captions are now the mean position of their own entities,
    // not five fixed points on a ring, so the only geometric claim left is that
    // each one lands on the canvas among the entities it names.
    XCTAssertTrue(
      first.activeClusters.map(first.center(for:)).allSatisfy { center in
        (0...1).contains(center.x) && (0...1).contains(center.y)
      })
  }

  func testRenderPlannerKeepsOverviewWorkWithinBudgets() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1)

    XCTAssertEqual(plan.detailLevel, .overview)
    assertWorkBudgets(plan, nodes: 1_200, edges: 2_000, labels: 12)
  }

  func testRenderPlannerAddsTheNeighborhoodCohortWithoutDroppingOverviewDots() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1.5)

    XCTAssertEqual(plan.detailLevel, .neighborhood)
    assertWorkBudgets(plan, nodes: 1_600, edges: 2_400, labels: 24)
    XCTAssertEqual(plan.visibleNodes.count, 1_600)
  }

  func testRenderPlannerAddsTheFullAccountCohortAtDetailZoom() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 2.2)

    XCTAssertEqual(plan.detailLevel, .detail)
    assertWorkBudgets(plan, nodes: 2_400, edges: 3_000, labels: 36)
    XCTAssertEqual(plan.visibleNodes.count, snapshot.nodes.count)
  }

  func testInspectModeMovesAutomaticLabelsToCanvasWithoutViewExplosion() {
    let snapshot = makeProductionScaleSnapshot()
    let automaticCanvasLabelZoom = MemoryAtlasZoomPolicy.automaticCanvasLabelZoom(
      nodeCount: snapshot.nodes.count
    )
    let plan = makePlan(snapshot: snapshot, zoom: automaticCanvasLabelZoom)

    XCTAssertEqual(MemoryAtlasZoomPolicy.maximumZoom(nodeCount: snapshot.nodes.count, compact: false), 180)
    XCTAssertEqual(MemoryAtlasZoomPolicy.maximumZoom(nodeCount: snapshot.nodes.count, compact: true), 1.35)
    XCTAssertEqual(automaticCanvasLabelZoom, 45)
    XCTAssertEqual(plan.detailLevel, .inspect)
    assertWorkBudgets(plan, nodes: 3_200, edges: 4_200, labels: 96)
    XCTAssertEqual(plan.visibleNodes.count, snapshot.nodes.count)
    XCTAssertLessThan(plan.interactiveNodes.count, plan.visibleNodes.count)
    XCTAssertTrue(plan.labelNodeIDs.isEmpty)
    XCTAssertTrue(plan.usesCanvasLabels)
    XCTAssertFalse(plan.isFullyLabelled)
    XCTAssertEqual(Set(plan.canvasLabelNodes.map(\.id)), Set(plan.visibleNodes.map(\.id)))
  }

  func testDynamicMaximumZoomGrowsWithGraphDensity() {
    XCTAssertEqual(MemoryAtlasZoomPolicy.fullyLabelledZoom(nodeCount: 1), 16)
    XCTAssertEqual(MemoryAtlasZoomPolicy.fullyLabelledZoom(nodeCount: 1_946), 160)
    XCTAssertEqual(MemoryAtlasZoomPolicy.fullyLabelledZoom(nodeCount: 10_000), 360)
    XCTAssertEqual(MemoryAtlasZoomPolicy.automaticCanvasLabelZoom(nodeCount: 1_946), 40)
    XCTAssertEqual(MemoryAtlasZoomPolicy.automaticCanvasLabelZoom(nodeCount: 10_000), 90)
  }

  func testFullyLabelledNodesRetainTheInspectTargetSize() {
    let inspectRadius = MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: 3,
      zoom: 56.49,
      compact: false,
      isFullyLabelled: false,
      isInspect: true,
      isFocus: true
    )
    let fullyLabelledRadius = MemoryAtlasNodeVisualPolicy.radius(
      clusterRank: 3,
      zoom: 160,
      compact: false,
      isFullyLabelled: true,
      isInspect: true,
      isFocus: true
    )

    XCTAssertEqual(inspectRadius, 12)
    XCTAssertEqual(fullyLabelledRadius, inspectRadius)
  }

  func testDynamicMaximumZoomLabelsEveryVisibleEntityWithoutViewExplosion() {
    let snapshot = makeProductionScaleSnapshot()
    let maximumZoom = MemoryAtlasZoomPolicy.maximumZoom(
      nodeCount: snapshot.nodes.count,
      compact: false
    )
    let plan = makePlan(snapshot: snapshot, zoom: maximumZoom)

    XCTAssertTrue(plan.isFullyLabelled)
    XCTAssertTrue(plan.usesCanvasLabels)
    XCTAssertEqual(plan.visibleNodes.count, snapshot.nodes.count)
    XCTAssertEqual(Set(plan.canvasLabelNodes.map(\.id)), Set(plan.visibleNodes.map(\.id)))
    XCTAssertTrue(plan.labelNodeIDs.isEmpty)
    XCTAssertLessThanOrEqual(plan.interactiveNodes.count, 96)
  }

  func testCenterAnchoredDeepZoomKeepsTheFocusedEntityInView() {
    let viewport = CGSize(width: 1_200, height: 800)
    let focusedPosition = CGPoint(x: 0.357_342, y: 0.422_746)
    let startingZoom: CGFloat = 4
    let projectionSpan = MemoryAtlasLayoutEngine.projectionSpan(of: viewport)
    let startingPan = CGSize(
      width: (0.5 - focusedPosition.x) * projectionSpan * startingZoom,
      height: (0.5 - focusedPosition.y) * projectionSpan * startingZoom
    )
    let maximumZoom = MemoryAtlasZoomPolicy.fullyLabelledZoom(nodeCount: 1_946)
    let endingPan = MemoryAtlasZoomPolicy.panPreservingCenterZoom(
      startingPan,
      from: startingZoom,
      to: maximumZoom
    )

    let startingPoint = MemoryAtlasRenderPlanner.renderedPoint(
      for: focusedPosition,
      viewportSize: viewport,
      zoom: startingZoom,
      pan: startingPan
    )
    let endingPoint = MemoryAtlasRenderPlanner.renderedPoint(
      for: focusedPosition,
      viewportSize: viewport,
      zoom: maximumZoom,
      pan: endingPan
    )
    XCTAssertEqual(startingPoint.x, endingPoint.x, accuracy: 0.000_1)
    XCTAssertEqual(startingPoint.y, endingPoint.y, accuracy: 0.000_1)
  }

  func testSelectedFocusModeRetainsTheRenderedBackgroundCohort() throws {
    let snapshot = makeProductionScaleSnapshot()
    let selected = try XCTUnwrap(snapshot.nodeByID["node-2"])
    let viewport = CGSize(width: 1_200, height: 800)
    let zoom: CGFloat = 4
    let pan = CGSize(
      width: (0.5 - selected.normalizedPosition.x) * viewport.width * zoom,
      height: (0.5 - selected.normalizedPosition.y) * viewport.height * zoom
    )

    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: viewport,
      zoom: zoom,
      pan: pan,
      compact: false,
      selectedNodeID: selected.id,
      matchingNodeIDs: nil
    )

    XCTAssertEqual(plan.detailLevel, .focus)
    XCTAssertTrue(plan.visibleNodes.contains { $0.id == selected.id })
    XCTAssertTrue(
      plan.relatedNodeIDs.allSatisfy { relatedID in
        plan.visibleNodes.contains { $0.id == relatedID }
      })
    XCTAssertEqual(plan.visibleNodes.count, snapshot.nodes.count)
  }

  func testSelectedHighDegreeNodeShowsOnlyBoundedDirectNeighborhood() throws {
    let snapshot = makeProductionScaleSnapshot()
    let viewport = CGSize(width: 1_200, height: 800)
    let zoom: CGFloat = 2
    let owner = try XCTUnwrap(snapshot.nodeByID["owner"])
    let ownerPan = CGSize(
      width: 0,
      height: (0.5 - owner.normalizedPosition.y) * viewport.height * zoom
    )
    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: viewport,
      zoom: zoom,
      pan: ownerPan,
      compact: false,
      selectedNodeID: "owner",
      matchingNodeIDs: nil
    )

    XCTAssertLessThanOrEqual(plan.visibleEdges.count, 80)
    XCTAssertLessThanOrEqual(plan.labelNodeIDs.count, 36)
    XCTAssertTrue(
      plan.visibleEdges.allSatisfy { edge in
        edge.edge.sourceId == "owner" || edge.edge.targetId == "owner"
      })
    XCTAssertTrue(plan.relatedNodeIDs.contains("owner"))
  }

  func testRepeatedCameraFramesKeepProductionScaleWorkBounded() {
    let snapshot = makeProductionScaleSnapshot()
    let viewport = CGSize(width: 1_200, height: 800)

    for frame in 0..<180 {
      let progress = CGFloat(frame) / 179
      let zoom = 1 + progress * 15
      let pan = CGSize(
        width: (progress - 0.5) * 480,
        height: (0.5 - progress) * 260
      )
      let plan = MemoryAtlasRenderPlanner.makePlan(
        snapshot: snapshot,
        viewportSize: viewport,
        zoom: zoom,
        pan: pan,
        compact: false,
        selectedNodeID: frame.isMultiple(of: 3) ? "owner" : nil,
        matchingNodeIDs: nil
      )

      let nodeLimit =
        zoom < 1.35 ? 1_200 : (zoom < 1.9 ? 1_600 : (zoom < MemoryAtlasZoomPolicy.focusModeZoom ? 2_400 : 3_200))
      let baseEdgeLimit =
        zoom < 1.35
        ? 2_000
        : (zoom < 1.9
          ? 2_400
          : (zoom < MemoryAtlasZoomPolicy.focusModeZoom
            ? 3_000 : (zoom < MemoryAtlasZoomPolicy.inspectModeZoom ? 3_600 : 4_200)))
      let edgeLimit = frame.isMultiple(of: 3) ? min(baseEdgeLimit, 80) : baseEdgeLimit
      XCTAssertLessThanOrEqual(plan.visibleNodes.count, nodeLimit)
      XCTAssertLessThanOrEqual(plan.visibleEdges.count, edgeLimit)
      let labelLimit =
        zoom >= MemoryAtlasZoomPolicy.inspectModeZoom ? 96 : (zoom >= MemoryAtlasZoomPolicy.focusModeZoom ? 72 : 36)
      XCTAssertLessThanOrEqual(plan.interactiveNodes.count, labelLimit)
    }
  }

  func testGesturePlanCacheAvoidsRepeatedProductionScalePlanning() {
    let snapshot = makeProductionScaleSnapshot()
    let cache = MemoryAtlasRenderPlanCache(snapshot: snapshot)
    let viewport = CGSize(width: 1_200, height: 800)
    var expectedNodeIDs: [String] = []
    var expectedEdgeIDs: [String] = []

    // Every frame stays in the detail band. Pan and exact zoom change the
    // projection, but not the planner's stable node/edge cohort, so a live
    // gesture should pay for that graph-wide selection once rather than 180
    // times. The view still recomputes a fresh plan after the gesture ends.
    for frame in 0..<180 {
      let progress = CGFloat(frame) / 179
      let plan = cache.makePlan(
        viewportSize: viewport,
        zoom: 2.2 + progress * 0.8,
        pan: CGSize(width: progress * 480, height: -progress * 260),
        compact: false,
        selectedNodeID: nil,
        matchingNodeIDs: nil,
        matchingEdges: nil,
        asOf: nil,
        isCameraMoving: true
      )
      if frame == 0 {
        expectedNodeIDs = plan.visibleNodes.map(\.id)
        expectedEdgeIDs = plan.visibleEdges.map(\.id)
      } else {
        XCTAssertEqual(plan.visibleNodes.map(\.id), expectedNodeIDs)
        XCTAssertEqual(plan.visibleEdges.map(\.id), expectedEdgeIDs)
      }
    }

    XCTAssertEqual(cache.plannerInvocationCount, 1)
    XCTAssertEqual(cache.transientReuseCount, 179)

    _ = cache.makePlan(
      viewportSize: viewport,
      zoom: 3,
      pan: CGSize(width: 480, height: -260),
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil,
      matchingEdges: nil,
      asOf: nil,
      isCameraMoving: false
    )
    XCTAssertEqual(cache.plannerInvocationCount, 2)
  }

  func testProjectionKeepsTheSnapshotAndGestureCacheAcrossViewTransactions() {
    let graph = makeProductionScaleGraph()
    let projection = MemoryAtlasProjection(graph: graph, userName: "Atlas Owner")
    let viewport = CGSize(width: 1_200, height: 800)

    XCTAssertEqual(projection.snapshot.nodes.count, productionScaleNodeCount)
    XCTAssertEqual(projection.snapshot.edges.count, productionScaleEdgeCount)
    XCTAssertEqual(projection.connectionBirthFractions.count, productionScaleEdgeCount)
    XCTAssertEqual(projection.connectionBirthFractions, projection.connectionBirthFractions.sorted())

    for frame in 0..<120 {
      _ = projection.renderPlanCache.makePlan(
        viewportSize: viewport,
        zoom: 2.2 + CGFloat(frame) * 0.002,
        pan: CGSize(width: CGFloat(frame), height: -CGFloat(frame)),
        compact: false,
        selectedNodeID: nil,
        matchingNodeIDs: nil,
        matchingEdges: nil,
        asOf: nil,
        isCameraMoving: true
      )
    }

    XCTAssertEqual(projection.renderPlanCache.plannerInvocationCount, 1)
    XCTAssertEqual(projection.renderPlanCache.transientReuseCount, 119)
  }

  func testZoomOnlyAddsStableEntityCohorts() {
    let snapshot = makeProductionScaleSnapshot()
    let zooms: [CGFloat] = [1, 1.35, 1.9, 3.2, 7.5]
    let plans = zooms.map { makePlan(snapshot: snapshot, zoom: $0) }

    for (current, next) in zip(plans, plans.dropFirst()) {
      let currentIDs = Set(current.visibleNodes.map(\.id))
      let nextIDs = Set(next.visibleNodes.map(\.id))
      XCTAssertTrue(currentIDs.isSubset(of: nextIDs))
      XCTAssertGreaterThanOrEqual(next.visibleNodes.count, current.visibleNodes.count)
      XCTAssertGreaterThanOrEqual(next.visibleEdges.count, current.visibleEdges.count)
    }
  }

  func testCameraMotionDoesNotChangeTheRenderedEntityCohort() {
    let snapshot = makeProductionScaleSnapshot()
    let stationary = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: 1.5,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil
    )
    let panned = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: 1.5,
      pan: CGSize(width: 480, height: -260),
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil
    )

    XCTAssertEqual(stationary.visibleNodes.map(\.id), panned.visibleNodes.map(\.id))
  }

  func testStaticPreviewUsesBoundedNonInteractiveWork() {
    let preview = MemoryAtlasRenderPlanner.makePreviewPlan(snapshot: makeProductionScaleSnapshot())

    XCTAssertEqual(preview.detailLevel, .overview)
    XCTAssertLessThanOrEqual(preview.visibleNodes.count, 260)
    XCTAssertLessThanOrEqual(preview.visibleEdges.count, 24)
    XCTAssertTrue(preview.interactiveNodes.isEmpty)
    XCTAssertTrue(preview.labelNodeIDs.isEmpty)
  }

  /// Run with:
  /// `xcrun swift test --package-path Desktop --filter MemoryAtlasPerformanceHarnessTests/testMeasureProductionScaleLayout`
  ///
  /// XCTest prints the local baseline without making correctness depend on the
  /// speed or load of a particular Mac.
  func testMeasureProductionScaleLayout() {
    let graph = makeProductionScaleGraph()

    // One iteration, not the default ten. This reports a diagnostic local
    // baseline without letting a non-asserting benchmark consume the isolated
    // suite's CI timeout budget under a loaded debug runner.
    let options = XCTMeasureOptions()
    options.iterationCount = 1

    measure(metrics: [XCTClockMetric(), XCTCPUMetric(), XCTMemoryMetric()], options: options) {
      _ = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "Atlas Owner")
    }
  }

  /// Diagnostic counterpart to the deterministic work-budget tests. A local
  /// run reports planning latency, CPU, and memory without a machine-specific
  /// pass/fail threshold.
  func testMeasureProductionScaleDetailPlanning() {
    let snapshot = makeProductionScaleSnapshot()

    measure(metrics: [XCTClockMetric(), XCTCPUMetric(), XCTMemoryMetric()]) {
      _ = makePlan(snapshot: snapshot, zoom: 2.2)
    }
  }

  /// Routed through the production memo rather than relaying every case's own
  /// relaxation. Thirteen render-plan cases share one fixture, and laying out
  /// 1,946 entities thirteen times cost this suite over a minute in a debug
  /// build while proving nothing about the planner any one of them measures.
  /// `testMeasureProductionScaleLayout` still calls the engine directly, so the
  /// layout's own cost stays measured.
  private func makeProductionScaleSnapshot() -> MemoryAtlasSnapshot {
    MemoryAtlasSnapshotCache.shared.snapshot(
      for: makeProductionScaleGraph(),
      userName: "Atlas Owner"
    )
  }

  private func makePlan(
    snapshot: MemoryAtlasSnapshot,
    zoom: CGFloat
  ) -> MemoryAtlasRenderPlan {
    MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: zoom,
      pan: .zero,
      compact: false,
      selectedNodeID: nil,
      matchingNodeIDs: nil
    )
  }

  private func assertWorkBudgets(
    _ plan: MemoryAtlasRenderPlan,
    nodes: Int,
    edges: Int,
    labels: Int,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    XCTAssertLessThanOrEqual(plan.visibleNodes.count, nodes, file: file, line: line)
    XCTAssertLessThanOrEqual(plan.visibleEdges.count, edges, file: file, line: line)
    XCTAssertLessThanOrEqual(plan.labelNodeIDs.count, labels, file: file, line: line)
    XCTAssertLessThanOrEqual(plan.interactiveNodes.count, labels, file: file, line: line)
  }

  private func makeProductionScaleGraph() -> KnowledgeGraphResponse {
    let nodes = (0..<productionScaleNodeCount).map { index -> KnowledgeGraphNode in
      if index == 0 {
        return KnowledgeGraphNode(id: "owner", label: "Atlas Owner", nodeType: .person)
      }

      let type: KnowledgeGraphNodeType
      switch index % 5 {
      case 0: type = .person
      case 1: type = .organization
      case 2: type = .thing
      case 3: type = .concept
      default: type = .place
      }
      return KnowledgeGraphNode(
        id: "node-\(index)",
        label: "Synthetic entity \(index)",
        nodeType: type,
        aliases: ["Alias \(index)"],
        memoryIds: ["memory-\(index)"]
      )
    }

    var edges: [KnowledgeGraphEdge] = []
    edges.reserveCapacity(productionScaleEdgeCount)

    for index in 1..<productionScaleNodeCount {
      edges.append(
        KnowledgeGraphEdge(
          id: "anchor-edge-\(index)",
          sourceId: "owner",
          targetId: "node-\(index)",
          label: relationshipLabel(for: index),
          memoryIds: ["memory-\(index)"]
        )
      )
    }

    let remainingEdgeCount = productionScaleEdgeCount - edges.count
    for index in 0..<remainingEdgeCount {
      let sourceIndex = index + 1
      let targetIndex = ((index * 37 + 97) % (productionScaleNodeCount - 1)) + 1
      edges.append(
        KnowledgeGraphEdge(
          id: "cross-edge-\(index)",
          sourceId: "node-\(sourceIndex)",
          targetId: "node-\(targetIndex)",
          label: relationshipLabel(for: index + 2),
          memoryIds: ["cross-memory-\(index)"]
        )
      )
    }

    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }

  private func relationshipLabel(for index: Int) -> String {
    switch index % 3 {
    case 0: return "works_on"
    case 1: return "works_with"
    default: return "uses"
    }
  }
}
