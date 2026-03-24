import Foundation
import GRDB

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
           let parsed = try? JSONDecoder().decode([String].self, from: data) {
            aliases = parsed
        } else {
            aliases = []
        }
        return KnowledgeGraphNode(
            id: nodeId,
            label: label,
            nodeType: KnowledgeGraphNodeType(rawValue: nodeType) ?? .concept,
            aliases: aliases,
            memoryIds: [],
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

    static let databaseTableName = "local_kg_edges"

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    /// Convert to API-compatible KnowledgeGraphEdge
    func toKnowledgeGraphEdge() -> KnowledgeGraphEdge {
        KnowledgeGraphEdge(
            id: edgeId,
            sourceId: sourceNodeId,
            targetId: targetNodeId,
            label: label,
            memoryIds: [],
            createdAt: createdAt
        )
    }
}
