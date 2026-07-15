import XCTest
@testable import Omi_Computer

/// Deterministic production-scale input for Memory Atlas performance loops.
///
/// The fixture intentionally sits above the sampled account graph (about
/// 1,946 nodes and 2,784 edges), so a passing optimization is not accidentally
/// tuned only for a small unit-test graph. Work-budget assertions belong here;
/// wall-clock measurements are diagnostic because runner hardware varies.
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
    XCTAssertTrue(first.activeClusters.map(first.center(for:)).allSatisfy { center in
      abs(hypot((center.x - 0.5) / 0.15, (center.y - 0.5) / 0.25) - 1) < 0.000_001
    })
  }

  func testRenderPlannerKeepsOverviewWorkWithinBudgets() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1)

    XCTAssertEqual(plan.detailLevel, .overview)
    assertWorkBudgets(plan, nodes: 1_200, edges: 36, labels: 12)
  }

  func testRenderPlannerAddsTheNeighborhoodCohortWithoutDroppingOverviewDots() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1.5)

    XCTAssertEqual(plan.detailLevel, .neighborhood)
    assertWorkBudgets(plan, nodes: 1_600, edges: 96, labels: 24)
    XCTAssertEqual(plan.visibleNodes.count, 1_600)
  }

  func testRenderPlannerAddsTheFullAccountCohortAtDetailZoom() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 2.2)

    XCTAssertEqual(plan.detailLevel, .detail)
    assertWorkBudgets(plan, nodes: 2_400, edges: 160, labels: 36)
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
    assertWorkBudgets(plan, nodes: 3_200, edges: 360, labels: 96)
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
    let startingPan = CGSize(
      width: (0.5 - focusedPosition.x) * viewport.width * startingZoom,
      height: (0.5 - focusedPosition.y) * viewport.height * startingZoom
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
    XCTAssertTrue(plan.relatedNodeIDs.allSatisfy { relatedID in
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
    XCTAssertTrue(plan.visibleEdges.allSatisfy { edge in
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

      let nodeLimit = zoom < 1.35 ? 1_200 : (zoom < 1.9 ? 1_600 : (zoom < MemoryAtlasZoomPolicy.focusModeZoom ? 2_400 : 3_200))
      let baseEdgeLimit = zoom < 1.35 ? 36 : (zoom < 1.9 ? 96 : (zoom < MemoryAtlasZoomPolicy.focusModeZoom ? 160 : (zoom < MemoryAtlasZoomPolicy.inspectModeZoom ? 260 : 360)))
      let edgeLimit = frame.isMultiple(of: 3) ? min(baseEdgeLimit, 80) : baseEdgeLimit
      XCTAssertLessThanOrEqual(plan.visibleNodes.count, nodeLimit)
      XCTAssertLessThanOrEqual(plan.visibleEdges.count, edgeLimit)
      let labelLimit = zoom >= MemoryAtlasZoomPolicy.inspectModeZoom ? 96 : (zoom >= MemoryAtlasZoomPolicy.focusModeZoom ? 72 : 36)
      XCTAssertLessThanOrEqual(plan.interactiveNodes.count, labelLimit)
    }
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

    measure(metrics: [XCTClockMetric(), XCTCPUMetric(), XCTMemoryMetric()]) {
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

  private func makeProductionScaleSnapshot() -> MemoryAtlasSnapshot {
    MemoryAtlasLayoutEngine.makeSnapshot(
      graph: makeProductionScaleGraph(),
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
