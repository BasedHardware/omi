import XCTest
@testable import Omi_Computer

final class MemoryAtlasCommunityDetectorTests: XCTestCase {
  func testDetectionIsDeterministicAcrossInputOrdering() {
    let graph = clusteredGraph()
    let first = MemoryAtlasCommunityDetector.detect(graph: graph, ownerNodeID: "owner")
    let reversed = MemoryAtlasCommunityDetector.detect(
      graph: KnowledgeGraphResponse(nodes: graph.nodes.reversed(), edges: graph.edges.reversed()),
      ownerNodeID: "owner"
    )

    XCTAssertEqual(first, reversed)
    XCTAssertGreaterThanOrEqual(first.communities.count, 4)
    XCTAssertLessThanOrEqual(first.communities.count, 7)
    XCTAssertEqual(first.communityIDByNodeID.count, graph.nodes.count)
  }

  func testOwnerFanDoesNotCollapseDistinctNeighborhoods() {
    let projection = MemoryAtlasCommunityDetector.detect(graph: clusteredGraph(), ownerNodeID: "owner")
    let groups = (0..<4).compactMap { projection.communityIDByNodeID["anchor-\($0)"] }

    XCTAssertEqual(Set(groups).count, 4)
    XCTAssertFalse(projection.communities.contains { $0.anchorNodeID == "owner" })
  }

  func testPreviousAnchorsAndCommunityIDsSurviveGraphGrowth() throws {
    let graph = clusteredGraph()
    let first = MemoryAtlasCommunityDetector.detect(graph: graph, ownerNodeID: "owner")
    let expanded = KnowledgeGraphResponse(
      nodes: graph.nodes + [node("new", evidence: 20)],
      edges: graph.edges + [edge("new-link", "new", "anchor-0", memories: 12)]
    )
    let second = MemoryAtlasCommunityDetector.detect(graph: expanded, ownerNodeID: "owner", previous: first)

    XCTAssertEqual(first.communities.map(\.id), second.communities.map(\.id))
    XCTAssertEqual(first.communities.map(\.anchorNodeID), second.communities.map(\.anchorNodeID))
    XCTAssertEqual(second.communityIDByNodeID["new"], first.communityIDByNodeID["anchor-0"])
  }

  func testHysteresisKeepsMembershipForSmallAffinityChange() throws {
    let graph = clusteredGraph()
    let first = MemoryAtlasCommunityDetector.detect(graph: graph, ownerNodeID: "owner")
    let oldCommunity = try XCTUnwrap(first.communityIDByNodeID["member-0"])
    let competingAnchor = try XCTUnwrap(
      first.communities.first(where: { $0.id != oldCommunity })?.anchorNodeID
    )
    let changed = KnowledgeGraphResponse(
      nodes: graph.nodes,
      edges: graph.edges + [edge("weak-competition", "member-0", competingAnchor, memories: 1)]
    )
    let second = MemoryAtlasCommunityDetector.detect(graph: changed, ownerNodeID: "owner", previous: first)

    XCTAssertEqual(second.communityIDByNodeID["member-0"], oldCommunity)
  }

  func testMissingAnchorPromotesFallbackWithoutChangingCommunityIdentity() throws {
    let graph = clusteredGraph()
    let first = MemoryAtlasCommunityDetector.detect(graph: graph, ownerNodeID: "owner")
    let removed = try XCTUnwrap(first.communities.first)
    let expectedReplacement = try XCTUnwrap(removed.fallbackNodeIDs.first)
    let graphWithoutAnchor = KnowledgeGraphResponse(
      nodes: graph.nodes.filter { $0.id != removed.anchorNodeID },
      edges: graph.edges.filter { $0.sourceId != removed.anchorNodeID && $0.targetId != removed.anchorNodeID }
    )
    let second = MemoryAtlasCommunityDetector.detect(graph: graphWithoutAnchor, ownerNodeID: "owner", previous: first)
    let replacement = try XCTUnwrap(second.communities.first(where: { $0.id == removed.id }))

    XCTAssertEqual(replacement.anchorNodeID, expectedReplacement)
    XCTAssertEqual(replacement.id, removed.id)
  }

  func testSparseAndEmptyGraphsBehaveGracefully() {
    let empty = MemoryAtlasCommunityDetector.detect(graph: .init(nodes: [], edges: []))
    let sparse = MemoryAtlasCommunityDetector.detect(
      graph: .init(nodes: [node("only", evidence: 0)], edges: [])
    )

    XCTAssertTrue(empty.communities.isEmpty)
    XCTAssertEqual(sparse.communities.count, 1)
    XCTAssertEqual(sparse.communityIDByNodeID["only"], sparse.communities.first?.id)
  }

  func testRenamingAnchorRefreshesCommunityDisplayName() throws {
    let graph = clusteredGraph()
    let first = MemoryAtlasCommunityDetector.detect(graph: graph, ownerNodeID: "owner")
    let community = try XCTUnwrap(first.communities.first)
    let renamedNodes = graph.nodes.map { node in
      guard node.id == community.anchorNodeID else { return node }
      return KnowledgeGraphNode(
        id: node.id, label: "Renamed Topic", nodeType: node.nodeType, aliases: node.aliases,
        memoryIds: node.memoryIds, createdAt: node.createdAt, updatedAt: node.updatedAt
      )
    }
    let second = MemoryAtlasCommunityDetector.detect(
      graph: .init(nodes: renamedNodes, edges: graph.edges), ownerNodeID: "owner", previous: first
    )

    XCTAssertEqual(second.communities.first(where: { $0.id == community.id })?.displayName, "Renamed Topic")
  }

  func testProductionScaleProjectionCompletesAndAssignsEveryNode() {
    let nodes = (0..<1_200).map { node("n-\($0)", evidence: ($0 % 8) + 1) }
    let edges = (0..<1_800).map { index in
      edge("e-\(index)", "n-\(index % 1_200)", "n-\((index * 37 + 41) % 1_200)", memories: index % 5)
    }
    let projection = MemoryAtlasCommunityDetector.detect(graph: .init(nodes: nodes, edges: edges))

    XCTAssertEqual(projection.communityIDByNodeID.count, 1_200)
    XCTAssertEqual(projection.communities.count, 7)
  }

  private func clusteredGraph() -> KnowledgeGraphResponse {
    var nodes = [KnowledgeGraphNode(id: "owner", label: "Owner", nodeType: .person, memoryIds: ["owner"])]
    var edges: [KnowledgeGraphEdge] = []
    for cluster in 0..<4 {
      nodes.append(node("anchor-\(cluster)", evidence: 12 - cluster))
      nodes.append(node("member-\(cluster)", evidence: 2))
      edges.append(edge("internal-\(cluster)", "anchor-\(cluster)", "member-\(cluster)", memories: 8))
      edges.append(edge("owner-\(cluster)", "owner", "anchor-\(cluster)", label: "related_to", memories: 20))
    }
    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }

  private func node(_ id: String, evidence: Int) -> KnowledgeGraphNode {
    KnowledgeGraphNode(
      id: id, label: id.replacingOccurrences(of: "-", with: " ").capitalized, nodeType: .concept,
      memoryIds: (0..<evidence).map { "\(id)-m-\($0)" }, updatedAt: Date(timeIntervalSince1970: 100)
    )
  }

  private func edge(
    _ id: String, _ source: String, _ target: String, label: String = "builds", memories: Int
  ) -> KnowledgeGraphEdge {
    KnowledgeGraphEdge(
      id: id, sourceId: source, targetId: target, label: label,
      memoryIds: (0..<memories).map { "\(id)-m-\($0)" }, createdAt: Date(timeIntervalSince1970: 100)
    )
  }
}
