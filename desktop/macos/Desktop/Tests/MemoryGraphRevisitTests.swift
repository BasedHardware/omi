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
    // The Brain Map is reachable only from its own hub tab now — the inline
    // Memories card is gone — so MemoriesPage no longer receives the graph view
    // model at all. Both the canonical destination and legacy fallback must use
    // the persistent, container-owned instance.
    XCTAssertTrue(home.contains("graphViewModel: viewModelContainer.memoryGraphViewModel"))
    XCTAssertTrue(home.contains("viewModel: viewModelContainer.memoryGraphViewModel"))
    XCTAssertTrue(home.contains("MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)"))
    // Static wiring tripwire: the Memory menu keeps the shared destination
    // owner while the graph remains a dedicated spatial surface.
    XCTAssertFalse(home.contains("constrainedListPage(MemoryHubPage"))
    XCTAssertTrue(home.contains("switch destination"))
    XCTAssertTrue(home.contains("MemoryGraphPage(viewModel: viewModelContainer.memoryGraphViewModel)"))
    XCTAssertTrue(graph.contains("scnView.backgroundColor = NSColor(OmiColors.backgroundPrimary)"))
  }

  func testMemoryHubDestinationMenuHasStableRoutes() {
    XCTAssertEqual(
      MemoryHubDestination.allCases,
      [.memories, .conversations, .brainMap]
    )
    XCTAssertEqual(
      MemoryHubDestination.dropdownDestinations,
      [.conversations, .brainMap]
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

  func testMemoryDropdownRejectsStaleHoverAndKeepsPointerTransitOpen() throws {
    var state = MemoryDropdownInteractionState()

    let staleOpen = try XCTUnwrap(state.hoverChanged(true, in: .anchor))
    XCTAssertNil(state.hoverChanged(false, in: .anchor))
    XCTAssertFalse(state.apply(staleOpen))
    XCTAssertFalse(state.isPresented)

    let activeOpen = try XCTUnwrap(state.hoverChanged(true, in: .anchor))
    XCTAssertTrue(state.apply(activeOpen))
    XCTAssertTrue(state.isPresented)

    let pendingClose = try XCTUnwrap(state.hoverChanged(false, in: .anchor))
    XCTAssertNil(state.hoverChanged(true, in: .dropdown))
    XCTAssertFalse(state.apply(pendingClose))
    XCTAssertTrue(state.isPresented)
  }

  func testMemoryDropdownDismissesAfterNavigation() throws {
    var state = MemoryDropdownInteractionState()

    let pendingOpen = try XCTUnwrap(state.hoverChanged(true, in: .anchor))
    XCTAssertTrue(state.apply(pendingOpen))
    XCTAssertTrue(state.isPresented)

    state.dismiss()
    XCTAssertFalse(state.isPresented)
  }

  func testMemoryDropdownPillsUseAnOpaqueOmiSurface() throws {
    // omi-test-quality: source-inspection -- static visual contract: dropdown rows must
    // occlude the page beneath them while retaining Omi's neutral pill styling.
    let source = try source(at: "Sources/MainWindow/DesktopTopBar.swift")
    let dropdownRowSource =
      source.components(separatedBy: "private struct MemoryDropdownRow").last ?? ""

    XCTAssertTrue(dropdownRowSource.contains("OmiColors.backgroundSecondary"))
    XCTAssertTrue(dropdownRowSource.contains("OmiColors.backgroundTertiary"))
    XCTAssertTrue(dropdownRowSource.contains("OmiColors.border.opacity(0.55)"))
    XCTAssertFalse(dropdownRowSource.contains(": Color.clear"))
  }

  func testTopNavigationUsesCompactPillWidthsAndTightSpacing() {
    XCTAssertEqual(TopNavigationPillMetrics.itemSpacing, 4)
    XCTAssertEqual(TopNavigationPillMetrics.horizontalPadding, 12)
    XCTAssertEqual(
      TopNavigationPillMetrics.width(for: SidebarNavItem.dashboard.rawValue),
      88
    )
    XCTAssertEqual(
      TopNavigationPillMetrics.width(for: SidebarNavItem.conversations.rawValue),
      128
    )
    XCTAssertEqual(
      TopNavigationPillMetrics.width(for: SidebarNavItem.tasks.rawValue),
      84
    )
    XCTAssertEqual(
      TopNavigationPillMetrics.width(for: SidebarNavItem.apps.rawValue),
      80
    )
    XCTAssertEqual(
      TopNavigationPillMetrics.width(
        for: SidebarNavItem.tasks.rawValue,
        badgeCount: 93
      ),
      122,
      "badged pills must grow instead of clipping their count"
    )
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
