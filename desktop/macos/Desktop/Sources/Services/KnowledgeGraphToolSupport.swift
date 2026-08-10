import Foundation

enum KnowledgeGraphToolSupport {
  /// Release-lane contract: this type crosses the async seam out of `resolveDiscoveryText`, so it
  /// must stay `Sendable`: the whole-module release compile (the auto-release gate) rejects a
  /// non-Sendable return here even when debug builds stay quiet. See #11373/#11374.
  ///
  /// The dictionaries are `[String: Any]` because the tool plumbing consumes heterogeneous
  /// JSON-shaped values, but every value put in them here is an immutable `String` or `[String]`
  /// built locally in `resolveDiscoveryText` — nothing shared or mutable crosses the boundary.
  /// `@unchecked` because `Any` erases what the initializer guarantees; the release
  /// (whole-module) compile otherwise rejects returning this across the async seam.
  struct ClientGraph: @unchecked Sendable {
    let nodes: [[String: Any]]
    let edges: [[String: Any]]
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
