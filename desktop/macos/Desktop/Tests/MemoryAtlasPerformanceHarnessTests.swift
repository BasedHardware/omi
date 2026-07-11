import XCTest
@testable import Omi_Computer

/// Deterministic production-scale input for Memory Atlas performance loops.
///
/// The fixture intentionally sits just above the sampled account graph (about
/// 1,124 nodes and 1,668 edges), so a passing optimization is not accidentally
/// tuned only for a small unit-test graph. Work-budget assertions belong here;
/// wall-clock measurements are diagnostic because runner hardware varies.
final class MemoryAtlasPerformanceHarnessTests: XCTestCase {
  private let productionScaleNodeCount = 1_200
  private let productionScaleEdgeCount = 1_800

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
  }

  func testRenderPlannerKeepsOverviewWorkWithinBudgets() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1)

    XCTAssertEqual(plan.detailLevel, .overview)
    assertWorkBudgets(plan, nodes: 1_200, edges: 36, labels: 12)
  }

  func testRenderPlannerCullsAndBoundsNeighborhoodWork() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 1.5)

    XCTAssertEqual(plan.detailLevel, .neighborhood)
    assertWorkBudgets(plan, nodes: 600, edges: 96, labels: 24)
    XCTAssertLessThan(plan.visibleNodes.count, snapshot.nodes.count)
  }

  func testRenderPlannerCullsAndBoundsDetailWork() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 2.2)

    XCTAssertEqual(plan.detailLevel, .detail)
    assertWorkBudgets(plan, nodes: 450, edges: 160, labels: 36)
    XCTAssertLessThan(plan.visibleNodes.count, snapshot.nodes.count)
  }

  func testInspectModeExpandsEveryVisibleEntityWithoutGrowingWorkUnbounded() {
    let snapshot = makeProductionScaleSnapshot()
    let plan = makePlan(snapshot: snapshot, zoom: 15.5)

    XCTAssertEqual(MemoryAtlasZoomPolicy.maximumZoom(compact: false), 16)
    XCTAssertEqual(MemoryAtlasZoomPolicy.maximumZoom(compact: true), 1.35)
    XCTAssertEqual(plan.detailLevel, .inspect)
    assertWorkBudgets(plan, nodes: 64, edges: 64, labels: 64)
    XCTAssertLessThan(plan.visibleNodes.count, snapshot.nodes.count)
    XCTAssertEqual(Set(plan.interactiveNodes.map(\.id)), Set(plan.visibleNodes.map(\.id)))
    XCTAssertEqual(plan.labelNodeIDs, Set(plan.visibleNodes.map(\.id)))
  }

  func testSelectedFocusModeExcludesUnrelatedBackgroundNodes() throws {
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
    XCTAssertTrue(plan.visibleNodes.allSatisfy { plan.relatedNodeIDs.contains($0.id) })
  }

  func testSelectedHighDegreeNodeShowsOnlyBoundedDirectNeighborhood() {
    let snapshot = makeProductionScaleSnapshot()
    let viewport = CGSize(width: 1_200, height: 800)
    let zoom: CGFloat = 2
    let ownerPan = CGSize(
      width: 0,
      height: (0.5 - 0.77) * viewport.height * zoom
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

      let nodeLimit = zoom < 1.35 ? 1_200 : (zoom < 1.9 ? 600 : (zoom < MemoryAtlasZoomPolicy.focusModeZoom ? 450 : (zoom < MemoryAtlasZoomPolicy.inspectModeZoom ? 72 : 64)))
      let baseEdgeLimit = zoom < 1.35 ? 36 : (zoom < 1.9 ? 96 : (zoom < MemoryAtlasZoomPolicy.focusModeZoom ? 160 : (zoom < MemoryAtlasZoomPolicy.inspectModeZoom ? 80 : 64)))
      let edgeLimit = frame.isMultiple(of: 3) ? min(baseEdgeLimit, 80) : baseEdgeLimit
      XCTAssertLessThanOrEqual(plan.visibleNodes.count, nodeLimit)
      XCTAssertLessThanOrEqual(plan.visibleEdges.count, edgeLimit)
      let labelLimit = zoom >= MemoryAtlasZoomPolicy.inspectModeZoom ? 64 : (zoom >= MemoryAtlasZoomPolicy.focusModeZoom ? 72 : 36)
      XCTAssertLessThanOrEqual(plan.interactiveNodes.count, labelLimit)
    }
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
