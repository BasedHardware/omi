import Foundation
@preconcurrency import GRDB

/// Actor for local knowledge graph CRUD operations
actor KnowledgeGraphStorage {
  static let shared = KnowledgeGraphStorage()

  private var _dbQueue: DatabasePool?
  private var _dbGeneration = -1

  private init() {}

  private func ensureDB() async throws -> DatabasePool {
    if let db = _dbQueue, await RewindDatabase.shared.poolGeneration() == _dbGeneration { return db }

    try await RewindDatabase.shared.initialize()
    let (queue, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let db = queue else {
      throw NSError(
        domain: "KnowledgeGraphStorage", code: 1, userInfo: [NSLocalizedDescriptionKey: "Database not initialized"])
    }
    _dbQueue = db
    _dbGeneration = generation
    return db
  }

  func invalidateCache() {
    _dbQueue = nil
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
    // Rows saved here must survive a Brain Map rebuild, which replaces every
    // row under its own prefix; a row that arrives under it is moved off it.
    let (nodes, edges) = LocalKGReservedIdentifiers.relocating(nodes: nodes, edges: edges)

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
              INSERT OR REPLACE INTO local_kg_edges (edgeId, sourceNodeId, targetNodeId, label, createdAt, memoryIdsJson)
              VALUES (?, ?, ?, ?, ?, ?)
              """,
            arguments: [
              edge.edgeId, edge.sourceNodeId, edge.targetNodeId, edge.label, edge.createdAt, edge.memoryIdsJson,
            ]
          )
        }
        // Throwing here rolls the transaction back if ownership changed
        // while a larger graph was being applied.
        try authorization.require()
      }
    }

    log("KnowledgeGraphStorage: Merged \(nodes.count) nodes, \(edges.count) edges")
  }

  /// Replace the locally rebuilt Brain Map: every row whose id carries the
  /// rebuild prefix goes, everything else in the tables stays, and the new
  /// rows land in the same transaction so a reader never sees half a map.
  func replaceRebuiltGraph(
    nodes: [LocalKGNodeRecord],
    edges: [LocalKGEdgeRecord],
    authorization: LocalMutationAuthorization
  ) async throws {
    try authorization.require()
    let db = try await ensureDB()
    let prefix = BrainMapLocalGraphAssembly.nodeIDPrefix

    try await authorization.withCommitLease {
      try await db.write { database in
        try authorization.require()
        try database.execute(sql: "DELETE FROM local_kg_edges WHERE edgeId LIKE ?", arguments: [prefix + "%"])
        try database.execute(sql: "DELETE FROM local_kg_nodes WHERE nodeId LIKE ?", arguments: [prefix + "%"])
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
              INSERT OR REPLACE INTO local_kg_edges (edgeId, sourceNodeId, targetNodeId, label, createdAt, memoryIdsJson)
              VALUES (?, ?, ?, ?, ?, ?)
              """,
            arguments: [
              edge.edgeId, edge.sourceNodeId, edge.targetNodeId, edge.label, edge.createdAt, edge.memoryIdsJson,
            ]
          )
        }
        try authorization.require()
      }
    }

    log("KnowledgeGraphStorage: Replaced rebuilt Brain Map with \(nodes.count) nodes, \(edges.count) edges")
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

// MARK: - Schema

/// Migrations for the local knowledge-graph tables, registered from
/// `RewindDatabase` alongside the rest of the schema.
enum LocalKGSchema {
  static func registerMigrations(on migrator: inout DatabaseMigrator) {
    // A Brain Map rebuild cites what each relationship came from; the edge
    // table predates that and only carried the node's citations.
    migrator.registerMigration("addLocalKGEdgeCitations") { db in
      guard try db.columns(in: "local_kg_edges").contains(where: { $0.name == "memoryIdsJson" }) == false else {
        return
      }
      try db.alter(table: "local_kg_edges") { t in
        t.add(column: "memoryIdsJson", .text)
      }
    }
  }
}
