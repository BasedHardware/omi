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
