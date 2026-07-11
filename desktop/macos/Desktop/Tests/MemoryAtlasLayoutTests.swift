import XCTest
@testable import Omi_Computer

final class MemoryAtlasLayoutTests: XCTestCase {
  func testLayoutAnchorsNamedPersonAndProducesStablePositions() throws {
    let graph = sampleGraph()

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(first.anchorNodeID, "david")
    XCTAssertEqual(first.nodes.map(\.id), second.nodes.map(\.id))
    XCTAssertEqual(
      first.nodes.map(\.normalizedPosition),
      second.nodes.map(\.normalizedPosition)
    )
    XCTAssertEqual(first.nodeByID["david"]?.normalizedPosition, CGPoint(x: 0.5, y: 0.77))
  }

  func testRelationshipsDriveAtlasClusters() throws {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")

    XCTAssertEqual(snapshot.nodeByID["omi"]?.cluster, .projects)
    XCTAssertEqual(snapshot.nodeByID["openai"]?.cluster, .collaborators)
    XCTAssertEqual(snapshot.nodeByID["python"]?.cluster, .tools)
  }

  func testEveryRenderedEdgeHasPlacedEndpoints() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")

    XCTAssertEqual(snapshot.edges.count, 3)
    XCTAssertTrue(snapshot.edges.allSatisfy { edge in
      snapshot.nodes.contains { $0.normalizedPosition == edge.source }
        && snapshot.nodes.contains { $0.normalizedPosition == edge.target }
    })
  }

  func testLayoutCoalescesDuplicateServerIdentifiersWithoutTrapping() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David stale", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
        KnowledgeGraphNode(id: "david", label: "David current", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "relationship", sourceId: "david", targetId: "missing", label: "uses"),
        KnowledgeGraphEdge(id: "relationship", sourceId: "david", targetId: "omi", label: "works_on"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David current")

    XCTAssertEqual(snapshot.nodes.count, 2)
    XCTAssertEqual(snapshot.nodeByID["david"]?.node.label, "David current")
    XCTAssertEqual(snapshot.edges.count, 1)
    XCTAssertEqual(snapshot.edges.first?.edge.targetId, "omi")
  }

  func testPresentationModeKeepsLegacyGraphUntilCanonicalLifecycleIsExposed() {
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: false),
      .legacyBrainMap
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: true),
      .canonicalAtlas
    )
  }

  func testOverviewSuppressesOwnerFanButPreservesSalientCrossEntityRelationship() {
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "owner", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "project", label: "Atlas", nodeType: .concept),
        KnowledgeGraphNode(id: "person", label: "Sam", nodeType: .person),
      ],
      edges: [
        KnowledgeGraphEdge(id: "owner-project", sourceId: "owner", targetId: "project", label: "works_on"),
        KnowledgeGraphEdge(id: "owner-person", sourceId: "owner", targetId: "person", label: "works_with"),
        KnowledgeGraphEdge(id: "cross", sourceId: "person", targetId: "project", label: "works_on"),
      ]
    )

    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")

    XCTAssertEqual(snapshot.overviewEdges.map(\.id), ["cross"])
    XCTAssertTrue(snapshot.overviewEdges.allSatisfy {
      $0.edge.sourceId != "owner" && $0.edge.targetId != "owner"
    })
  }

  func testRecencyAndReinforcementAreDeterministicFromExistingEvidence() throws {
    let newest = Date(timeIntervalSince1970: 2_000_000)
    let graph = KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "owner", label: "David", nodeType: .person, updatedAt: newest),
        KnowledgeGraphNode(
          id: "fresh", label: "Fresh", nodeType: .concept,
          memoryIds: ["m1", "m2", "m5"], updatedAt: newest
        ),
        KnowledgeGraphNode(
          id: "stale", label: "Stale", nodeType: .concept,
          memoryIds: ["m3"], updatedAt: newest.addingTimeInterval(-90 * 86_400)
        ),
      ],
      edges: [
        KnowledgeGraphEdge(
          id: "e1", sourceId: "fresh", targetId: "stale", label: "supports",
          memoryIds: ["m2", "m4"]
        ),
      ]
    )

    let first = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let second = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: "David")
    let fresh = try XCTUnwrap(first.nodeByID["fresh"])
    let stale = try XCTUnwrap(first.nodeByID["stale"])

    XCTAssertEqual(fresh.recencyScore, 1)
    XCTAssertLessThan(stale.recencyScore, fresh.recencyScore)
    XCTAssertGreaterThan(fresh.reinforcementScore, stale.reinforcementScore)
    XCTAssertEqual(first.nodes.map(\.recencyScore), second.nodes.map(\.recencyScore))
    XCTAssertEqual(first.nodes.map(\.reinforcementScore), second.nodes.map(\.reinforcementScore))
  }

  func testFocusContainsOnlySelectedNodeAndDirectNeighborsAndBoundsRelationshipLabels() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")
    let plan = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot,
      viewportSize: CGSize(width: 1_200, height: 800),
      zoom: 4,
      pan: .zero,
      compact: false,
      selectedNodeID: "david",
      matchingNodeIDs: nil
    )

    XCTAssertEqual(Set(plan.visibleNodes.map(\.id)), ["david", "omi", "openai", "python"])
    XCTAssertTrue(plan.visibleNodes.allSatisfy { plan.relatedNodeIDs.contains($0.id) })
    XCTAssertLessThanOrEqual(plan.relationshipLabelEdges.count, 12)
    XCTAssertFalse(plan.relationshipLabelEdges.isEmpty)
  }

  func testRelationshipLabelsAreHiddenUntilSemanticDetailIsUseful() {
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: sampleGraph(), userName: "David")
    let overview = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot, viewportSize: CGSize(width: 1_200, height: 800), zoom: 1,
      pan: .zero, compact: false, selectedNodeID: nil, matchingNodeIDs: nil
    )
    let focus = MemoryAtlasRenderPlanner.makePlan(
      snapshot: snapshot, viewportSize: CGSize(width: 1_200, height: 800), zoom: 4,
      pan: .zero, compact: false, selectedNodeID: "david", matchingNodeIDs: nil
    )

    XCTAssertTrue(overview.relationshipLabelEdges.isEmpty)
    XCTAssertLessThanOrEqual(focus.relationshipLabelEdges.count, 12)
  }

  private func sampleGraph() -> KnowledgeGraphResponse {
    KnowledgeGraphResponse(
      nodes: [
        KnowledgeGraphNode(id: "david", label: "David", nodeType: .person),
        KnowledgeGraphNode(id: "omi", label: "Omi", nodeType: .thing),
        KnowledgeGraphNode(id: "openai", label: "OpenAI", nodeType: .organization),
        KnowledgeGraphNode(id: "python", label: "Python", nodeType: .thing),
      ],
      edges: [
        KnowledgeGraphEdge(id: "work", sourceId: "david", targetId: "omi", label: "works_on"),
        KnowledgeGraphEdge(id: "with", sourceId: "david", targetId: "openai", label: "works_with"),
        KnowledgeGraphEdge(id: "uses", sourceId: "david", targetId: "python", label: "uses"),
      ]
    )
  }
}
