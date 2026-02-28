import Foundation
import GRDB

/// Actor for local knowledge graph CRUD operations
actor KnowledgeGraphStorage {
    static let shared = KnowledgeGraphStorage()

    private var _dbQueue: DatabasePool?

    private init() {}

    private func ensureDB() async throws -> DatabasePool {
        if let db = _dbQueue { return db }

        try await RewindDatabase.shared.initialize()
        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw NSError(domain: "KnowledgeGraphStorage", code: 1, userInfo: [NSLocalizedDescriptionKey: "Database not initialized"])
        }
        _dbQueue = db
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

    /// Save nodes and edges (clears existing data first)
    func saveGraph(nodes: [LocalKGNodeRecord], edges: [LocalKGEdgeRecord]) async throws {
        let db = try await ensureDB()

        try await db.write { database in
            try database.execute(sql: "DELETE FROM local_kg_edges")
            try database.execute(sql: "DELETE FROM local_kg_nodes")

            for node in nodes {
                let record = node
                try record.insert(database)
            }
            for edge in edges {
                let record = edge
                try record.insert(database)
            }
        }

        log("KnowledgeGraphStorage: Saved \(nodes.count) nodes, \(edges.count) edges")
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
