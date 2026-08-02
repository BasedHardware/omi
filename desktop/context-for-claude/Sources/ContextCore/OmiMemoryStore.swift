import Foundation
import GRDB

/// A memory read from the main Omi desktop app's local database.
///
/// Mirrors the subset of `MemoryRecord` columns that Context for Claude renders.
/// `id` is the backend ID when synced, or `local_<rowid>` when the memory has
/// not reached the server yet — the same convention the main app uses.
public struct LocalMemory: Sendable, Equatable {
    public let id: String
    public let content: String
    public let category: String?

    public init(id: String, content: String, category: String?) {
        self.id = id
        self.content = content
        self.category = category
    }
}

/// Read-only access to the main Omi desktop app's `memories` table.
///
/// Opens `omi.db` with a read-only WAL connection — the same safe pattern
/// `ContextStore` uses for `context.db`. A reader never blocks the main app's
/// writer, so a Claude query can run while Omi is capturing.
///
/// `@unchecked Sendable` is honest: the only stored state is GRDB's pool, which
/// serializes its own connections.
public final class OmiMemoryStore: @unchecked Sendable {
    public static let shared = OmiMemoryStore()

    private let databaseURLProvider: () -> URL?
    private let state = PoolState()

    init(databaseURLProvider: @escaping () -> URL? = { ContextPaths.omiDatabaseURL }) {
        self.databaseURLProvider = databaseURLProvider
    }

    /// True when the main Omi app's database was found and opened.
    public var isAvailable: Bool { currentPool != nil }

    /// Searches memories by substring, matching the main app's `content LIKE` pattern.
    ///
    /// `LIKE` wildcards in the query are escaped so user text is treated literally.
    /// Only non-deleted, non-dismissed memories are returned, newest first.
    public func searchMemories(query: String, limit: Int) -> [LocalMemory] {
        guard let pool = currentPool else { return [] }
        let escaped = query
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "%", with: "\\%")
            .replacingOccurrences(of: "_", with: "\\_")
        let pattern = "%\(escaped)%"
        let clamped = max(1, min(limit, 50))
        return (try? pool.read { db in
            try LocalMemoryRow.fetchAll(
                db,
                sql: """
                SELECT id, backendId, content, category
                FROM memories
                WHERE deleted = 0 AND isDismissed = 0
                  AND content LIKE ? ESCAPE '\\'
                ORDER BY createdAt DESC
                LIMIT ?
                """,
                arguments: [pattern, clamped]
            )
        })?.compactMap { $0.toMemory() } ?? []
    }

    private var currentPool: DatabasePool? {
        state.pool(for: databaseURLProvider())
    }
}

private final class PoolState: @unchecked Sendable {
    private let lock = NSLock()
    private var url: URL?
    private var pool: DatabasePool?

    func pool(for nextURL: URL?) -> DatabasePool? {
        lock.lock()
        defer { lock.unlock() }
        guard let nextURL else {
            url = nil
            pool = nil
            return nil
        }
        if url != nextURL {
            url = nextURL
            pool = try? DatabasePool(
                path: nextURL.path,
                configuration: ContextStore.makeConfiguration(readOnly: true))
        }
        return pool
    }
}

private struct LocalMemoryRow: FetchableRecord {
    let id: Int64?
    let backendId: String?
    let content: String
    let category: String?

    enum Columns: String, ColumnExpression {
        case id, backendId, content, category
    }

    init(row: Row) {
        id = row[Columns.id]
        backendId = row[Columns.backendId]
        content = row[Columns.content] ?? ""
        category = row[Columns.category]
    }

    func toMemory() -> LocalMemory? {
        guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let memoryId = backendId ?? (id.map { "local_\($0)" } ?? "")
        return LocalMemory(id: memoryId, content: content, category: category)
    }
}
