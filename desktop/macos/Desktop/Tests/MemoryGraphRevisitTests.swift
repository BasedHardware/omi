import XCTest

@testable import Omi_Computer

final class MemoryGraphRevisitTests: XCTestCase {
  func testHomeMemoriesUsePersistentGraphViewModel() throws {
    let graph = try source(at: "Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift")
    let home = try source(at: "Sources/MainWindow/DesktopHomeView.swift")
    let container = try source(at: "Sources/ViewModelContainer.swift")

    XCTAssertFalse(graph.contains("@StateObject private var viewModel = MemoryGraphViewModel()"))
    XCTAssertTrue(graph.contains("@ObservedObject var viewModel: MemoryGraphViewModel"))
    XCTAssertTrue(container.contains("let memoryGraphViewModel = MemoryGraphViewModel()"))
    XCTAssertTrue(container.contains("memoryGraphViewModel.resetSessionState()"))
    XCTAssertTrue(home.contains("graphViewModel: viewModelContainer.memoryGraphViewModel"))
    // The Brain Map moved from an inline Memories card to its own hub tab, still
    // driven by the persistent, container-owned view model.
    XCTAssertTrue(home.contains("MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)"))
    // Static wiring tripwire: the Memory menu routes each destination into the
    // same full-width surface while the graph keeps the shared background.
    XCTAssertFalse(home.contains("constrainedListPage(MemoryHubPage"))
    XCTAssertFalse(home.contains("listContentWidth"))
    XCTAssertTrue(home.contains("switch destination"))
    XCTAssertTrue(home.contains("MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)"))
    XCTAssertTrue(graph.contains("scnView.backgroundColor = NSColor(OmiColors.backgroundPrimary)"))
  }

  func testMemoryHubDestinationMenuHasStableRoutes() {
    XCTAssertEqual(
      MemoryHubDestination.allCases,
      [.memories, .conversations, .brainMap]
    )
    XCTAssertEqual(MemoryHubDestination.memories.title, "Memories")
    XCTAssertEqual(MemoryHubDestination.conversations.title, "Conversations")
    XCTAssertEqual(MemoryHubDestination.brainMap.title, "Brain Map")
    XCTAssertEqual(MemoryHubDestination(rawValue: 1), .conversations)
    XCTAssertEqual(
      MemoryHubDestination.destination(for: .conversations),
      .conversations
    )
    XCTAssertEqual(
      MemoryHubDestination.destination(
        for: .conversations,
        requestedRawValue: MemoryHubDestination.brainMap.rawValue
      ),
      .brainMap
    )
    XCTAssertNil(MemoryHubDestination.destination(for: .tasks))
  }

  @MainActor
  func testGraphSignatureIsStableAcrossResponseOrdering() {
    let first = sampleGraph()
    let reordered = KnowledgeGraphResponse(nodes: first.nodes.reversed(), edges: first.edges.reversed())

    XCTAssertEqual(
      MemoryGraphViewModel.graphSignature(of: first),
      MemoryGraphViewModel.graphSignature(of: reordered)
    )
  }

  @MainActor
  func testGraphSignatureChangesWhenRenderedGraphChanges() {
    let base = sampleGraph()
    let baseSignature = MemoryGraphViewModel.graphSignature(of: base)

    XCTAssertNotEqual(
      baseSignature, MemoryGraphViewModel.graphSignature(of: sampleGraph(nodeLabel: "Different project")))
    XCTAssertNotEqual(baseSignature, MemoryGraphViewModel.graphSignature(of: sampleGraph(nodeType: .place)))
    XCTAssertNotEqual(baseSignature, MemoryGraphViewModel.graphSignature(of: sampleGraph(edgeLabel: "visited")))
    XCTAssertNotEqual(baseSignature, MemoryGraphViewModel.graphSignature(of: sampleGraph(edgeTargetId: "org")))
  }

  func testApplyLayoutRequiresEveryNonFixedNodeAndRestoresPositions() {
    let simulation = ForceDirectedSimulation()
    simulation.populate(graphResponse: sampleGraph(), userNodeLabel: "Me")

    let originalPositions = simulation.layoutPositions()
    let nonFixedIds = simulation.nodes.filter { !$0.isFixed }.map(\.id)
    XCTAssertFalse(nonFixedIds.isEmpty)

    XCTAssertFalse(simulation.applyLayout([:]))
    XCTAssertEqual(simulation.layoutPositions(), originalPositions)

    let cachedPositions = Dictionary(
      uniqueKeysWithValues: nonFixedIds.enumerated().map {
        ($0.element, SIMD3<Float>(Float($0.offset + 1) * 10, Float($0.offset + 1) * 20, 5))
      })

    XCTAssertTrue(simulation.applyLayout(cachedPositions))
    let restored = simulation.layoutPositions()
    for (id, position) in cachedPositions { XCTAssertEqual(restored[id], position) }
    XCTAssertTrue(simulation.isStable)
  }

  func testRunSyncKeepsFixedUserNodeAnchoredAndProducesFiniteLayout() throws {
    let simulation = ForceDirectedSimulation()
    simulation.populate(graphResponse: sampleGraph(), userNodeLabel: "Me")

    let fixedNode = try XCTUnwrap(simulation.nodes.first(where: \.isFixed))
    let fixedPosition = fixedNode.position

    simulation.runSync(ticks: 40)

    XCTAssertEqual(fixedNode.position, fixedPosition)
    XCTAssertGreaterThanOrEqual(simulation.lastStepEnergy, 0)
    for node in simulation.nodes {
      XCTAssertTrue(node.position.x.isFinite && node.position.y.isFinite && node.position.z.isFinite)
    }
  }

  // MARK: - Helpers

  private func source(at relativePath: String) throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func sampleGraph(
    nodeLabel: String = "Project Atlas",
    nodeType: KnowledgeGraphNodeType = .concept,
    edgeLabel: String = "works on",
    edgeTargetId: String = "project"
  ) -> KnowledgeGraphResponse {
    KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "me", label: "Me", nodeType: .person),
        KnowledgeGraphNode(id: "project", label: nodeLabel, nodeType: nodeType),
        KnowledgeGraphNode(id: "org", label: "Omi", nodeType: .organization),
      ],
      edges: [
        KnowledgeGraphEdge(id: "edge-me-target", sourceId: "me", targetId: edgeTargetId, label: edgeLabel),
        KnowledgeGraphEdge(id: "edge-project-org", sourceId: "project", targetId: "org", label: "belongs to"),
      ])
  }
}
