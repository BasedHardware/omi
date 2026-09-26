import Foundation
@preconcurrency import GRDB

/// Actor for local knowledge graph CRUD operations
actor KnowledgeGraphStorage {
  static let shared = KnowledgeGraphStorage()
  private let repository = RewindRepository(owner: "KnowledgeGraphStorage")

  private init() {}

  private func ensureDB() async throws -> DatabasePool {
    guard let databasePool = try await repository.databasePool() else {
      throw NSError(
        domain: "KnowledgeGraphStorage", code: 1, userInfo: [NSLocalizedDescriptionKey: "Database not initialized"])
    }
    return databasePool
  }

  func invalidateCache() async {
    await repository.invalidate()
  }

  /// Load the local knowledge graph as an API-compatible response
  func loadGraph() async -> KnowledgeGraphResponse {
    guard let db = try? await ensureDB() else {
      return KnowledgeGraphResponse(nodes: [], edges: [])
    }

    do {
      return try await db.read { database in
        let nodeRecords = try LocalKGNodeRecord.fetchAll(database)
        let edgeRecords = try LocalKGEdgeRecord.fetchAll(database)

        let nodes = nodeRecords.map { $0.toKnowledgeGraphNode() }
        let edges = edgeRecords.map { $0.toKnowledgeGraphEdge() }

        return KnowledgeGraphResponse(nodes: nodes, edges: edges)
      }
    } catch {
      log("KnowledgeGraphStorage: Failed to load graph: \(error.localizedDescription)")
      return KnowledgeGraphResponse(nodes: [], edges: [])
    }
  }

  /// Merge nodes and edges into existing data (upsert, no delete)
  func mergeGraph(
    nodes: [LocalKGNodeRecord],
    edges: [LocalKGEdgeRecord],
    authorization: LocalMutationAuthorization
  ) async throws {
    try authorization.require()
    let db = try await ensureDB()

    try await authorization.withCommitLease {
      try await db.write { database in
        try authorization.require()
        for node in nodes {
          try database.execute(
            sql: """
              INSERT OR REPLACE INTO local_kg_nodes (nodeId, label, nodeType, aliasesJson, sourceFileIds, createdAt, updatedAt)
              VALUES (?, ?, ?, ?, ?, ?, ?)
              """,
            arguments: [
              node.nodeId, node.label, node.nodeType, node.aliasesJson, node.sourceFileIds, node.createdAt,
              node.updatedAt,
            ]
          )
        }
        for edge in edges {
          try database.execute(
            sql: """
              INSERT OR REPLACE INTO local_kg_edges (edgeId, sourceNodeId, targetNodeId, label, createdAt)
              VALUES (?, ?, ?, ?, ?)
              """,
            arguments: [edge.edgeId, edge.sourceNodeId, edge.targetNodeId, edge.label, edge.createdAt]
          )
        }
        // Throwing here rolls the transaction back if ownership changed
        // while a larger graph was being applied.
        try authorization.require()
      }
    }

    log("KnowledgeGraphStorage: Merged \(nodes.count) nodes, \(edges.count) edges")
  }

  /// Delete all local knowledge graph data under an explicit owner lease.
  func clearAll(authorization: LocalMutationAuthorization) async throws {
    try authorization.require()
    let db = try await ensureDB()

    try await authorization.withCommitLease {
      try await db.write { database in
        try authorization.require()
        try database.execute(sql: "DELETE FROM local_kg_edges")
        try database.execute(sql: "DELETE FROM local_kg_nodes")
        try authorization.require()
      }
    }

    log("KnowledgeGraphStorage: Cleared all graph data")
  }

  /// Check if the local graph has any data
  func isEmpty() async -> Bool {
    guard let db = try? await ensureDB() else { return true }

    do {
      return try await db.read { database in
        let count = try Int.fetchOne(database, sql: "SELECT COUNT(*) FROM local_kg_nodes") ?? 0
        return count == 0
      }
    } catch {
      return true
    }
  }
}
