import XCTest

@testable import Omi_Computer

final class KnowledgeGraphToolSupportTests: XCTestCase {
  func testClientGraphCrossesDetachedTaskWithoutErasingNodeData() async {
    let graph = KnowledgeGraphToolSupport.ClientGraph(
      nodes: [
        .init(id: "node", label: "Node", nodeType: "concept", aliases: ["alias"])
      ],
      edges: [
        .init(sourceId: "source", targetId: "target", label: "relates_to")
      ])

    let transferred = await Task.detached { graph }.value

    XCTAssertEqual(transferred.nodes.map(\.id), ["node"])
    XCTAssertEqual(transferred.nodes.first?.aliases, ["alias"])
    XCTAssertEqual(transferred.edges.first?.sourceId, "source")
    XCTAssertEqual(transferred.edges.first?.targetId, "target")
    XCTAssertEqual(transferred.nodesAsPayload.first?["node_type"] as? String, "concept")
    XCTAssertEqual(transferred.edgesAsPayload.first?["target_id"] as? String, "target")
  }
}
