import Foundation
@preconcurrency import GRDB

// MARK: - Local Knowledge Graph Node Record

struct LocalKGNodeRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?
  var nodeId: String
  var label: String
  var nodeType: String
  var aliasesJson: String?
  var sourceFileIds: String?
  var createdAt: Date
  var updatedAt: Date

  static let databaseTableName = "local_kg_nodes"

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }

  /// Convert to API-compatible KnowledgeGraphNode
  func toKnowledgeGraphNode() -> KnowledgeGraphNode {
    let aliases: [String]
    if let json = aliasesJson, let data = json.data(using: .utf8),
      let parsed = try? JSONDecoder().decode([String].self, from: data)
    {
      aliases = parsed
    } else {
      aliases = []
    }
    // A Brain Map rebuild stores what each entity cites here as a JSON array;
    // file indexing left the column empty, which decodes to no citations.
    let citations: [String]
    if let json = sourceFileIds, let data = json.data(using: .utf8),
      let parsed = try? JSONDecoder().decode([String].self, from: data)
    {
      citations = parsed
    } else {
      citations = []
    }
    return KnowledgeGraphNode(
      id: nodeId,
      label: label,
      nodeType: KnowledgeGraphNodeType(rawValue: nodeType) ?? .concept,
      aliases: aliases,
      memoryIds: citations,
      createdAt: createdAt,
      updatedAt: updatedAt
    )
  }
}

// MARK: - Local Knowledge Graph Edge Record

struct LocalKGEdgeRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?
  var edgeId: String
  var sourceNodeId: String
  var targetNodeId: String
  var label: String
  var createdAt: Date
  /// What the relationship cites, as a JSON array of citation ids. A Brain
  /// Map rebuild writes it; file indexing leaves it empty.
  var memoryIdsJson: String? = nil

  static let databaseTableName = "local_kg_edges"

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }

  /// Convert to API-compatible KnowledgeGraphEdge
  func toKnowledgeGraphEdge() -> KnowledgeGraphEdge {
    let citations: [String]
    if let json = memoryIdsJson, let data = json.data(using: .utf8),
      let parsed = try? JSONDecoder().decode([String].self, from: data)
    {
      citations = parsed
    } else {
      citations = []
    }
    return KnowledgeGraphEdge(
      id: edgeId,
      sourceId: sourceNodeId,
      targetId: targetNodeId,
      label: label,
      memoryIds: citations,
      createdAt: createdAt
    )
  }
}

// MARK: - Reserved identifiers

/// The `brainmap:` id prefix belongs to the Brain Map rebuild, which replaces
/// every row carrying it. A row the file indexer or a chat tool saves under
/// that prefix would be wiped by the next rebuild, so their ids are moved off
/// it here before they are written.
enum LocalKGReservedIdentifiers {
  static let rebuildPrefix = BrainMapLocalGraphAssembly.nodeIDPrefix
  static let relocatedPrefix = "local:"

  static func relocated(_ id: String) -> String {
    id.hasPrefix(rebuildPrefix) ? relocatedPrefix + id : id
  }

  static func relocating(
    nodes: [LocalKGNodeRecord], edges: [LocalKGEdgeRecord]
  ) -> (nodes: [LocalKGNodeRecord], edges: [LocalKGEdgeRecord]) {
    let nodes = nodes.map { node in
      var node = node
      node.nodeId = relocated(node.nodeId)
      return node
    }
    let edges = edges.map { edge in
      var edge = edge
      edge.edgeId = relocated(edge.edgeId)
      edge.sourceNodeId = relocated(edge.sourceNodeId)
      edge.targetNodeId = relocated(edge.targetNodeId)
      return edge
    }
    return (nodes, edges)
  }
}
