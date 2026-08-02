import Foundation

/// Builds `local_kg_*` records from parsed extraction payloads.
/// Mirrors the merge semantics of `ChatToolExecutor.executeSaveKnowledgeGraph`.
enum KnowledgeGraphRecordBuilder {
  struct ParsedNode {
    let id: String
    let label: String
    let nodeType: String
    let aliases: [String]
  }

  struct ParsedEdge {
    let sourceId: String
    let targetId: String
    let label: String
  }

  static func buildRecords(
    nodes: [ParsedNode],
    edges: [ParsedEdge],
    createdAt: Date = Date()
  ) -> (nodes: [LocalKGNodeRecord], edges: [LocalKGEdgeRecord]) {
    var nodeRecords: [LocalKGNodeRecord] = []
    var edgeRecords: [LocalKGEdgeRecord] = []
    var seenLabels: [String: String] = [:]
    var idRemap: [String: String] = [:]

    for node in nodes {
      let lowerLabel = node.label.lowercased()
      if let existingId = seenLabels[lowerLabel] {
        idRemap[node.id] = existingId
        continue
      }

      seenLabels[lowerLabel] = node.id
      idRemap[node.id] = node.id

      var aliasesJson: String?
      if !node.aliases.isEmpty, let data = try? JSONEncoder().encode(node.aliases) {
        aliasesJson = String(data: data, encoding: .utf8)
      }

      nodeRecords.append(
        LocalKGNodeRecord(
          nodeId: node.id,
          label: node.label,
          nodeType: node.nodeType,
          aliasesJson: aliasesJson,
          sourceFileIds: nil,
          createdAt: createdAt,
          updatedAt: createdAt
        ))
    }

    for edge in edges {
      let remappedSource = idRemap[edge.sourceId] ?? edge.sourceId
      let remappedTarget = idRemap[edge.targetId] ?? edge.targetId
      guard remappedSource != remappedTarget else { continue }

      let edgeId =
        "\(remappedSource)_\(remappedTarget)_\(edge.label.lowercased().replacingOccurrences(of: " ", with: "_"))"
      edgeRecords.append(
        LocalKGEdgeRecord(
          edgeId: edgeId,
          sourceNodeId: remappedSource,
          targetNodeId: remappedTarget,
          label: edge.label,
          createdAt: createdAt
        ))
    }

    return (nodeRecords, edgeRecords)
  }

  static func parseExtractionJSON(_ jsonText: String) -> (nodes: [ParsedNode], edges: [ParsedEdge])? {
    guard let data = jsonText.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }

    let nodesArray = root["nodes"] as? [[String: Any]] ?? []
    let edgesArray = root["edges"] as? [[String: Any]] ?? []

    let nodes: [ParsedNode] = nodesArray.compactMap { node in
      guard let id = node["id"] as? String,
        let label = node["label"] as? String
      else { return nil }
      let nodeType = node["node_type"] as? String ?? "concept"
      let aliases = node["aliases"] as? [String] ?? []
      return ParsedNode(id: id, label: label, nodeType: nodeType, aliases: aliases)
    }

    let edges: [ParsedEdge] = edgesArray.compactMap { edge in
      guard let sourceId = edge["source_id"] as? String,
        let targetId = edge["target_id"] as? String,
        let label = edge["label"] as? String
      else { return nil }
      return ParsedEdge(sourceId: sourceId, targetId: targetId, label: label)
    }

    return (nodes, edges)
  }
}
