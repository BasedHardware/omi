import Foundation
import OmiCore
import OmiNetwork

/// Backend state for memory management and the knowledge graph.
public final class FakeMemoryExtras: @unchecked Sendable {
    /// One entry per call, e.g. `visibility:m1=public`, `baseline:m1=true`, `review:m2=false`, `delete-all`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix), leaving the rest working.
    public var failing: Set<String> = []
    public var graph = KnowledgeGraph(
        nodes: [
            .init(id: "kg-user", label: "Me", kind: "user"),
            .init(id: "kg-anna", label: "Anna", kind: "person", memoryIDs: ["m2"]),
            .init(id: "kg-berlin", label: "Berlin", kind: "place"),
        ],
        edges: [
            .init(source: "kg-user", target: "kg-anna", label: "works with"),
            .init(source: "kg-user", target: "kg-berlin", label: "lives in"),
        ]
    )

    /// The backend's review queue (`memoryReviewQueue`); resolved ones leave it.
    public var conflicts: [MemoryConflict] = []

    public init() {}
}

public extension FakeAPIClient {
    private func recordMemory(_ kind: String, _ entry: String) throws {
        try lock.withLock {
            if let _error { throw _error }
            memoryExtras.log.append(entry.isEmpty ? kind : "\(kind):\(entry)")
            if memoryExtras.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    private func updateMemory(_ id: String, _ change: (inout Memory) -> Void) {
        lock.withLock {
            if let index = _memories.firstIndex(where: { $0.id == id }) { change(&_memories[index]) }
        }
    }

    func setMemoryVisibility(id: String, visibility: Memory.Visibility) async throws {
        try recordMemory("visibility", "\(id)=\(visibility.rawValue)")
        updateMemory(id) { $0.visibility = visibility }
    }

    func setMemoryBaseline(id: String, pinned: Bool) async throws {
        try recordMemory("baseline", "\(id)=\(pinned)")
        updateMemory(id) { $0.isBaseline = pinned }
    }

    func reviewMemory(id: String, isRight: Bool) async throws {
        try recordMemory("review", "\(id)=\(isRight)")
        if isRight {
            updateMemory(id) {
                $0.reviewed = true
                $0.userReview = true
            }
        } else {
            lock.withLock { _memories.removeAll { $0.id == id } }
        }
    }

    func memoryReviewQueue() async throws -> [MemoryConflict] {
        try recordMemory("queue", "")
        return lock.withLock { memoryExtras.conflicts }
    }

    func resolveMemoryConflict(id: String, decision: MemoryConflict.Decision) async throws {
        try recordMemory("resolve", "\(id)=\(decision.rawValue)")
        lock.withLock { memoryExtras.conflicts.removeAll { $0.id == id } }
    }

    func deleteAllMemories() async throws {
        try recordMemory("delete-all", "")
        lock.withLock { _memories = [] }
    }

    func knowledgeGraph() async throws -> KnowledgeGraph {
        try recordMemory("graph", "")
        return memoryExtras.graph
    }
}
