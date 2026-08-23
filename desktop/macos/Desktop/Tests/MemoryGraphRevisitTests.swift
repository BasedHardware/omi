import XCTest

@testable import Omi_Computer

final class MemoryGraphRevisitTests: XCTestCase {
  func testHomeMemoriesUsePersistentGraphViewModel() throws {
    let graph = try source(at: "Sources/MainWindow/Pages/MemoryGraph/MemoryGraphPage.swift")
    let hub = try source(at: "Sources/MainWindow/MemoryHubPage.swift")
    let home = try source(at: "Sources/MainWindow/DesktopHomeView.swift")
    let container = try source(at: "Sources/ViewModelContainer.swift")

    XCTAssertFalse(graph.contains("@StateObject private var viewModel = MemoryGraphViewModel()"))
    XCTAssertTrue(graph.contains("@ObservedObject var viewModel: MemoryGraphViewModel"))
    XCTAssertTrue(container.contains("let memoryGraphViewModel = MemoryGraphViewModel()"))
    XCTAssertTrue(container.contains("memoryGraphViewModel.resetSessionState()"))
    // The Brain Map is reachable only from its own hub tab now — the inline
    // Memories card is gone — so MemoriesPage no longer receives the graph view
    // model at all. Both the canonical destination and legacy fallback must use
    // the persistent, container-owned instance.
    XCTAssertTrue(hub.contains("graphViewModel: viewModelContainer.memoryGraphViewModel"))
    XCTAssertTrue(hub.contains("MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)"))
    XCTAssertTrue(hub.contains("switch destination"))
    // Static wiring tripwire: the shell owns the hub's placement, and the hub is
    // a full-bleed destination — the readable-width cap belongs to the pages
    // inside it, not to the hub itself.
    XCTAssertFalse(home.contains("constrainedListPage(MemoryHubPage"))
    // The Brain Map moved onto the glass panel. `OmiColors.backgroundPrimary` was the dark chrome's
    // near-black page ground, and a SceneKit view that paints it is drawing a page ground of its own
    // inside a translucent panel — the thing `InkGlass`'s "hosted content paints no background" rule
    // exists to stop. The scene now paints nothing; the dark ground it genuinely needs (its nodes are
    // emissive and its labels are white) is `glassMediaMat`, a framed media viewport applied around
    // it, so the graph stays legible without the page pretending to be opaque.
    XCTAssertTrue(graph.contains("scnView.backgroundColor = .clear"))
    XCTAssertTrue(graph.contains(".glassMediaMat("))
  }

  func testMemoryHubDestinationMenuHasStableRoutes() {
    XCTAssertEqual(
      MemoryHubDestination.allCases,
      [.memories, .conversations, .brainMap, .activity]
    )
    // Storage identity, pinned: these raw values are persisted, so the enum may not be reordered.
    // Reading order is a different list and lives with the control that presents it — see
    // `ChatFirstDestinationParityTests.testTheActivityChipRowOffersEveryHubPageAndNothingElse`.
    XCTAssertEqual(MemoryHubDestination.activity.title, "Brain")
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

  /// The hover menu these three tests used to cover is gone, and so is
  /// `MemoryDropdownInteractionState` — its hover-generation machinery had no other caller. The
  /// Memory hub's four destinations are now selected by Activity's chip row; that contract is held
  /// by `ChatFirstDestinationParityTests.testTheActivityChipRowOffersEveryHubPageAndNothingElse`
  /// and `TopNavigationBarLayoutTests`.
  func testTopNavigationUsesCompactPillSpacing() {
    XCTAssertEqual(TopNavigationPillMetrics.itemSpacing, 4)
    XCTAssertEqual(TopNavigationPillMetrics.horizontalPadding, 12)
    XCTAssertEqual(TopNavigationPillMetrics.height, 30)
  }

  func testMemoryHubUsesReadableWidthUntilTheActiveTranscriptOpens() {
    XCTAssertEqual(MemoryHubLayoutPolicy.readableContentWidth, 900)
    XCTAssertFalse(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: nil,
        presentedConversationID: nil,
        transcriptDrawerOpen: false
      ))
    XCTAssertFalse(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: "conversation-1",
        presentedConversationID: "conversation-1",
        transcriptDrawerOpen: false
      ))
    XCTAssertFalse(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: "conversation-1",
        presentedConversationID: "conversation-2",
        transcriptDrawerOpen: true
      ))
    XCTAssertTrue(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: "conversation-1",
        presentedConversationID: "conversation-1",
        transcriptDrawerOpen: true
      ))
  }

  func testOpeningAMemoryIntoTheSidePanelReleasesTheReadableWidthCap() {
    // The memory detail is a side panel rather than a modal, so with the cap
    // still applied the panel would take its 360pt out of the list's 900pt
    // column instead of out of the window.
    XCTAssertTrue(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: nil,
        presentedConversationID: nil,
        transcriptDrawerOpen: false,
        memoryDetailOpen: true
      ))
    XCTAssertFalse(
      MemoryHubLayoutPolicy.usesAvailableWidth(
        conversationID: nil,
        presentedConversationID: nil,
        transcriptDrawerOpen: false,
        memoryDetailOpen: false
      ))
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
    // omi-test-quality: source-inspection -- static contract: which token a call site names is a source fact; a rendered view cannot report it.
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
