import Foundation
import Observation
import OmiCore
import OmiNetwork

/// What Omi knows about the user, grouped by category. Management (undo delete, visibility,
/// baseline, review, delete all) is in `MemoriesStore+Manage.swift`.
@MainActor
@Observable
public final class MemoriesStore {
    public enum Phase: Equatable, Sendable { case idle, loading, loaded, failed(String) }

    /// A delete waiting out its undo window: the memory is off the list, the backend not told yet.
    public struct PendingDeletion: Equatable, Sendable {
        public let memory: Memory
        let index: Int
    }

    /// Flutter's three kinds (`MemoryCategory`), always offered as filters: what Omi learned about
    /// the user, insights from conversations, and what the user typed in.
    public static let kinds = ["system", "interesting", "manual"]

    public internal(set) var phase: Phase = .idle
    public internal(set) var memories: [Memory] = []
    /// Set when an action failed.
    public internal(set) var lastError: String?
    public internal(set) var pendingDeletion: PendingDeletion?
    /// Memories the backend holds back as conflicts (`MemoriesStore+Review.swift`).
    public internal(set) var reviewConflicts: [MemoryConflict] = []

    let api: any APIClientProtocol
    private let pageSize: Int
    let undoWindow: Duration
    var deletionTask: Task<Void, Never>?

    /// `pageSize` 500 is the backend maximum.
    public init(api: any APIClientProtocol, pageSize: Int = 500, undoWindow: Duration = .seconds(5)) {
        self.api = api
        self.pageSize = pageSize
        self.undoWindow = undoWindow
    }

    /// Every memory: pages until one comes back short.
    public func load() async {
        if memories.isEmpty { phase = .loading }
        do {
            let all = try await Paging.all(pageSize: pageSize) { try await api.memories(limit: $0, offset: $1) }
            let hidden = pendingDeletion?.memory.id
            memories = all.filter { $0.id != hidden }
            phase = .loaded
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// A memory the user types in themselves. Returns whether the backend took it.
    @discardableResult
    public func add(_ content: String) async -> Bool {
        let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return false }
        lastError = nil
        do {
            memories.insert(try await api.createMemory(content: text, category: "manual"), at: 0)
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }

    /// Optimistic edit; the old text comes back if the backend refuses.
    public func edit(_ id: String, content: String) async {
        let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let index = memories.firstIndex(where: { $0.id == id }) else { return }
        let previous = memories[index].content
        memories[index].content = text
        do {
            try await api.editMemory(id: id, content: text)
        } catch {
            if let index = memories.firstIndex(where: { $0.id == id }) { memories[index].content = previous }
        }
    }

    /// Optimistic delete; the memory comes back if the backend refuses.
    public func delete(_ id: String) async {
        guard let index = memories.firstIndex(where: { $0.id == id }) else { return }
        let removed = memories.remove(at: index)
        do {
            try await api.deleteMemory(id: id)
        } catch {
            memories.insert(removed, at: min(index, memories.count))
        }
    }

    /// Categories by size, newest memory first inside each.
    public func grouped(matching query: String = "") -> [(category: String, memories: [Memory])] {
        let needle = query.trimmingCharacters(in: .whitespaces)
        let visible = needle.isEmpty ? memories : memories.filter { $0.content.localizedCaseInsensitiveContains(needle) }
        return Dictionary(grouping: visible, by: \.category)
            .map { ($0.key, $0.value.sorted { $0.createdAt > $1.createdAt }) }
            .sorted { $0.1.count == $1.1.count ? $0.0 < $1.0 : $0.1.count > $1.1.count }
    }

    /// The filter chips: the three kinds first (always), then any other category present, with counts.
    public func filterChips(matching query: String = "") -> [(category: String, count: Int)] {
        let counts = Dictionary(grouping: grouped(matching: query), by: \.category).mapValues { $0.first?.memories.count ?? 0 }
        let others = counts.keys.filter { !Self.kinds.contains($0) }.sorted { counts[$0, default: 0] > counts[$1, default: 0] }
        return (Self.kinds + others).map { ($0, counts[$0, default: 0]) }
    }

    /// Newest first, narrowed to one category (`nil`: all) and the search text.
    public func visible(matching query: String = "", category: String? = nil) -> [Memory] {
        grouped(matching: query)
            .filter { category == nil || $0.category == category }
            .flatMap(\.memories)
            .sorted { $0.createdAt > $1.createdAt }
    }
}
