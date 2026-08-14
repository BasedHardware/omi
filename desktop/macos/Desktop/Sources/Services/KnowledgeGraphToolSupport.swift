import Foundation

enum KnowledgeGraphToolSupport {
  /// Release-lane contract: this type crosses the async seam out of `resolveDiscoveryText`, so it
  /// must stay `Sendable`: the whole-module release compile (the auto-release gate) rejects a
  /// non-Sendable return here even when debug builds stay quiet. See #11373/#11374.
  struct ClientGraph: Sendable {
    struct Node: Sendable {
      let id: String
      let label: String
      let nodeType: String
      let aliases: [String]
    }

    struct Edge: Sendable {
      let sourceId: String
      let targetId: String
      let label: String
    }

    let nodes: [Node]
    let edges: [Edge]

    var nodesAsPayload: [[String: Any]] {
      nodes.map { node in
        [
          "id": node.id,
          "label": node.label,
          "node_type": node.nodeType,
          "aliases": node.aliases,
        ] as [String: Any]
      }
    }

    var edgesAsPayload: [[String: Any]] {
      edges.map { edge in
        [
          "source_id": edge.sourceId,
          "target_id": edge.targetId,
          "label": edge.label,
        ] as [String: Any]
      }
    }
  }

  enum ResolveOutcome: Sendable {
    case success(ClientGraph)
    case failure(String)
  }

  /// Resolve `discovery_text` through backend knowledge_graph SSOT extract.
  static func resolveDiscoveryText(
    _ discoveryText: String,
    expectedOwnerId: String?
  ) async -> ResolveOutcome {
    let trimmed = discoveryText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      return .failure("Error: 'discovery_text' or 'nodes' is required")
    }
    do {
      let extracted = try await APIClient.shared.extractKnowledgeGraph(
        text: trimmed,
        expectedOwnerId: expectedOwnerId)
      let nodes = extracted.nodes.map { node in
        ClientGraph.Node(
          id: node.id,
          label: node.label,
          nodeType: node.nodeType.rawValue,
          aliases: node.aliases)
      }
      let edges = extracted.edges.map { edge in
        ClientGraph.Edge(
          sourceId: edge.sourceId,
          targetId: edge.targetId,
          label: edge.label)
      }
      return .success(ClientGraph(nodes: nodes, edges: edges))
    } catch {
      return .failure(
        "Error: backend knowledge graph extract failed: \(error.localizedDescription)")
    }
  }
}
