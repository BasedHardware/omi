import Foundation
import OmiCore

/// The knowledge graph Omi builds from memories (`GET v1/knowledge-graph`, one capped page).
public struct KnowledgeGraph: Sendable, Equatable {
    public struct Node: Sendable, Equatable, Identifiable {
        public let id: String
        public let label: String
        /// `person`, `place`, `organization`, `thing`, `concept` (canonical data also `user`, `entity`).
        public let kind: String
        public let memoryIDs: [String]

        public init(id: String, label: String, kind: String, memoryIDs: [String] = []) {
            self.id = id
            self.label = label
            self.kind = kind
            self.memoryIDs = memoryIDs
        }
    }

    public struct Edge: Sendable, Equatable, Hashable {
        public let source: String
        public let target: String
        public let label: String

        public init(source: String, target: String, label: String) {
            self.source = source
            self.target = target
            self.label = label
        }
    }

    public let nodes: [Node]
    public let edges: [Edge]

    public init(nodes: [Node], edges: [Edge]) {
        self.nodes = nodes
        self.edges = edges
    }
}

/// Memory management beyond add/edit/delete. Contracts from `backend/routers/memories.py`
/// and `knowledge_graph.py`; the Flutter calls are in `app/lib/backend/http/api/memories.dart`.
public extension APIClient {
    /// `PATCH v3/memories/{id}/visibility` with `{"value": "private"|"public"}`.
    func setMemoryVisibility(id: String, visibility: Memory.Visibility) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["value": visibility.rawValue])
        _ = try await data(.patch, "v3/memories/\(id)/visibility", body: .json(body))
    }

    /// `PATCH v3/memories/{id}/baseline?value=`.
    func setMemoryBaseline(id: String, pinned: Bool) async throws {
        _ = try await data(.patch, "v3/memories/\(id)/baseline", query: [URLQueryItem(name: "value", value: String(pinned))])
    }

    /// `POST v3/memories/{id}/review?value=`: true keeps it, false discards it (it leaves the list).
    func reviewMemory(id: String, isRight: Bool) async throws {
        _ = try await data(.post, "v3/memories/\(id)/review", query: [URLQueryItem(name: "value", value: String(isRight))])
    }

    /// `DELETE v3/memories` (`scope=all`): every memory, for good.
    func deleteAllMemories() async throws {
        _ = try await data(.delete, "v3/memories", query: [URLQueryItem(name: "scope", value: "all")])
    }

    /// `GET v1/knowledge-graph`; duplicate and self-loop edges are dropped.
    func knowledgeGraph() async throws -> KnowledgeGraph {
        var graphRequest = try await request(.get, "v1/knowledge-graph")
        graphRequest.timeoutInterval = 60
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: graphRequest)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            throw APIError.http(status: status, body: String(bytes: data.prefix(500), encoding: .utf8) ?? "")
        }
        return KnowledgeGraphMapper.map((try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:])
    }
}

enum KnowledgeGraphMapper {
    static func map(_ json: [String: Any]) -> KnowledgeGraph {
        let nodes = (json["nodes"] as? [[String: Any]] ?? []).compactMap { node -> KnowledgeGraph.Node? in
            guard let id = node["id"] as? String else { return nil }
            return KnowledgeGraph.Node(
                id: id, label: node["label"] as? String ?? id, kind: node["node_type"] as? String ?? "concept",
                memoryIDs: node["memory_ids"] as? [String] ?? []
            )
        }
        let known = Set(nodes.map(\.id))
        var seen = Set<String>()
        let edges = (json["edges"] as? [[String: Any]] ?? []).compactMap { edge -> KnowledgeGraph.Edge? in
            guard let source = edge["source_id"] as? String, let target = edge["target_id"] as? String,
                  source != target, known.contains(source), known.contains(target),
                  seen.insert([source, target].sorted().joined(separator: "|")).inserted else { return nil }
            return KnowledgeGraph.Edge(source: source, target: target, label: edge["label"] as? String ?? "")
        }
        return KnowledgeGraph(nodes: nodes, edges: edges)
    }
}
