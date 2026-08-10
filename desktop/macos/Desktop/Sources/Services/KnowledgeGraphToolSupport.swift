import Foundation

enum KnowledgeGraphToolSupport {
  struct ClientGraph {
    let nodes: [[String: Any]]
    let edges: [[String: Any]]
  }

  enum ResolveOutcome {
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
        [
          "id": node.id,
          "label": node.label,
          "node_type": node.nodeType.rawValue,
          "aliases": node.aliases,
        ] as [String: Any]
      }
      let edges = extracted.edges.map { edge in
        [
          "source_id": edge.sourceId,
          "target_id": edge.targetId,
          "label": edge.label,
        ] as [String: Any]
      }
      return .success(ClientGraph(nodes: nodes, edges: edges))
    } catch {
      return .failure(
        "Error: backend knowledge graph extract failed: \(error.localizedDescription)")
    }
  }
}
