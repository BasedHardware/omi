import Foundation

/// Builds `local_kg_*` records from parsed extraction payloads.
/// Mirrors the merge semantics of `ChatToolExecutor.executeSaveKnowledgeGraph`.
enum KnowledgeGraphRecordBuilder {
  /// Node types the extraction is allowed to emit. Model output for OCR/window
  /// title is untrusted, so anything outside this set is dropped rather than
  /// written into ``local_kg_*``.
  static let allowedNodeTypes: Set<String> = [
    "person", "place", "organization", "thing", "concept",
  ]

  /// Bounds for untrusted model output. OCR/window title can carry adversarial
  /// text, so ids, labels, aliases, and edge labels are length-capped and the
  /// graph size is bounded.
  static let maxFieldLength = 200
  static let maxNodes = 500
  static let maxEdges = 2_000

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

  /// Whether ``value`` is safe to store as an id or edge label. Untrusted model
  /// output must not smuggle control characters or SQL-/shell-significant text
  /// into durable records.
  static func isSafeIdentifier(_ value: String) -> Bool {
    guard !value.isEmpty, value.count <= maxFieldLength else { return false }
    for scalar in value.unicodeScalars {
      let ok =
        (scalar >= "a" && scalar <= "z")
        || (scalar >= "A" && scalar <= "Z")
        || (scalar >= "0" && scalar <= "9")
        || scalar == "_" || scalar == "-" || scalar == "."
      if !ok { return false }
    }
    return true
  }

  /// Normalize a free-text label: trim, collapse whitespace, and cap length.
  static func normalizedLabel(_ value: String) -> String? {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let collapsed =
      trimmed
      .split(whereSeparator: \.isWhitespace)
      .joined(separator: " ")
    guard collapsed.count <= maxFieldLength else { return nil }
    return collapsed
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

    let acceptedNodeIds = Set(nodeRecords.map(\.nodeId))

    for edge in edges {
      // An edge endpoint is only usable if it remaps onto a node this same call
      // accepted. Model output is untrusted, so an endpoint that names a node
      // that was dropped, disallowed, truncated away, or never emitted must not
      // become a dangling `local_kg_edges` row referencing a node that does not
      // exist.
      guard let remappedSource = idRemap[edge.sourceId],
        let remappedTarget = idRemap[edge.targetId],
        acceptedNodeIds.contains(remappedSource),
        acceptedNodeIds.contains(remappedTarget)
      else { continue }
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

    var nodes: [ParsedNode] = []
    for node in nodesArray {
      guard let rawId = node["id"] as? String,
        let rawLabel = node["label"] as? String,
        isSafeIdentifier(rawId),
        let label = normalizedLabel(rawLabel)
      else { continue }
      let nodeType = node["node_type"] as? String ?? "concept"
      guard allowedNodeTypes.contains(nodeType) else { continue }
      let aliases = (node["aliases"] as? [String] ?? [])
        .compactMap(normalizedLabel)
        .prefix(8)
      nodes.append(ParsedNode(id: rawId, label: label, nodeType: nodeType, aliases: Array(aliases)))
      if nodes.count >= maxNodes { break }
    }

    var edges: [ParsedEdge] = []
    for edge in edgesArray {
      guard let sourceId = edge["source_id"] as? String,
        let targetId = edge["target_id"] as? String,
        let rawLabel = edge["label"] as? String,
        isSafeIdentifier(sourceId),
        isSafeIdentifier(targetId),
        let label = normalizedLabel(rawLabel),
        isSafeIdentifier(label)
      else { continue }
      edges.append(ParsedEdge(sourceId: sourceId, targetId: targetId, label: label))
      if edges.count >= maxEdges { break }
    }

    return (nodes, edges)
  }
}
